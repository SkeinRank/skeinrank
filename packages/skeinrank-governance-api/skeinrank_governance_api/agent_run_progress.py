"""Agent run progress snapshots computed from persisted tracking rows."""

from __future__ import annotations

from typing import Any

from skeinrank_governance.models import (
    AgentCandidateObservation,
    AgentDocumentVisit,
    AgentEvidenceWindow,
    AgentLlmReview,
    AgentProposalAttempt,
    AgentRun,
)
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .agent_run_registry import FINAL_AGENT_RUN_STATUSES, get_agent_run_by_run_id

AGENT_RUN_PROGRESS_SCHEMA_VERSION = "skeinrank.agent_run_progress.v1"

_EXPECTED_DOCUMENTS_KEYS = (
    "expected_documents_total",
    "documents_total",
    "total_documents",
    "target_documents",
    "max_documents",
    "max_docs",
)
_PHASE_KEYS = ("phase", "current_phase", "stage")


class AgentRunProgressError(ValueError):
    """Raised when an agent run progress request is invalid."""


def get_agent_run_progress(session: Session, run_id: str) -> dict[str, Any]:
    """Return an operator-facing progress snapshot for one agent run.

    The snapshot is computed from the existing agent tracking tables and the
    optional ``summary_json`` hints stored on ``agent_runs``. It intentionally
    does not mutate run state, submit proposals, or call external services.
    """

    agent_run = get_agent_run_by_run_id(session, run_id)
    if agent_run is None:
        raise AgentRunProgressError(f"Agent run not found: {run_id}")

    summary = dict(agent_run.summary_json or {})
    expected_documents_total = _extract_expected_documents_total(summary)

    document_statuses = _counts_by_status(
        session,
        AgentDocumentVisit,
        AgentDocumentVisit.visit_status,
        agent_run.id,
    )
    document_total = _count_rows(session, AgentDocumentVisit, agent_run.id)
    should_scan_total = _count_boolean_rows(
        session,
        AgentDocumentVisit,
        AgentDocumentVisit.should_scan,
        True,
        agent_run.id,
    )
    should_skip_total = _count_boolean_rows(
        session,
        AgentDocumentVisit,
        AgentDocumentVisit.should_scan,
        False,
        agent_run.id,
    )
    evidence_windows_reported = _sum_int_column(
        session,
        AgentDocumentVisit,
        AgentDocumentVisit.evidence_windows_found,
        agent_run.id,
    )

    candidate_statuses = _counts_by_status(
        session,
        AgentCandidateObservation,
        AgentCandidateObservation.observation_status,
        agent_run.id,
    )
    candidate_total = _count_rows(session, AgentCandidateObservation, agent_run.id)

    evidence_window_total = _count_rows(session, AgentEvidenceWindow, agent_run.id)

    review_statuses = _counts_by_status(
        session,
        AgentLlmReview,
        AgentLlmReview.review_status,
        agent_run.id,
    )
    review_total = _count_rows(session, AgentLlmReview, agent_run.id)

    proposal_statuses = _counts_by_status(
        session,
        AgentProposalAttempt,
        AgentProposalAttempt.attempt_status,
        agent_run.id,
    )
    proposal_total = _count_rows(session, AgentProposalAttempt, agent_run.id)
    proposals_submitted = _count_boolean_rows(
        session,
        AgentProposalAttempt,
        AgentProposalAttempt.submitted,
        True,
        agent_run.id,
    )

    document_errors = document_statuses.get("error", 0)
    candidate_errors = candidate_statuses.get("error", 0)
    llm_review_errors = review_statuses.get("error", 0)
    proposal_errors = proposal_statuses.get("error", 0)
    total_errors = (
        document_errors
        + candidate_errors
        + llm_review_errors
        + proposal_errors
        + (1 if agent_run.error_message else 0)
    )

    progress_numerator = document_total
    progress_denominator = expected_documents_total
    pending_documents = (
        max(0, expected_documents_total - document_total)
        if expected_documents_total is not None
        else None
    )

    return {
        "schema_version": AGENT_RUN_PROGRESS_SCHEMA_VERSION,
        "run_id": agent_run.run_id,
        "status": agent_run.status,
        "phase": _infer_phase(agent_run, summary),
        "is_terminal": agent_run.status in FINAL_AGENT_RUN_STATUSES,
        "percent_complete": _percent_complete(
            status=agent_run.status,
            numerator=progress_numerator,
            denominator=progress_denominator,
        ),
        "documents": {
            "total_expected": expected_documents_total,
            "visited": document_total,
            "processed": document_total,
            "pending": pending_documents,
            "scanned": should_scan_total,
            "skipped": should_skip_total + document_statuses.get("skipped", 0),
            "unchanged": document_statuses.get("unchanged_seen", 0),
            "changed": document_statuses.get("content_changed", 0)
            + document_statuses.get("context_changed", 0),
            "errors": document_errors,
            "by_status": document_statuses,
        },
        "candidates": {
            "observed": candidate_total,
            "queued_for_review": candidate_statuses.get("queued_for_review", 0),
            "reviewed": candidate_statuses.get("reviewed", 0),
            "rejected": candidate_statuses.get("rejected", 0),
            "needs_evidence": candidate_statuses.get("needs_evidence", 0),
            "errors": candidate_errors,
            "by_status": candidate_statuses,
        },
        "evidence": {
            "windows": evidence_window_total,
            "windows_reported_by_visits": evidence_windows_reported,
        },
        "llm_reviews": {
            "total": review_total,
            "proposed": review_statuses.get("proposed", 0),
            "rejected": review_statuses.get("rejected", 0),
            "needs_evidence": review_statuses.get("needs_evidence", 0),
            "errors": llm_review_errors,
            "by_status": review_statuses,
        },
        "proposals": {
            "total": proposal_total,
            "validation_passed": proposal_statuses.get("validation_passed", 0),
            "validation_warning": proposal_statuses.get("validation_warning", 0),
            "validation_blocked": proposal_statuses.get("validation_blocked", 0),
            "submitted": proposals_submitted,
            "created": proposal_statuses.get("created", 0),
            "idempotent_existing_alias": proposal_statuses.get(
                "idempotent_existing_alias", 0
            ),
            "manual_review_required": proposal_statuses.get(
                "manual_review_required", 0
            ),
            "errors": proposal_errors,
            "by_status": proposal_statuses,
        },
        "errors": {
            "total": total_errors,
            "run_error": bool(agent_run.error_message),
            "document_errors": document_errors,
            "candidate_errors": candidate_errors,
            "llm_review_errors": llm_review_errors,
            "proposal_errors": proposal_errors,
            "message": agent_run.error_message,
        },
        "artifacts": {
            "artifacts_uri": agent_run.artifacts_uri,
            "report_uri": agent_run.report_uri,
        },
        "timestamps": {
            "created_at": agent_run.created_at,
            "started_at": agent_run.started_at,
            "finished_at": agent_run.finished_at,
            "updated_at": agent_run.updated_at,
        },
    }


