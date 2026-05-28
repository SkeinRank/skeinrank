"""Read-only diagnostics/report snapshots for persisted agent runs."""

from __future__ import annotations

from collections import Counter, defaultdict
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

from .agent_run_progress import get_agent_run_progress
from .agent_run_registry import FINAL_AGENT_RUN_STATUSES, get_agent_run_by_run_id

AGENT_RUN_REPORT_SCHEMA_VERSION = "skeinrank.agent_run_report.v1"

_ERROR_STATUSES = {"error"}
_SKIPPED_DOCUMENT_STATUSES = {"skipped", "unchanged_seen"}
_MANUAL_REVIEW_PROPOSAL_STATUSES = {
    "validation_warning",
    "validation_blocked",
    "manual_review_required",
    "error",
}
_REVIEW_ATTENTION_STATUSES = {"needs_evidence", "rejected", "error"}
_SUMMARY_USAGE_KEYS = (
    "usage",
    "llm_usage",
    "token_usage",
    "cost",
    "costs",
    "budget",
)
_COST_KEYS = (
    "estimated_cost_usd",
    "cost_usd",
    "total_cost_usd",
    "usd",
)
_PROMPT_TOKEN_KEYS = ("prompt_tokens", "input_tokens")
_COMPLETION_TOKEN_KEYS = ("completion_tokens", "output_tokens")
_TOTAL_TOKEN_KEYS = ("total_tokens", "tokens")


class AgentRunReportError(ValueError):
    """Raised when an agent run report request cannot be served."""


