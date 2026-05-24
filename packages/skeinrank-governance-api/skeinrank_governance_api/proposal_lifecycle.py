"""Proposal lifecycle helpers for governance suggestions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from skeinrank_governance.models import GovernanceSuggestion

SUGGESTION_LIFECYCLE_STATUSES = (
    "pending_reviewable",
    "pending_needs_review",
    "pending_blocked",
    "approved_applied",
    "rejected",
    "unknown",
)


@dataclass(frozen=True)
class ProposalLifecycleDecision:
    """Computed lifecycle state for a governance suggestion."""

    lifecycle_status: str
    lifecycle_reason: str
    validation_status: str
    can_approve: bool
    can_apply: bool
    requires_warning_override: bool = False


def proposal_validation_status(summary: object) -> str:
    """Return the normalized proposal validation status from a saved summary."""

    if isinstance(summary, dict):
        value = summary.get("status")
        if isinstance(value, str) and value.strip():
            return value.strip().lower()
    return "unknown"


def proposal_validation_counts(summary: object) -> dict[str, int]:
    """Return normalized validation count values from a saved summary."""

    if not isinstance(summary, dict):
        return {}
    counts = summary.get("counts")
    if not isinstance(counts, dict):
        return {}
    normalized: dict[str, int] = {}
    for key, value in counts.items():
        if isinstance(key, str) and isinstance(value, int):
            normalized[key] = value
    return normalized


def proposal_validation_reasons(summary: object, expected_status: str) -> list[str]:
    """Return human-readable validation reasons for a check status."""

    if not isinstance(summary, dict):
        return []
    checks = summary.get("checks")
    if not isinstance(checks, dict):
        return []
    reasons: list[str] = []
    for name, check in checks.items():
        if not isinstance(name, str) or not isinstance(check, dict):
            continue
        status_value = check.get("status")
        if status_value != expected_status:
            continue
        message = check.get("message")
        if isinstance(message, str) and message.strip():
            reasons.append(f"{name}: {message.strip()}")
        else:
            reasons.append(name)
    return reasons


def proposal_warning_requires_explicit_override(
    suggestion: GovernanceSuggestion,
) -> bool:
    """Return whether validation warnings should block direct approval.

    Agent/import proposals carry external automation context and should require an
    explicit warning override. Legacy human/manual suggestions can still fall
    through to the existing domain checks so old errors such as missing canonical
    term, duplicate alias, or stop-list violations remain precise.
    """

    if suggestion.proposal_source_type == "agent":
        return True
    if suggestion.idempotency_key:
        return True
    if (
        isinstance(suggestion.source_payload_json, dict)
        and suggestion.source_payload_json
    ):
        return True
    return False


def classify_proposal_lifecycle(
    suggestion: GovernanceSuggestion,
) -> ProposalLifecycleDecision:
    """Compute proposal lifecycle state without mutating the suggestion."""

    validation_status = proposal_validation_status(
        suggestion.validation_summary_json or {}
    )
    if suggestion.status == "approved":
        return ProposalLifecycleDecision(
            lifecycle_status="approved_applied",
            lifecycle_reason="suggestion_already_approved",
            validation_status=validation_status,
            can_approve=False,
            can_apply=False,
        )
    if suggestion.status == "rejected":
        return ProposalLifecycleDecision(
            lifecycle_status="rejected",
            lifecycle_reason="suggestion_rejected",
            validation_status=validation_status,
            can_approve=False,
            can_apply=False,
        )
    if suggestion.status != "pending":
        return ProposalLifecycleDecision(
            lifecycle_status="unknown",
            lifecycle_reason=f"unsupported_status:{suggestion.status}",
            validation_status=validation_status,
            can_approve=False,
            can_apply=False,
        )
    if validation_status == "blocked":
        return ProposalLifecycleDecision(
            lifecycle_status="pending_blocked",
            lifecycle_reason="validation_blocked",
            validation_status=validation_status,
            can_approve=False,
            can_apply=False,
        )
    if validation_status == "warning":
        if proposal_warning_requires_explicit_override(suggestion):
            return ProposalLifecycleDecision(
                lifecycle_status="pending_needs_review",
                lifecycle_reason="validation_warning_requires_explicit_override",
                validation_status=validation_status,
                can_approve=False,
                can_apply=False,
                requires_warning_override=True,
            )
        return ProposalLifecycleDecision(
            lifecycle_status="pending_reviewable",
            lifecycle_reason="validation_warning_allows_legacy_review_flow",
            validation_status=validation_status,
            can_approve=True,
            can_apply=True,
            requires_warning_override=False,
        )
    return ProposalLifecycleDecision(
        lifecycle_status="pending_reviewable",
        lifecycle_reason="pending_validation_allows_review",
        validation_status=validation_status,
        can_approve=True,
        can_apply=True,
    )


def lifecycle_decision_json(
    decision: ProposalLifecycleDecision,
) -> dict[str, Any]:
    """Serialize a lifecycle decision for API responses and audit payloads."""

    return {
        "lifecycle_status": decision.lifecycle_status,
        "lifecycle_reason": decision.lifecycle_reason,
        "validation_status": decision.validation_status,
        "can_approve": decision.can_approve,
        "can_apply": decision.can_apply,
        "requires_warning_override": decision.requires_warning_override,
    }
