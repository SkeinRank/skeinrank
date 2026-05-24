"""DB-backed agent candidate observation and evidence window helpers."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from skeinrank_governance.models import (
    AGENT_CANDIDATE_OBSERVATION_STATUSES,
    AgentCandidateObservation,
    AgentDocumentVisit,
    AgentEvidenceWindow,
    normalize_value,
)
from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from .agent_run_registry import get_agent_run_by_run_id


class AgentCandidateObservationError(ValueError):
    """Raised when a candidate observation command is invalid."""


def record_candidate_observation(
    session: Session,
    *,
    run_id: str,
    candidate_alias: str,
    document_visit_id: int | None = None,
    possible_canonical: str | None = None,
    slot: str | None = None,
    observation_status: str = "discovered",
    discovery_score: float = 0.0,
    weighted_count: float = 0.0,
    document_frequency: int = 0,
    discovery_reasons: list[str] | None = None,
    canonical_hint: dict[str, Any] | None = None,
    candidate_pack: dict[str, Any] | None = None,
    metadata_json: dict[str, Any] | None = None,
    evidence_windows: list[dict[str, Any]] | None = None,
    error_message: str | None = None,
) -> AgentCandidateObservation:
    """Create one candidate observation and optional evidence windows."""

    agent_run = get_agent_run_by_run_id(session, run_id)
    if agent_run is None:
        raise AgentCandidateObservationError(f"Agent run not found: {run_id}")
    normalized_alias = normalize_value(candidate_alias)
    if not normalized_alias:
        raise AgentCandidateObservationError("candidate_alias must not be empty.")
    document_visit = _resolve_document_visit(
        session,
        document_visit_id=document_visit_id,
        agent_run_id=agent_run.id,
    )
    normalized_status = _validate_observation_status(observation_status)
    normalized_canonical = (
        normalize_value(possible_canonical) if possible_canonical else None
    )
    observation = AgentCandidateObservation(
        agent_run=agent_run,
        document_visit=document_visit,
        run_id=agent_run.run_id,
        profile_id=agent_run.profile_id,
        binding_id=agent_run.binding_id,
        candidate_alias=candidate_alias.strip(),
        normalized_alias=normalized_alias,
        possible_canonical=possible_canonical.strip() if possible_canonical else None,
        normalized_canonical=normalized_canonical,
        slot=slot.strip().upper() if slot else None,
        observation_status=normalized_status,
        discovery_score=max(0.0, float(discovery_score)),
        weighted_count=max(0.0, float(weighted_count)),
        document_frequency=max(0, int(document_frequency)),
        discovery_reasons_json=discovery_reasons or [],
        canonical_hint_json=canonical_hint or {},
        candidate_pack_json=candidate_pack or {},
        metadata_json=metadata_json or {},
        error_message=error_message,
    )
    session.add(observation)
    persisted_windows: list[AgentEvidenceWindow] = []
    for window_payload in evidence_windows or []:
        evidence_window = _build_evidence_window(
            agent_run=agent_run,
            observation=observation,
            document_visit=document_visit,
            payload=window_payload,
        )
        persisted_windows.append(evidence_window)
        session.add(evidence_window)
    observation.evidence_windows_found = len(persisted_windows)
    return observation


def list_candidate_observations(
    session: Session,
    *,
    run_id: str,
    observation_status: str | None = None,
    candidate_alias: str | None = None,
    limit: int = 100,
) -> list[AgentCandidateObservation]:
    """List candidate observations for one run."""

    agent_run = get_agent_run_by_run_id(session, run_id)
    if agent_run is None:
        raise AgentCandidateObservationError(f"Agent run not found: {run_id}")
    statement: Select[tuple[AgentCandidateObservation]] = select(
        AgentCandidateObservation
    ).where(AgentCandidateObservation.agent_run_id == agent_run.id)
    if observation_status is not None:
        statement = statement.where(
            AgentCandidateObservation.observation_status
            == _validate_observation_status(observation_status)
        )
    if candidate_alias:
        statement = statement.where(
            AgentCandidateObservation.normalized_alias
            == normalize_value(candidate_alias)
        )
    statement = statement.order_by(
        AgentCandidateObservation.discovery_score.desc(),
        AgentCandidateObservation.created_at.desc(),
        AgentCandidateObservation.id.desc(),
    ).limit(max(1, min(limit, 500)))
    return list(session.scalars(statement))


def list_evidence_windows(
    session: Session,
    *,
    run_id: str,
    candidate_observation_id: int | None = None,
    source_id: str | None = None,
    limit: int = 100,
) -> list[AgentEvidenceWindow]:
    """List persisted evidence windows for one run."""

    agent_run = get_agent_run_by_run_id(session, run_id)
    if agent_run is None:
        raise AgentCandidateObservationError(f"Agent run not found: {run_id}")
    statement: Select[tuple[AgentEvidenceWindow]] = select(AgentEvidenceWindow).where(
        AgentEvidenceWindow.agent_run_id == agent_run.id
    )
    if candidate_observation_id is not None:
        statement = statement.where(
            AgentEvidenceWindow.candidate_observation_id == candidate_observation_id
        )
    if source_id:
        statement = statement.where(AgentEvidenceWindow.source_id == source_id.strip())
    statement = statement.order_by(
        AgentEvidenceWindow.created_at.desc(), AgentEvidenceWindow.id.desc()
    ).limit(max(1, min(limit, 500)))
    return list(session.scalars(statement))


def _build_evidence_window(
    *,
    agent_run,
    observation: AgentCandidateObservation,
    document_visit: AgentDocumentVisit | None,
    payload: dict[str, Any],
) -> AgentEvidenceWindow:
    text = str(payload.get("text") or "").strip()
    if not text:
        raise AgentCandidateObservationError("evidence window text must not be empty.")
    source_id = str(
        payload.get("source_id")
        or (document_visit.source_id if document_visit is not None else "unknown")
    ).strip()
    if not source_id:
        raise AgentCandidateObservationError(
            "evidence window source_id must not be empty."
        )
    source_type = str(payload.get("source_type") or "evidence").strip() or "evidence"
    field = str(payload.get("field") or "text").strip() or "text"
    metadata = payload.get("metadata") or {}
    start_char = payload.get("start_char")
    end_char = payload.get("end_char")
    evidence_hash = payload.get("evidence_hash") or compute_evidence_hash(
        observation.normalized_alias,
        source_id,
        field,
        text,
        start_char=start_char,
        end_char=end_char,
    )
    return AgentEvidenceWindow(
        agent_run=agent_run,
        candidate_observation=observation,
        document_visit=document_visit,
        run_id=agent_run.run_id,
        profile_id=agent_run.profile_id,
        binding_id=agent_run.binding_id,
        candidate_alias=observation.candidate_alias,
        normalized_alias=observation.normalized_alias,
        source_id=source_id,
        source_type=source_type,
        field=field,
        start_char=start_char,
        end_char=end_char,
        text=text,
        evidence_hash=str(evidence_hash).strip().lower(),
        metadata_json=metadata if isinstance(metadata, dict) else {"value": metadata},
    )


def compute_evidence_hash(
    normalized_alias: str,
    source_id: str,
    field: str,
    text: str,
    *,
    start_char: int | None = None,
    end_char: int | None = None,
) -> str:
    """Return a stable hash for evidence-window idempotency."""

    payload = {
        "alias": normalized_alias,
        "source_id": source_id,
        "field": field,
        "start_char": start_char,
        "end_char": end_char,
        "text": text,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _resolve_document_visit(
    session: Session,
    *,
    document_visit_id: int | None,
    agent_run_id: int,
) -> AgentDocumentVisit | None:
    if document_visit_id is None:
        return None
    visit = session.get(AgentDocumentVisit, document_visit_id)
    if visit is None:
        raise AgentCandidateObservationError(
            f"Document visit not found: {document_visit_id}"
        )
    if visit.agent_run_id != agent_run_id:
        raise AgentCandidateObservationError(
            "Document visit belongs to a different agent run."
        )
    return visit


def _validate_observation_status(status: str) -> str:
    normalized = status.strip().lower()
    if normalized not in AGENT_CANDIDATE_OBSERVATION_STATUSES:
        raise AgentCandidateObservationError(
            "Invalid candidate observation status "
            f"{status!r}. Expected one of "
            f"{list(AGENT_CANDIDATE_OBSERVATION_STATUSES)!r}."
        )
    return normalized