def _count_rows(session: Session, model: type[Any], agent_run_id: int) -> int:
    value = session.scalar(
        select(func.count())
        .select_from(model)
        .where(model.agent_run_id == agent_run_id)
    )
    return int(value or 0)


def _count_boolean_rows(
    session: Session,
    model: type[Any],
    column: Any,
    expected: bool,
    agent_run_id: int,
) -> int:
    value = session.scalar(
        select(func.count())
        .select_from(model)
        .where(model.agent_run_id == agent_run_id, column.is_(expected))
    )
    return int(value or 0)


def _sum_int_column(
    session: Session,
    model: type[Any],
    column: Any,
    agent_run_id: int,
) -> int:
    value = session.scalar(
        select(func.coalesce(func.sum(column), 0))
        .select_from(model)
        .where(model.agent_run_id == agent_run_id)
    )
    return int(value or 0)


def _counts_by_status(
    session: Session,
    model: type[Any],
    status_column: Any,
    agent_run_id: int,
) -> dict[str, int]:
    rows = session.execute(
        select(status_column, func.count())
        .select_from(model)
        .where(model.agent_run_id == agent_run_id)
        .group_by(status_column)
    ).all()
    return {str(status): int(count) for status, count in rows}


def _extract_expected_documents_total(summary: dict[str, Any]) -> int | None:
    for key in _EXPECTED_DOCUMENTS_KEYS:
        value = summary.get(key)
        parsed = _parse_positive_int(value)
        if parsed is not None:
            return parsed
    progress = summary.get("progress")
    if isinstance(progress, dict):
        for key in _EXPECTED_DOCUMENTS_KEYS:
            parsed = _parse_positive_int(progress.get(key))
            if parsed is not None:
                return parsed
    return None


def _parse_positive_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value >= 0:
        return value
    if isinstance(value, float) and value >= 0 and value.is_integer():
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _infer_phase(agent_run: AgentRun, summary: dict[str, Any]) -> str:
    for key in _PHASE_KEYS:
        value = summary.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    progress = summary.get("progress")
    if isinstance(progress, dict):
        for key in _PHASE_KEYS:
            value = progress.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    if agent_run.status == "queued":
        return "queued"
    if agent_run.status == "running":
        return "running"
    if agent_run.status == "needs_review":
        return "needs_review"
    return agent_run.status


def _percent_complete(
    *, status: str, numerator: int, denominator: int | None
) -> float | None:
    if denominator is not None:
        if denominator == 0:
            return 1.0
        return round(min(1.0, max(0.0, numerator / denominator)), 4)
    if status in FINAL_AGENT_RUN_STATUSES:
        return 1.0
    return None