def get_agent_run_report(
    session: Session,
    run_id: str,
    *,
    item_limit: int = 25,
) -> dict[str, Any]:
    """Return a read-only operator report for one agent run.

    The report is computed from existing run tracking rows. It does not mutate
    run state, retry work, submit proposals, call OpenRouter/Elasticsearch, or
    publish snapshots.
    """

    agent_run = get_agent_run_by_run_id(session, run_id)
    if agent_run is None:
        raise AgentRunReportError(f"Agent run not found: {run_id}")

    limit = max(1, min(int(item_limit), 100))
    summary = dict(agent_run.summary_json or {})
    progress = get_agent_run_progress(session, run_id)

    document_rows = _document_rows(session, agent_run.id)
    candidate_rows = _candidate_rows(session, agent_run.id)
    review_rows = _review_rows(session, agent_run.id)
    proposal_rows = _proposal_rows(session, agent_run.id)

    skipped_documents = [
        _document_item(visit) for visit in document_rows if _is_skipped_document(visit)
    ][:limit]
    document_errors = [
        _document_item(visit)
        for visit in document_rows
        if _is_error(visit.visit_status, visit.error_message)
    ][:limit]
    candidate_errors = [
        _candidate_item(observation)
        for observation in candidate_rows
        if _is_error(observation.observation_status, observation.error_message)
    ][:limit]
    review_errors = [
        _review_item(review)
        for review in review_rows
        if _is_error(review.review_status, review.error_message)
    ][:limit]
    proposal_errors = [
        _proposal_item(attempt)
        for attempt in proposal_rows
        if _is_error(attempt.attempt_status, attempt.error_message)
    ][:limit]

    errors = (
        _run_error_item(agent_run)
        + document_errors
        + candidate_errors
        + review_errors
        + proposal_errors
    )[:limit]

    manual_review_items = _manual_review_items(
        candidate_rows=candidate_rows,
        review_rows=review_rows,
        proposal_rows=proposal_rows,
        limit=limit,
    )
    proposal_outcomes = _proposal_outcomes(proposal_rows)
    candidate_outcomes = _candidate_outcomes(candidate_rows, review_rows)
    usage = _usage_report(summary, review_rows)
    findings = _diagnostic_findings(
        agent_run=agent_run,
        progress=progress,
        skipped_documents=skipped_documents,
        errors=errors,
        manual_review_items=manual_review_items,
        proposal_outcomes=proposal_outcomes,
        usage=usage,
    )
    recommendations = _recommendations(
        agent_run=agent_run,
        progress=progress,
        findings=findings,
        usage=usage,
    )

    return {
        "schema_version": AGENT_RUN_REPORT_SCHEMA_VERSION,
        "run_id": agent_run.run_id,
        "status": agent_run.status,
        "phase": progress["phase"],
        "is_terminal": agent_run.status in FINAL_AGENT_RUN_STATUSES,
        "run": {
            "id": agent_run.id,
            "agent_name": agent_run.agent_name,
            "agent_version": agent_run.agent_version,
            "trigger_type": agent_run.trigger_type,
            "profile_name": agent_run.profile_name,
            "binding_id": agent_run.binding_id,
            "openrouter_model": agent_run.openrouter_model,
            "prompt_version": agent_run.prompt_version,
            "workflow_engine": agent_run.workflow_engine,
            "config_hash": agent_run.config_hash,
            "requested_by": agent_run.requested_by,
            "error_message": agent_run.error_message,
        },
        "progress": progress,
        "usage": usage,
        "diagnostics": {
            "status": _overall_status(agent_run, progress, findings),
            "findings": findings,
            "recommendations": recommendations,
        },
        "documents": {
            "skipped_samples": skipped_documents,
            "error_samples": document_errors,
        },
        "candidates": candidate_outcomes,
        "proposals": proposal_outcomes,
        "manual_review_items": manual_review_items,
        "errors": errors,
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


def _document_rows(session: Session, agent_run_id: int) -> list[AgentDocumentVisit]:
    return list(
        session.scalars(
            select(AgentDocumentVisit)
            .where(AgentDocumentVisit.agent_run_id == agent_run_id)
            .order_by(AgentDocumentVisit.id.asc())
        )
    )


def _candidate_rows(
    session: Session, agent_run_id: int
) -> list[AgentCandidateObservation]:
    return list(
        session.scalars(
            select(AgentCandidateObservation)
            .where(AgentCandidateObservation.agent_run_id == agent_run_id)
            .order_by(AgentCandidateObservation.id.asc())
        )
    )


def _review_rows(session: Session, agent_run_id: int) -> list[AgentLlmReview]:
    return list(
        session.scalars(
            select(AgentLlmReview)
            .where(AgentLlmReview.agent_run_id == agent_run_id)
            .order_by(AgentLlmReview.id.asc())
        )
    )


def _proposal_rows(session: Session, agent_run_id: int) -> list[AgentProposalAttempt]:
    return list(
        session.scalars(
            select(AgentProposalAttempt)
            .where(AgentProposalAttempt.agent_run_id == agent_run_id)
            .order_by(AgentProposalAttempt.id.asc())
        )
    )


def _run_error_item(agent_run: AgentRun) -> list[dict[str, Any]]:
    if not agent_run.error_message:
        return []
    return [
        {
            "kind": "run_error",
            "tracking_table": "agent_runs",
            "tracking_id": agent_run.id,
            "source_id": None,
            "candidate_alias": None,
            "normalized_alias": None,
            "status": agent_run.status,
            "message": agent_run.error_message,
            "metadata": {},
        }
    ]


def _document_item(visit: AgentDocumentVisit) -> dict[str, Any]:
    return {
        "kind": "document",
        "tracking_table": "agent_document_visits",
        "tracking_id": visit.id,
        "source_id": visit.source_id,
        "candidate_alias": None,
        "normalized_alias": None,
        "status": visit.visit_status,
        "message": visit.error_message,
        "metadata": {
            "should_scan": visit.should_scan,
            "source_type": visit.source_type,
            "index_name": visit.index_name,
            "external_document_id": visit.external_document_id,
            "evidence_windows_found": visit.evidence_windows_found,
        },
    }


def _candidate_item(observation: AgentCandidateObservation) -> dict[str, Any]:
    return {
        "kind": "candidate",
        "tracking_table": "agent_candidate_observations",
        "tracking_id": observation.id,
        "source_id": _source_id_for_observation(observation),
        "candidate_alias": observation.candidate_alias,
        "normalized_alias": observation.normalized_alias,
        "status": observation.observation_status,
        "message": observation.error_message,
        "metadata": {
            "possible_canonical": observation.possible_canonical,
            "slot": observation.slot,
            "discovery_score": observation.discovery_score,
            "document_frequency": observation.document_frequency,
            "evidence_windows_found": observation.evidence_windows_found,
        },
    }


def _review_item(review: AgentLlmReview) -> dict[str, Any]:
    return {
        "kind": "llm_review",
        "tracking_table": "agent_llm_reviews",
        "tracking_id": review.id,
        "source_id": _source_id_for_observation(review.candidate_observation),
        "candidate_alias": review.candidate_alias,
        "normalized_alias": review.normalized_alias,
        "status": review.review_status,
        "message": review.error_message,
        "metadata": {
            "possible_canonical": review.possible_canonical,
            "slot": review.slot,
            "action": review.action,
            "confidence": review.confidence,
            "model": review.model,
        },
    }


def _proposal_item(attempt: AgentProposalAttempt) -> dict[str, Any]:
    return {
        "kind": "proposal_attempt",
        "tracking_table": "agent_proposal_attempts",
        "tracking_id": attempt.id,
        "source_id": _source_id_for_observation(attempt.candidate_observation),
        "candidate_alias": attempt.alias_value,
        "normalized_alias": attempt.normalized_alias,
        "status": attempt.attempt_status,
        "message": attempt.error_message,
        "metadata": {
            "canonical_value": attempt.canonical_value,
            "slot": attempt.slot,
            "validation_status": attempt.validation_status,
            "validation_category": attempt.validation_category,
            "confidence": attempt.confidence,
            "submitted": attempt.submitted,
            "governance_suggestion_id": attempt.governance_suggestion_id,
            "idempotency_key": attempt.idempotency_key,
        },
    }


def _manual_review_items(
    *,
    candidate_rows: list[AgentCandidateObservation],
    review_rows: list[AgentLlmReview],
    proposal_rows: list[AgentProposalAttempt],
    limit: int,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    seen: set[str] = set()

    for attempt in proposal_rows:
        if attempt.attempt_status not in _MANUAL_REVIEW_PROPOSAL_STATUSES:
            continue
        item = _proposal_item(attempt)
        item["kind"] = "proposal_manual_review"
        _append_once(items, seen, item)

    for review in review_rows:
        if review.review_status not in _REVIEW_ATTENTION_STATUSES:
            continue
        item = _review_item(review)
        item["kind"] = "llm_review_manual_review"
        _append_once(items, seen, item)

    for observation in candidate_rows:
        if observation.observation_status not in {
            "needs_evidence",
            "rejected",
            "error",
        }:
            continue
        item = _candidate_item(observation)
        item["kind"] = "candidate_manual_review"
        _append_once(items, seen, item)

    return items[:limit]


def _append_once(
    items: list[dict[str, Any]], seen: set[str], item: dict[str, Any]
) -> None:
    key = (
        f"{item.get('tracking_table')}:{item.get('tracking_id')}:" f"{item.get('kind')}"
    )
    if key in seen:
        return
    seen.add(key)
    items.append(item)


def _candidate_outcomes(
    candidate_rows: list[AgentCandidateObservation], review_rows: list[AgentLlmReview]
) -> dict[str, Any]:
    candidate_statuses = Counter(row.observation_status for row in candidate_rows)
    review_statuses = Counter(row.review_status for row in review_rows)
    return {
        "observed": len(candidate_rows),
        "by_observation_status": dict(sorted(candidate_statuses.items())),
        "by_review_status": dict(sorted(review_statuses.items())),
        "needs_evidence": candidate_statuses.get("needs_evidence", 0)
        + review_statuses.get("needs_evidence", 0),
        "rejected": candidate_statuses.get("rejected", 0)
        + review_statuses.get("rejected", 0),
        "errors": candidate_statuses.get("error", 0) + review_statuses.get("error", 0),
    }


def _proposal_outcomes(proposal_rows: list[AgentProposalAttempt]) -> dict[str, Any]:
    statuses = Counter(row.attempt_status for row in proposal_rows)
    categories = Counter(
        row.validation_category for row in proposal_rows if row.validation_category
    )
    submitted = sum(1 for row in proposal_rows if row.submitted)
    blocked = statuses.get("validation_blocked", 0)
    warnings = statuses.get("validation_warning", 0)
    manual = statuses.get("manual_review_required", 0)
    return {
        "total": len(proposal_rows),
        "submitted": submitted,
        "blocked": blocked,
        "warnings": warnings,
        "manual_review_required": manual,
        "errors": statuses.get("error", 0),
        "by_attempt_status": dict(sorted(statuses.items())),
        "by_validation_category": dict(sorted(categories.items())),
    }


def _usage_report(
    summary: dict[str, Any], review_rows: list[AgentLlmReview]
) -> dict[str, Any]:
    prompt_tokens = 0
    completion_tokens = 0
    total_tokens = 0
    review_cost_values: list[float] = []
    by_model: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "llm_reviews": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "estimated_cost_usd": None,
        }
    )

    for review in review_rows:
        usage = _flatten_usage(review.usage_json or {})
        prompt = _first_number(usage, _PROMPT_TOKEN_KEYS) or 0
        completion = _first_number(usage, _COMPLETION_TOKEN_KEYS) or 0
        total = _first_number(usage, _TOTAL_TOKEN_KEYS) or prompt + completion
        cost = _first_number(usage, _COST_KEYS)
        if cost is not None:
            review_cost_values.append(cost)

        model_key = review.model or "unknown"
        model_usage = by_model[model_key]
        model_usage["llm_reviews"] += 1
        model_usage["prompt_tokens"] += int(prompt)
        model_usage["completion_tokens"] += int(completion)
        model_usage["total_tokens"] += int(total)
        if cost is not None:
            current_cost = model_usage["estimated_cost_usd"] or 0.0
            model_usage["estimated_cost_usd"] = round(current_cost + cost, 6)

        prompt_tokens += int(prompt)
        completion_tokens += int(completion)
        total_tokens += int(total)

    summary_usage = _summary_usage(summary)
    summary_prompt_tokens = int(summary_usage.get("prompt_tokens") or 0)
    summary_completion_tokens = int(summary_usage.get("completion_tokens") or 0)
    summary_total_tokens = int(summary_usage.get("total_tokens") or 0)
    if summary_prompt_tokens or summary_completion_tokens or summary_total_tokens:
        prompt_tokens = summary_prompt_tokens or prompt_tokens
        completion_tokens = summary_completion_tokens or completion_tokens
        total_tokens = (
            summary_total_tokens
            or summary_prompt_tokens + summary_completion_tokens
            or total_tokens
        )

    summary_cost = summary_usage.get("estimated_cost_usd")
    estimated_cost = (
        round(float(summary_cost), 6)
        if summary_cost is not None
        else round(sum(review_cost_values), 6)
        if review_cost_values
        else None
    )
    budget_limit = _budget_limit(summary)
    return {
        "llm_reviews": len(review_rows),
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "estimated_cost_usd": estimated_cost,
        "budget_limit_usd": budget_limit,
        "budget_exceeded": (
            estimated_cost > budget_limit
            if estimated_cost is not None and budget_limit is not None
            else False
        ),
        "by_model": dict(sorted(by_model.items())),
    }


