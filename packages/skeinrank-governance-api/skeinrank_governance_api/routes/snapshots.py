"""Runtime snapshot state endpoints for the governance console."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from skeinrank_governance.models import (
    ElasticsearchBinding,
    ElasticsearchEnrichmentJob,
    TerminologyProfile,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import AuthContext, require_roles
from ..dependencies import get_session
from ..runtime_snapshots import (
    RuntimeAliasEntry,
    active_runtime_alias_entries,
    alias_entries_from_snapshot,
    build_runtime_snapshot_payload,
)
from ..schemas import (
    SnapshotBindingState,
    SnapshotCounts,
    SnapshotDiffSummary,
    SnapshotHistoryItem,
    SnapshotSummaryResponse,
)

router = APIRouter(
    prefix="/v1/snapshots",
    tags=["snapshots"],
)

_RUNNING_JOB_STATUSES = {"queued", "running", "cancel_requested"}
_HISTORY_LIMIT = 25


@router.get("/summary", response_model=SnapshotSummaryResponse)
def get_snapshot_summary(
    _current_user: AuthContext = Depends(
        require_roles("admin", "moderator", "contributor")
    ),
    session: Session = Depends(get_session),
) -> SnapshotSummaryResponse:
    """Return active runtime snapshots, diffs, and recent snapshot history."""

    bindings = list(
        session.scalars(
            select(ElasticsearchBinding)
            .join(TerminologyProfile)
            .order_by(
                ElasticsearchBinding.is_enabled.desc(),
                ElasticsearchBinding.normalized_name,
            )
        )
    )
    latest_jobs = _latest_jobs_by_binding(session, bindings)
    binding_states = [
        _binding_state(
            session=session,
            binding=binding,
            latest_job=latest_jobs.get(binding.id),
        )
        for binding in bindings
    ]
    history = [
        _history_item(job)
        for job in session.scalars(
            select(ElasticsearchEnrichmentJob)
            .join(ElasticsearchBinding)
            .order_by(
                ElasticsearchEnrichmentJob.created_at.desc(),
                ElasticsearchEnrichmentJob.id.desc(),
            )
            .limit(_HISTORY_LIMIT)
        )
    ]

    return SnapshotSummaryResponse(
        counts=SnapshotCounts(
            bindings=len(binding_states),
            active_snapshots=sum(
                1 for binding in binding_states if binding.active_snapshot_version
            ),
            stale_snapshots=sum(
                1 for binding in binding_states if binding.status == "stale"
            ),
            pending_snapshots=sum(
                1 for binding in binding_states if binding.pending_snapshot_version
            ),
            failed_updates=sum(
                1 for binding in binding_states if binding.status == "failed"
            ),
            never_enriched=sum(
                1 for binding in binding_states if binding.status == "never_enriched"
            ),
            rollback_available=sum(
                1 for binding in binding_states if binding.rollback_available
            ),
        ),
        bindings=binding_states,
        history=history,
    )


def _latest_jobs_by_binding(
    session: Session,
    bindings: list[ElasticsearchBinding],
) -> dict[int, ElasticsearchEnrichmentJob]:
    binding_ids = [binding.id for binding in bindings]
    if not binding_ids:
        return {}

    jobs = list(
        session.scalars(
            select(ElasticsearchEnrichmentJob)
            .where(ElasticsearchEnrichmentJob.binding_id.in_(binding_ids))
            .order_by(
                ElasticsearchEnrichmentJob.binding_id,
                ElasticsearchEnrichmentJob.created_at.desc(),
                ElasticsearchEnrichmentJob.id.desc(),
            )
        )
    )
    latest: dict[int, ElasticsearchEnrichmentJob] = {}
    for job in jobs:
        latest.setdefault(job.binding_id, job)
    return latest


def _binding_state(
    *,
    session: Session,
    binding: ElasticsearchBinding,
    latest_job: ElasticsearchEnrichmentJob | None,
) -> SnapshotBindingState:
    active_entries = alias_entries_from_snapshot(binding.runtime_snapshot_json)
    current_entries = active_runtime_alias_entries(session, binding.profile)
    diff = _snapshot_diff(
        active_entries=active_entries,
        current_entries=current_entries,
        active_checksum=_snapshot_checksum(binding.runtime_snapshot_json),
        current_checksum=_current_snapshot_checksum(session, binding),
    )
    status = _binding_snapshot_status(binding, latest_job, diff)
    return SnapshotBindingState(
        id=binding.id,
        name=binding.name,
        profile_name=binding.profile.name,
        index_name=binding.index_name,
        filter_field=binding.filter_field,
        filter_value=binding.filter_value,
        is_enabled=binding.is_enabled,
        status=status,
        active_snapshot_version=binding.last_successful_snapshot_version,
        pending_snapshot_version=binding.pending_snapshot_version,
        last_successful_snapshot_at=binding.last_successful_snapshot_at,
        last_successful_job_id=binding.last_successful_job_id,
        latest_job_id=latest_job.id if latest_job else None,
        latest_job_status=latest_job.status if latest_job else None,
        latest_job_error=latest_job.error_message if latest_job else None,
        rollback_available=_rollback_available(latest_job),
        snapshot_aliases_total=len(active_entries),
        current_aliases_total=len(current_entries),
        diff=diff,
        updated_at=binding.updated_at,
    )


def _binding_snapshot_status(
    binding: ElasticsearchBinding,
    latest_job: ElasticsearchEnrichmentJob | None,
    diff: SnapshotDiffSummary,
) -> str:
    if not binding.is_enabled:
        return "disabled"
    if latest_job and latest_job.status in _RUNNING_JOB_STATUSES:
        return "updating"
    if (
        latest_job
        and latest_job.status == "failed"
        and not binding.last_successful_snapshot_version
    ):
        return "failed"
    if not binding.last_successful_snapshot_version:
        return "never_enriched"
    if binding.pending_snapshot_version or diff.changed:
        return "stale"
    if latest_job and latest_job.status == "failed":
        return "failed"
    return "ready"


def _snapshot_diff(
    *,
    active_entries: list[RuntimeAliasEntry],
    current_entries: list[RuntimeAliasEntry],
    active_checksum: str | None,
    current_checksum: str | None,
) -> SnapshotDiffSummary:
    active_by_alias = {entry.normalized_alias: entry for entry in active_entries}
    current_by_alias = {entry.normalized_alias: entry for entry in current_entries}
    active_aliases = set(active_by_alias)
    current_aliases = set(current_by_alias)
    changed_aliases = 0
    for alias in active_aliases & current_aliases:
        active = active_by_alias[alias]
        current = current_by_alias[alias]
        if (
            active.normalized_canonical != current.normalized_canonical
            or active.slot != current.slot
            or active.confidence != current.confidence
        ):
            changed_aliases += 1

    added_aliases = len(current_aliases - active_aliases)
    removed_aliases = len(active_aliases - current_aliases)
    checksum_changed = bool(
        active_checksum and current_checksum and active_checksum != current_checksum
    )
    changed = bool(
        added_aliases or removed_aliases or changed_aliases or checksum_changed
    )
    return SnapshotDiffSummary(
        active_checksum=active_checksum,
        current_checksum=current_checksum,
        active_aliases=len(active_entries),
        current_aliases=len(current_entries),
        added_aliases=added_aliases,
        removed_aliases=removed_aliases,
        changed_aliases=changed_aliases,
        changed=changed,
    )


def _current_snapshot_checksum(
    session: Session, binding: ElasticsearchBinding
) -> str | None:
    try:
        payload = build_runtime_snapshot_payload(session, binding.profile)
    except Exception:
        return None
    checksum = payload.get("checksum")
    return str(checksum) if checksum else None


def _history_item(job: ElasticsearchEnrichmentJob) -> SnapshotHistoryItem:
    snapshot_json = job.snapshot_json if isinstance(job.snapshot_json, dict) else None
    return SnapshotHistoryItem(
        job_id=job.id,
        binding_id=job.binding_id,
        binding_name=job.binding.name,
        profile_name=job.profile.name,
        status=job.status,
        snapshot_version=job.snapshot_version,
        previous_snapshot_version=job.previous_snapshot_version,
        checksum=_snapshot_checksum(snapshot_json),
        alias_entries_total=len(alias_entries_from_snapshot(snapshot_json)),
        documents_seen=job.documents_seen,
        documents_enriched=job.documents_enriched,
        documents_failed=job.documents_failed,
        target_index=job.target_index,
        alias_name=job.alias_name,
        rollback_available=_rollback_available(job),
        error_message=job.error_message,
        created_at=job.created_at,
        finished_at=job.finished_at,
    )


def _snapshot_checksum(snapshot_json: dict | None) -> str | None:
    if not isinstance(snapshot_json, dict):
        return None
    checksum = snapshot_json.get("checksum")
    return str(checksum) if checksum else None


def _rollback_available(job: ElasticsearchEnrichmentJob | None) -> bool:
    if job is None or job.status != "succeeded":
        return False
    result_json = job.result_json if isinstance(job.result_json, dict) else {}
    rollout = result_json.get("rollout") if isinstance(result_json, dict) else None
    if not isinstance(rollout, dict):
        return False
    return bool(rollout.get("rollback_available"))
