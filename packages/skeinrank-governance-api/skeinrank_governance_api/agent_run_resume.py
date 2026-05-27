"""Read-only resume/retry planning for persisted agent runs."""

from __future__ import annotations

from collections import Counter
from typing import Any

from skeinrank_governance.models import (
    AgentCandidateObservation,
    AgentDocumentVisit,
    AgentLlmReview,
    AgentProposalAttempt,
    AgentRun,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from .agent_run_registry import FINAL_AGENT_RUN_STATUSES, get_agent_run_by_run_id

AGENT_RUN_RESUME_PLAN_SCHEMA_VERSION = "skeinrank.agent_run_resume_plan.v1"

_DOCUMENT_RESUME_STATUSES = {"new_document", "content_changed", "context_changed"}
_DOCUMENT_SKIPPED_STATUSES = {"skipped", "unchanged_seen"}
_ERROR_STATUSES = {"error"}
_SUMMARY_SOURCE_ID_KEYS = (
    "source_ids",
    "document_source_ids",
    "target_source_ids",
    "documents",
    "sources",
)


class AgentRunResumePlanError(ValueError):
    """Raised when a resume-plan request cannot be built."""


def build_agent_run_resume_plan(
    session: Session,
    run_id: str,
    *,
    batch_limit: int = 100,
    retry_errors: bool = True,
    retry_skipped: bool = False,
    force_rescan: bool = False,
    source_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Return a bounded read-only work plan for resuming an agent run.

    The planner only reads persisted run tracking rows. It does not update run
    status, retry external calls, submit proposals, or publish snapshots. The
    returned ``work_items`` can be used by an operator or future worker to decide
    which documents/candidates/reviews/proposal attempts are safe to process next.
    """

    agent_run = get_agent_run_by_run_id(session, run_id)
    if agent_run is None:
        raise AgentRunResumePlanError(f"Agent run not found: {run_id}")

    normalized_source_ids = _normalize_source_ids(source_ids)
    summary_source_ids = _source_ids_from_summary(agent_run.summary_json or {})
    effective_source_ids = normalized_source_ids or summary_source_ids
    source_filter = set(effective_source_ids) if effective_source_ids else None
    limit = max(1, min(int(batch_limit), 500))

    all_items = _build_all_work_items(
        session,
        agent_run=agent_run,
        source_filter=source_filter,
        retry_errors=retry_errors,
        retry_skipped=retry_skipped,
        force_rescan=force_rescan,
    )
    selected_items = all_items[:limit]
    selected_by_kind = Counter(item["kind"] for item in selected_items)
    all_by_kind = Counter(item["kind"] for item in all_items)

    is_terminal = agent_run.status in FINAL_AGENT_RUN_STATUSES
    has_errors = any(
        item["kind"].startswith("retry_") and item["kind"] != "retry_skipped_document"
        for item in all_items
    )
    can_resume = bool(all_items) and not (
        agent_run.status == "succeeded" and not force_rescan and not has_errors
    )

    notes: list[str] = []
    if is_terminal and all_items:
        notes.append(
            "run is terminal; plan is read-only and should be reviewed before "
            "starting a new worker execution"
        )
    if source_filter is not None:
        notes.append("plan is scoped to requested or summary-provided source_ids")
    if force_rescan:
        notes.append(
            "force_rescan requested; document work items bypass unchanged state"
        )
    if len(all_items) > limit:
        notes.append("batch_limit truncated the next executable batch")

    return {
        "schema_version": AGENT_RUN_RESUME_PLAN_SCHEMA_VERSION,
        "run_id": agent_run.run_id,
        "status": agent_run.status,
        "is_terminal": is_terminal,
        "can_resume": can_resume,
        "options": {
            "batch_limit": limit,
            "retry_errors": retry_errors,
            "retry_skipped": retry_skipped,
            "force_rescan": force_rescan,
            "source_ids": effective_source_ids,
        },
        "limits": {
            "batch_limit": limit,
            "requested_source_ids": len(effective_source_ids)
            if effective_source_ids is not None
            else None,
            "available_work_items": len(all_items),
            "selected_work_items": len(selected_items),
            "has_more": len(all_items) > limit,
        },
        "summary": {
            "by_kind": dict(sorted(all_by_kind.items())),
            "selected_by_kind": dict(sorted(selected_by_kind.items())),
            "notes": notes,
        },
        "work_items": selected_items,
    }


def _build_all_work_items(
    session: Session,
    *,
    agent_run: AgentRun,
    source_filter: set[str] | None,
    retry_errors: bool,
    retry_skipped: bool,
    force_rescan: bool,
) -> list[dict[str, Any]]:
    work_items: list[dict[str, Any]] = []
    entity_keys: set[str] = set()

    visits = list(
        session.scalars(
            select(AgentDocumentVisit)
            .where(AgentDocumentVisit.agent_run_id == agent_run.id)
            .order_by(AgentDocumentVisit.id.asc())
        )
    )
    visited_source_ids = {visit.source_id for visit in visits}

    if source_filter is not None:
        for source_id in sorted(source_filter - visited_source_ids):
            _add_item(
                work_items,
                entity_keys,
                {
                    "kind": "resume_unfinished_document",
                    "reason": "requested_source_id_not_visited",
                    "priority": 30,
                    "tracking_table": None,
                    "tracking_id": None,
                    "source_id": source_id,
                    "candidate_alias": None,
                    "normalized_alias": None,
                    "status": None,
                    "error_message": None,
                    "metadata": {},
                },
            )

    for visit in visits:
        if source_filter is not None and visit.source_id not in source_filter:
            continue
        item = _document_item(
            visit,
            retry_errors=retry_errors,
            retry_skipped=retry_skipped,
            force_rescan=force_rescan,
        )
        if item is not None:
            _add_item(work_items, entity_keys, item)

    if retry_errors:
        for observation in session.scalars(
            select(AgentCandidateObservation)
            .where(AgentCandidateObservation.agent_run_id == agent_run.id)
            .order_by(AgentCandidateObservation.id.asc())
        ):
            if not _is_error_row(
                observation.observation_status, observation.error_message
            ):
                continue
            if not _matches_source_filter(observation, source_filter):
                continue
            _add_item(
                work_items,
                entity_keys,
                _alias_item(
                    kind="retry_candidate_error",
                    reason="candidate_observation_error",
                    priority=40,
                    tracking_table="agent_candidate_observations",
                    tracking_id=observation.id,
                    candidate_alias=observation.candidate_alias,
                    normalized_alias=observation.normalized_alias,
                    status=observation.observation_status,
                    error_message=observation.error_message,
                    source_id=_source_id_for_alias_row(observation),
                    metadata={
                        "possible_canonical": observation.possible_canonical,
                        "slot": observation.slot,
                    },
                ),
            )

        for review in session.scalars(
            select(AgentLlmReview)
            .where(AgentLlmReview.agent_run_id == agent_run.id)
            .order_by(AgentLlmReview.id.asc())
        ):
            if not _is_error_row(review.review_status, review.error_message):
                continue
            if not _matches_source_filter(review, source_filter):
                continue
            _add_item(
                work_items,
                entity_keys,
                _alias_item(
                    kind="retry_llm_review_error",
                    reason="llm_review_error",
                    priority=50,
                    tracking_table="agent_llm_reviews",
                    tracking_id=review.id,
                    candidate_alias=review.candidate_alias,
                    normalized_alias=review.normalized_alias,
                    status=review.review_status,
                    error_message=review.error_message,
                    source_id=_source_id_for_alias_row(review),
                    metadata={
                        "possible_canonical": review.possible_canonical,
                        "slot": review.slot,
                        "model": review.model,
                    },
                ),
            )

        for attempt in session.scalars(
            select(AgentProposalAttempt)
            .where(AgentProposalAttempt.agent_run_id == agent_run.id)
            .order_by(AgentProposalAttempt.id.asc())
        ):
            if not _is_error_row(attempt.attempt_status, attempt.error_message):
                continue
            if not _matches_source_filter(attempt, source_filter):
                continue
            _add_item(
                work_items,
                entity_keys,
                _alias_item(
                    kind="retry_proposal_error",
                    reason="proposal_attempt_error",
                    priority=60,
                    tracking_table="agent_proposal_attempts",
                    tracking_id=attempt.id,
                    candidate_alias=attempt.alias_value,
                    normalized_alias=attempt.normalized_alias,
                    status=attempt.attempt_status,
                    error_message=attempt.error_message,
                    source_id=_source_id_for_alias_row(attempt),
                    metadata={
                        "canonical_value": attempt.canonical_value,
                        "slot": attempt.slot,
                        "idempotency_key": attempt.idempotency_key,
                    },
                ),
            )

    return sorted(
        work_items,
        key=lambda item: (
            int(item["priority"]),
            item.get("source_id") or "",
            item.get("normalized_alias") or "",
            item.get("tracking_id") or 0,
        ),
    )


def _document_item(
    visit: AgentDocumentVisit,
    *,
    retry_errors: bool,
    retry_skipped: bool,
    force_rescan: bool,
) -> dict[str, Any] | None:
    if force_rescan:
        kind = "force_rescan"
        reason = "force_rescan_requested"
        priority = 10
    elif retry_errors and _is_error_row(visit.visit_status, visit.error_message):
        kind = "retry_document_error"
        reason = "document_visit_error"
        priority = 20
    elif retry_skipped and _is_skipped_document(visit):
        kind = "retry_skipped_document"
        reason = "retry_skipped_requested"
        priority = 25
    elif visit.should_scan and visit.visit_status in _DOCUMENT_RESUME_STATUSES:
        kind = "resume_unfinished_document"
        reason = "document_marked_for_scan"
        priority = 30
    else:
        return None

    return {
        "kind": kind,
        "reason": reason,
        "priority": priority,
        "tracking_table": "agent_document_visits",
        "tracking_id": visit.id,
        "source_id": visit.source_id,
        "candidate_alias": None,
        "normalized_alias": None,
        "status": visit.visit_status,
        "error_message": visit.error_message,
        "metadata": {
            "should_scan": visit.should_scan,
            "source_type": visit.source_type,
            "index_name": visit.index_name,
            "external_document_id": visit.external_document_id,
        },
    }


def _alias_item(
    *,
    kind: str,
    reason: str,
    priority: int,
    tracking_table: str,
    tracking_id: int,
    candidate_alias: str,
    normalized_alias: str,
    status: str,
    error_message: str | None,
    source_id: str | None,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    return {
        "kind": kind,
        "reason": reason,
        "priority": priority,
        "tracking_table": tracking_table,
        "tracking_id": tracking_id,
        "source_id": source_id,
        "candidate_alias": candidate_alias,
        "normalized_alias": normalized_alias,
        "status": status,
        "error_message": error_message,
        "metadata": {
            key: value for key, value in metadata.items() if value is not None
        },
    }


def _add_item(
    items: list[dict[str, Any]],
    entity_keys: set[str],
    item: dict[str, Any],
) -> None:
    key = _entity_key(item)
    if key in entity_keys:
        return
    entity_keys.add(key)
    items.append(item)


def _entity_key(item: dict[str, Any]) -> str:
    if (
        item.get("tracking_table") == "agent_document_visits"
        or item.get("tracking_table") is None
    ):
        return f"document:{item.get('source_id') or item.get('tracking_id')}"
    return f"{item.get('tracking_table')}:{item.get('tracking_id')}"


def _is_error_row(status: str | None, error_message: str | None) -> bool:
    return status in _ERROR_STATUSES or bool(error_message)


def _is_skipped_document(visit: AgentDocumentVisit) -> bool:
    return visit.visit_status in _DOCUMENT_SKIPPED_STATUSES or not visit.should_scan


def _matches_source_filter(row: Any, source_filter: set[str] | None) -> bool:
    if source_filter is None:
        return True
    source_id = _source_id_for_alias_row(row)
    return source_id in source_filter if source_id is not None else False


def _source_id_for_alias_row(row: Any) -> str | None:
    observation = getattr(row, "candidate_observation", None)
    if isinstance(row, AgentCandidateObservation):
        observation = row
    document_visit = getattr(observation, "document_visit", None)
    if document_visit is not None:
        return document_visit.source_id
    return None


def _normalize_source_ids(source_ids: list[str] | None) -> list[str] | None:
    if source_ids is None:
        return None
    normalized: list[str] = []
    seen: set[str] = set()
    for source_id in source_ids:
        value = str(source_id).strip()
        if not value or value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return normalized or None


def _source_ids_from_summary(summary: dict[str, Any]) -> list[str] | None:
    for key in _SUMMARY_SOURCE_ID_KEYS:
        parsed = _parse_source_id_list(summary.get(key))
        if parsed is not None:
            return parsed
    progress = summary.get("progress")
    if isinstance(progress, dict):
        for key in _SUMMARY_SOURCE_ID_KEYS:
            parsed = _parse_source_id_list(progress.get(key))
            if parsed is not None:
                return parsed
    return None


def _parse_source_id_list(value: Any) -> list[str] | None:
    if not isinstance(value, list):
        return None
    source_ids: list[str] = []
    seen: set[str] = set()
    for item in value:
        if isinstance(item, str):
            raw = item
        elif isinstance(item, dict):
            raw = item.get("source_id") or item.get("id") or item.get("document_id")
        else:
            raw = None
        if raw is None:
            continue
        source_id = str(raw).strip()
        if not source_id or source_id in seen:
            continue
        seen.add(source_id)
        source_ids.append(source_id)
    return source_ids or None