def _summary_usage(summary: dict[str, Any]) -> dict[str, float | int | None]:
    usage: dict[str, Any] = {}
    for key in _SUMMARY_USAGE_KEYS:
        value = summary.get(key)
        if isinstance(value, dict):
            usage.update(_flatten_usage(value))
    usage.update(_flatten_usage(summary))
    prompt = _first_number(usage, _PROMPT_TOKEN_KEYS) or 0
    completion = _first_number(usage, _COMPLETION_TOKEN_KEYS) or 0
    total = _first_number(usage, _TOTAL_TOKEN_KEYS) or 0
    cost = _first_number(usage, _COST_KEYS)
    return {
        "prompt_tokens": int(prompt),
        "completion_tokens": int(completion),
        "total_tokens": int(total),
        "estimated_cost_usd": cost,
    }


def _budget_limit(summary: dict[str, Any]) -> float | None:
    flat = _flatten_usage(summary)
    return _first_number(
        flat,
        (
            "budget_limit_usd",
            "max_cost_usd",
            "cost_limit_usd",
            "openrouter_budget_usd",
        ),
    )


def _flatten_usage(value: Any) -> dict[str, Any]:
    flat: dict[str, Any] = {}
    if not isinstance(value, dict):
        return flat
    for key, item in value.items():
        if isinstance(item, dict):
            nested = _flatten_usage(item)
            for nested_key, nested_value in nested.items():
                flat.setdefault(nested_key, nested_value)
        else:
            flat[str(key)] = item
    return flat


