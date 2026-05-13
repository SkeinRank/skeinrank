"""Runtime snapshot helpers shared by enrichment and search endpoints."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from skeinrank_governance.models import (
    CanonicalTerm,
    ElasticsearchBinding,
    ElasticsearchEnrichmentJob,
    GovernanceGlobalStopListEntry,
    GovernanceStopListEntry,
    TermAlias,
    TerminologyProfile,
    utc_now,
)
from sqlalchemy import select
from sqlalchemy.orm import Session


@dataclass(frozen=True)
class RuntimeAliasEntry:
    """One active alias captured inside an immutable runtime snapshot."""

    alias_value: str
    normalized_alias: str
    canonical_value: str
    normalized_canonical: str
    slot: str
    confidence: float


def build_runtime_snapshot_payload(
    session: Session,
    profile: TerminologyProfile,
    *,
    snapshot_version: str | None = None,
) -> dict[str, Any]:
    """Build a deterministic, serializable runtime snapshot payload.

    The payload intentionally stores active alias rows instead of only a version
    string. Enrichment jobs and binding-aware runtime search can then keep using
    the exact dictionary version that was active when the job was created, even
    if profile terms or aliases are edited later.
    """

    entries = active_runtime_alias_entries(session, profile)
    entry_payload = [
        {
            "alias_value": entry.alias_value,
            "normalized_alias": entry.normalized_alias,
            "canonical_value": entry.canonical_value,
            "normalized_canonical": entry.normalized_canonical,
            "slot": entry.slot,
            "confidence": entry.confidence,
        }
        for entry in entries
    ]
    checksum = _snapshot_checksum(entry_payload)
    version = snapshot_version or f"{profile.normalized_name}@{checksum[:12]}"
    return {
        "version": version,
        "checksum": checksum,
        "profile_id": profile.id,
        "profile_name": profile.name,
        "normalized_profile_name": profile.normalized_name,
        "source": "postgres",
        "created_at": utc_now().isoformat(),
        "alias_entries": entry_payload,
    }


def active_runtime_alias_entries(
    session: Session, profile: TerminologyProfile
) -> list[RuntimeAliasEntry]:
    """Return active runtime alias entries after profile/global stop lists."""

    blocked_alias_values = _active_stop_values_for_target(
        session, profile, targets=("alias", "both")
    ) | _active_global_stop_values_for_target(session, targets=("alias", "both"))
    blocked_canonical_values = _active_stop_values_for_target(
        session, profile, targets=("canonical", "both")
    ) | _active_global_stop_values_for_target(session, targets=("canonical", "both"))
    aliases = list(
        session.scalars(
            select(TermAlias)
            .join(CanonicalTerm)
            .where(
                TermAlias.profile_id == profile.id,
                TermAlias.status == "active",
                CanonicalTerm.status == "active",
            )
            .order_by(TermAlias.normalized_alias)
        )
    )
    entries: list[RuntimeAliasEntry] = []
    for alias in aliases:
        if alias.normalized_alias in blocked_alias_values:
            continue
        if alias.term.normalized_value in blocked_canonical_values:
            continue
        entries.append(
            RuntimeAliasEntry(
                alias_value=alias.alias_value,
                normalized_alias=alias.normalized_alias,
                canonical_value=alias.term.canonical_value,
                normalized_canonical=alias.term.normalized_value,
                slot=alias.term.slot,
                confidence=alias.confidence,
            )
        )
    return entries


def alias_entries_from_snapshot(
    snapshot_json: dict[str, Any] | None,
) -> list[RuntimeAliasEntry]:
    """Deserialize runtime alias entries from a stored snapshot payload."""

    if not isinstance(snapshot_json, dict):
        return []
    entries = snapshot_json.get("alias_entries")
    if not isinstance(entries, list):
        return []
    result: list[RuntimeAliasEntry] = []
    for item in entries:
        if not isinstance(item, dict):
            continue
        alias_value = str(item.get("alias_value") or "").strip()
        normalized_alias = str(item.get("normalized_alias") or alias_value).strip()
        canonical_value = str(item.get("canonical_value") or "").strip()
        normalized_canonical = str(
            item.get("normalized_canonical") or canonical_value
        ).strip()
        slot = str(item.get("slot") or "").strip()
        if not alias_value or not normalized_alias or not canonical_value or not slot:
            continue
        try:
            confidence = float(item.get("confidence", 1.0))
        except (TypeError, ValueError):
            confidence = 1.0
        result.append(
            RuntimeAliasEntry(
                alias_value=alias_value,
                normalized_alias=normalized_alias,
                canonical_value=canonical_value,
                normalized_canonical=normalized_canonical,
                slot=slot,
                confidence=confidence,
            )
        )
    return result


def alias_tuples_from_snapshot(
    snapshot_json: dict[str, Any] | None,
) -> list[tuple[str, str, str, float]]:
    """Return the tuple shape used by existing enrichment matching helpers."""

    return [
        (
            entry.normalized_alias,
            entry.canonical_value,
            entry.slot,
            entry.confidence,
        )
        for entry in alias_entries_from_snapshot(snapshot_json)
    ]


def mark_binding_snapshot_success(
    *,
    binding: ElasticsearchBinding,
    job: ElasticsearchEnrichmentJob,
    completed_at: datetime | None = None,
) -> None:
    """Promote a job-pinned snapshot to the binding runtime snapshot."""

    if not job.snapshot_version or not isinstance(job.snapshot_json, dict):
        return
    binding.last_successful_snapshot_version = job.snapshot_version
    binding.last_successful_snapshot_at = completed_at or utc_now()
    binding.last_successful_job_id = job.id
    binding.pending_snapshot_version = None
    binding.runtime_snapshot_json = dict(job.snapshot_json)


def clear_binding_pending_snapshot(binding: ElasticsearchBinding) -> None:
    """Clear the transient pending snapshot marker after failed/cancelled jobs."""

    binding.pending_snapshot_version = None


def restore_binding_previous_snapshot(
    *, binding: ElasticsearchBinding, job: ElasticsearchEnrichmentJob
) -> None:
    """Restore binding runtime snapshot metadata during alias-swap rollback."""

    binding.last_successful_snapshot_version = job.previous_snapshot_version
    binding.runtime_snapshot_json = (
        dict(job.previous_snapshot_json)
        if isinstance(job.previous_snapshot_json, dict)
        else None
    )
    binding.pending_snapshot_version = None
    binding.last_successful_snapshot_at = (
        utc_now() if job.previous_snapshot_version else None
    )
    previous_job_id = None
    result_json = job.result_json or {}
    if isinstance(result_json, dict):
        previous_job_id = result_json.get("previous_successful_job_id")
    try:
        binding.last_successful_job_id = (
            int(previous_job_id) if previous_job_id is not None else None
        )
    except (TypeError, ValueError):
        binding.last_successful_job_id = None


def binding_snapshot_status(binding: ElasticsearchBinding) -> str:
    """Return a compact runtime snapshot state for API clients."""

    if binding.pending_snapshot_version:
        return "updating"
    if binding.last_successful_snapshot_version:
        return "ready"
    return "uninitialized"


def _active_stop_values_for_target(
    session: Session, profile: TerminologyProfile, *, targets: tuple[str, ...]
) -> set[str]:
    values = session.scalars(
        select(GovernanceStopListEntry.normalized_value).where(
            GovernanceStopListEntry.profile_id == profile.id,
            GovernanceStopListEntry.is_active.is_(True),
            GovernanceStopListEntry.target.in_(targets),
        )
    )
    return set(values)


def _active_global_stop_values_for_target(
    session: Session, *, targets: tuple[str, ...]
) -> set[str]:
    values = session.scalars(
        select(GovernanceGlobalStopListEntry.normalized_value).where(
            GovernanceGlobalStopListEntry.is_active.is_(True),
            GovernanceGlobalStopListEntry.target.in_(targets),
        )
    )
    return set(values)


def _snapshot_checksum(alias_entries: list[dict[str, Any]]) -> str:
    serialized = json.dumps(alias_entries, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