def _first_number(source: dict[str, Any], keys: tuple[str, ...]) -> float | None:
    for key in keys:
        value = source.get(key)
        parsed = _number(value)
        if parsed is not None:
            return parsed
    return None


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _diagnostic_findings(
    *,
    agent_run: AgentRun,
    progress: dict[str, Any],
    skipped_documents: list[dict[str, Any]],
    errors: list[dict[str, Any]],
    manual_review_items: list[dict[str, Any]],
    proposal_outcomes: dict[str, Any],
    usage: dict[str, Any],
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    error_total = int(progress["errors"]["total"])
    if agent_run.status == "failed" or error_total > 0:
        findings.append(
            {
                "severity": "error",
                "code": "agent_run_errors_present",
                "message": "Agent run has recorded errors.",
                "details": {"total_errors": error_total, "sampled_errors": len(errors)},
            }
        )
    if skipped_documents:
        findings.append(
            {
                "severity": "info",
                "code": "documents_skipped_or_unchanged",
                "message": "Some documents were skipped or detected as unchanged.",
                "details": {"sampled_documents": len(skipped_documents)},
            }
        )
    if manual_review_items:
        findings.append(
            {
                "severity": "warning",
                "code": "manual_review_required",
                "message": (
                    "Some candidates, reviews, or proposal attempts require "
                    "manual review."
                ),
                "details": {"sampled_items": len(manual_review_items)},
            }
        )
    if proposal_outcomes["blocked"]:
        findings.append(
            {
                "severity": "warning",
                "code": "proposal_validation_blocked",
                "message": "Some proposal attempts were blocked by validation.",
                "details": {"blocked": proposal_outcomes["blocked"]},
            }
        )
    if usage["budget_exceeded"]:
        findings.append(
            {
                "severity": "error",
                "code": "budget_limit_exceeded",
                "message": "Estimated LLM cost exceeded the configured run budget.",
                "details": {
                    "estimated_cost_usd": usage["estimated_cost_usd"],
                    "budget_limit_usd": usage["budget_limit_usd"],
                },
            }
        )
    if not findings:
        findings.append(
            {
                "severity": "info",
                "code": "no_diagnostics_found",
                "message": (
                    "No errors or manual-review blockers were found in persisted "
                    "tracking rows."
                ),
                "details": {},
            }
        )
    return findings


def _recommendations(
    *,
    agent_run: AgentRun,
    progress: dict[str, Any],
    findings: list[dict[str, Any]],
    usage: dict[str, Any],
) -> list[str]:
    codes = {str(finding["code"]) for finding in findings}
    recommendations: list[str] = []
    if "agent_run_errors_present" in codes:
        recommendations.append(
            "Inspect errors[] and use /resume-plan with retry_errors=true "
            "before rerunning the worker."
        )
    if "manual_review_required" in codes:
        recommendations.append(
            "Review manual_review_items before approving or applying "
            "generated proposals."
        )
    if "proposal_validation_blocked" in codes:
        recommendations.append(
            "Check validation categories and evidence before turning blocked "
            "candidates into suggestions."
        )
    if "documents_skipped_or_unchanged" in codes:
        recommendations.append(
            "Skipped/unchanged documents are expected for idempotent reruns; "
            "use force_rescan only when hashes or context are stale."
        )
    if usage["budget_exceeded"]:
        recommendations.append(
            "Reduce batch size or model cost before continuing this run."
        )
    if (
        agent_run.status in FINAL_AGENT_RUN_STATUSES
        and progress["errors"]["total"] == 0
    ):
        recommendations.append(
            "Archive report artifacts and keep the run immutable for audit."
        )
    if not recommendations:
        recommendations.append("No action required from persisted diagnostics.")
    return recommendations


def _overall_status(
    agent_run: AgentRun, progress: dict[str, Any], findings: list[dict[str, Any]]
) -> str:
    severities = {str(finding["severity"]) for finding in findings}
    if agent_run.status == "failed" or "error" in severities:
        return "degraded"
    if "warning" in severities or agent_run.status == "needs_review":
        return "needs_review"
    if progress["errors"]["total"] > 0:
        return "degraded"
    return "ok"


def _is_error(status: str | None, error_message: str | None) -> bool:
    return status in _ERROR_STATUSES or bool(error_message)


def _is_skipped_document(visit: AgentDocumentVisit) -> bool:
    return visit.visit_status in _SKIPPED_DOCUMENT_STATUSES or not visit.should_scan


def _source_id_for_observation(
    observation: AgentCandidateObservation | None,
) -> str | None:
    if observation is None or observation.document_visit is None:
        return None
    return observation.document_visit.source_id
