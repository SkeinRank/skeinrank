"""Validation checks for agent-ready governance proposals.

The proposal checker registry is intentionally side-effect free. It inspects
current governance state and returns structured validation results that can be
stored on ``GovernanceSuggestion.validation_summary_json``. Review/apply code can
then make policy decisions without re-discovering why a proposal looked risky.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from skeinrank_governance.models import (
    CanonicalTerm,
    GovernanceGlobalStopListEntry,
    GovernanceStopListEntry,
    GovernanceSuggestion,
    TermAlias,
    TerminologyProfile,
    normalize_value,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from .apply_policy import ensure_apply_policy_summary

PROPOSAL_VALIDATION_SCHEMA_VERSION = "skeinrank.proposal_validation.v1"
PROPOSAL_CHECK_STATUSES = ("passed", "warning", "blocked", "skipped")
PROPOSAL_CHECK_SEVERITIES = ("info", "warning", "error")


@dataclass(frozen=True)
class ProposalValidationContext:
    """Normalized proposal values used by checker functions."""

    session: Session
    profile: TerminologyProfile
    suggestion_type: str
    canonical_value: str
    alias_value: str | None
    slot: str
    confidence: float
    proposal_source_type: str = "human"
    proposal_source_name: str | None = None
    idempotency_key: str | None = None
    source_payload: dict[str, Any] | None = None

    @property
    def normalized_canonical(self) -> str:
        return normalize_value(self.canonical_value)

    @property
    def normalized_alias(self) -> str | None:
        if self.alias_value is None:
            return None
        return normalize_value(self.alias_value)

    @property
    def normalized_slot(self) -> str:
        return self.slot.strip().upper()


@dataclass(frozen=True)
class ProposalCheckResult:
    """Single proposal checker result."""

    name: str
    status: str
    severity: str
    message: str
    details: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "status": self.status,
            "severity": self.severity,
            "message": self.message,
        }
        if self.details:
            payload["details"] = self.details
        return payload


ProposalChecker = Callable[[ProposalValidationContext], ProposalCheckResult]


def build_proposal_validation_summary(
    session: Session,
    profile: TerminologyProfile,
    *,
    suggestion_type: str,
    canonical_value: str,
    alias_value: str | None,
    slot: str,
    confidence: float,
    proposal_source_type: str = "human",
    proposal_source_name: str | None = None,
    idempotency_key: str | None = None,
    source_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run the proposal checker registry and return a stable JSON summary."""

    context = ProposalValidationContext(
        session=session,
        profile=profile,
        suggestion_type=suggestion_type,
        canonical_value=canonical_value,
        alias_value=alias_value,
        slot=slot,
        confidence=confidence,
        proposal_source_type=proposal_source_type,
        proposal_source_name=proposal_source_name,
        idempotency_key=idempotency_key,
        source_payload=source_payload,
    )
    results = [checker(context) for checker in PROPOSAL_CHECK_REGISTRY]
    counts = {status: 0 for status in PROPOSAL_CHECK_STATUSES}
    for result in results:
        counts[result.status] += 1

    if counts["blocked"]:
        overall_status = "blocked"
    elif counts["warning"]:
        overall_status = "warning"
    else:
        overall_status = "passed"

    summary = {
        "schema_version": PROPOSAL_VALIDATION_SCHEMA_VERSION,
        "status": overall_status,
        "checks": {result.name: result.to_dict() for result in results},
        "counts": counts,
    }
    return ensure_apply_policy_summary(
        summary,
        suggestion_type=context.suggestion_type,
        canonical_value=context.canonical_value,
        alias_value=context.alias_value,
        slot=context.slot,
        confidence=context.confidence,
        proposal_source_type=context.proposal_source_type,
        proposal_source_name=context.proposal_source_name,
        source_payload=context.source_payload,
    )


def _check_shape(context: ProposalValidationContext) -> ProposalCheckResult:
    if context.suggestion_type == "alias":
        if context.normalized_alias:
            return ProposalCheckResult(
                name="shape",
                status="passed",
                severity="info",
                message="Alias proposal has a surface form.",
            )
        return ProposalCheckResult(
            name="shape",
            status="blocked",
            severity="error",
            message="Alias proposals require alias_value.",
        )

    if context.suggestion_type == "canonical_term":
        if context.normalized_alias:
            return ProposalCheckResult(
                name="shape",
                status="blocked",
                severity="error",
                message="Canonical term proposals must not include alias_value.",
            )
        return ProposalCheckResult(
            name="shape",
            status="passed",
            severity="info",
            message="Canonical term proposal shape is valid.",
        )

    return ProposalCheckResult(
        name="shape",
        status="blocked",
        severity="error",
        message=f"Unsupported suggestion_type: {context.suggestion_type}",
    )


def _check_canonical_state(context: ProposalValidationContext) -> ProposalCheckResult:
    term = _find_canonical_term(context)
    if context.suggestion_type == "alias":
        if term is None:
            return ProposalCheckResult(
                name="canonical_state",
                status="warning",
                severity="warning",
                message="Canonical term does not exist yet; approval will require it.",
                details={"canonical_value": context.canonical_value},
            )
        if term.slot != context.normalized_slot:
            return ProposalCheckResult(
                name="canonical_state",
                status="warning",
                severity="warning",
                message="Proposal slot differs from the existing canonical term slot.",
                details={
                    "canonical_value": term.canonical_value,
                    "existing_slot": term.slot,
                    "proposal_slot": context.normalized_slot,
                },
            )
        return ProposalCheckResult(
            name="canonical_state",
            status="passed",
            severity="info",
            message="Canonical term exists and slot matches.",
            details={"canonical_value": term.canonical_value, "slot": term.slot},
        )

    if term is None:
        return ProposalCheckResult(
            name="canonical_state",
            status="passed",
            severity="info",
            message="Canonical term is available.",
        )
    return ProposalCheckResult(
        name="canonical_state",
        status="blocked",
        severity="error",
        message="Canonical term already exists in this profile.",
        details={"canonical_value": term.canonical_value, "slot": term.slot},
    )


def _check_alias_state(context: ProposalValidationContext) -> ProposalCheckResult:
    if context.suggestion_type != "alias":
        return ProposalCheckResult(
            name="alias_state",
            status="skipped",
            severity="info",
            message="Alias checks do not apply to canonical term proposals.",
        )
    normalized_alias = context.normalized_alias
    if normalized_alias is None:
        return ProposalCheckResult(
            name="alias_state",
            status="blocked",
            severity="error",
            message="Alias proposal is missing alias_value.",
        )

    alias = context.session.scalar(
        select(TermAlias).where(
            TermAlias.profile_id == context.profile.id,
            TermAlias.normalized_alias == normalized_alias,
        )
    )
    if alias is None:
        return ProposalCheckResult(
            name="alias_state",
            status="passed",
            severity="info",
            message="Alias surface form is not active in this profile.",
            details={"normalized_alias": normalized_alias},
        )

    existing_canonical = alias.term.canonical_value if alias.term is not None else None
    existing_normalized = (
        alias.term.normalized_value if alias.term is not None else None
    )
    if existing_normalized == context.normalized_canonical:
        return ProposalCheckResult(
            name="alias_state",
            status="warning",
            severity="warning",
            message="Alias already maps to the requested canonical term.",
            details={
                "normalized_alias": normalized_alias,
                "existing_canonical": existing_canonical,
            },
        )
    return ProposalCheckResult(
        name="alias_state",
        status="blocked",
        severity="error",
        message="Alias already maps to a different canonical term.",
        details={
            "normalized_alias": normalized_alias,
            "existing_canonical": existing_canonical,
            "proposed_canonical": context.canonical_value,
        },
    )


def _check_stop_list(context: ProposalValidationContext) -> ProposalCheckResult:
    if context.suggestion_type == "alias":
        value = context.alias_value or ""
        target = "alias"
    else:
        value = context.canonical_value
        target = "canonical"

    normalized_value = normalize_value(value)
    if not normalized_value:
        return ProposalCheckResult(
            name="stop_list",
            status="blocked",
            severity="error",
            message="Proposal value is empty after normalization.",
        )

    target_values = _stop_list_targets_for(target)
    global_entry = context.session.scalar(
        select(GovernanceGlobalStopListEntry).where(
            GovernanceGlobalStopListEntry.normalized_value == normalized_value,
            GovernanceGlobalStopListEntry.target.in_(target_values),
            GovernanceGlobalStopListEntry.is_active.is_(True),
        )
    )
    if global_entry is not None:
        return ProposalCheckResult(
            name="stop_list",
            status="blocked",
            severity="error",
            message="Proposal value is blocked by the global stop list.",
            details={
                "value": global_entry.value,
                "target": global_entry.target,
                "reason": global_entry.reason,
            },
        )

    profile_entry = context.session.scalar(
        select(GovernanceStopListEntry).where(
            GovernanceStopListEntry.profile_id == context.profile.id,
            GovernanceStopListEntry.normalized_value == normalized_value,
            GovernanceStopListEntry.target.in_(target_values),
            GovernanceStopListEntry.is_active.is_(True),
        )
    )
    if profile_entry is not None:
        return ProposalCheckResult(
            name="stop_list",
            status="blocked",
            severity="error",
            message="Proposal value is blocked by the profile stop list.",
            details={
                "value": profile_entry.value,
                "target": profile_entry.target,
                "reason": profile_entry.reason,
            },
        )

    return ProposalCheckResult(
        name="stop_list",
        status="passed",
        severity="info",
        message="Proposal value is not blocked by active stop lists.",
    )


def _check_noise(context: ProposalValidationContext) -> ProposalCheckResult:
    if context.suggestion_type != "alias":
        return ProposalCheckResult(
            name="noise",
            status="skipped",
            severity="info",
            message="Noise checks do not apply to canonical term proposals.",
        )
    normalized_alias = context.normalized_alias or ""
    if len(normalized_alias) < 2:
        return ProposalCheckResult(
            name="noise",
            status="warning",
            severity="warning",
            message="Alias is very short and may be noisy.",
            details={"normalized_alias": normalized_alias},
        )
    return ProposalCheckResult(
        name="noise",
        status="passed",
        severity="info",
        message="Alias length is acceptable for proposal review.",
    )


def _check_confidence(context: ProposalValidationContext) -> ProposalCheckResult:
    if context.confidence < 0.5:
        return ProposalCheckResult(
            name="confidence",
            status="warning",
            severity="warning",
            message="Proposal confidence is low and should be reviewed carefully.",
            details={"confidence": context.confidence},
        )
    return ProposalCheckResult(
        name="confidence",
        status="passed",
        severity="info",
        message="Proposal confidence is within the reviewable range.",
        details={"confidence": context.confidence},
    )


def _check_idempotency_key(context: ProposalValidationContext) -> ProposalCheckResult:
    if not context.idempotency_key:
        return ProposalCheckResult(
            name="idempotency_key",
            status="warning",
            severity="warning",
            message="No idempotency_key was provided; safe retries are harder to deduplicate.",
        )

    existing = context.session.scalar(
        select(GovernanceSuggestion).where(
            GovernanceSuggestion.profile_id == context.profile.id,
            GovernanceSuggestion.idempotency_key == context.idempotency_key,
        )
    )
    if existing is not None:
        return ProposalCheckResult(
            name="idempotency_key",
            status="warning",
            severity="warning",
            message="A proposal with this idempotency_key already exists in the profile.",
            details={"existing_suggestion_id": existing.id},
        )
    return ProposalCheckResult(
        name="idempotency_key",
        status="passed",
        severity="info",
        message="Idempotency key is available in this profile.",
    )


def _check_agent_payload(context: ProposalValidationContext) -> ProposalCheckResult:
    if context.proposal_source_type != "agent":
        return ProposalCheckResult(
            name="agent_payload",
            status="skipped",
            severity="info",
            message="Agent payload check only applies to agent-sourced proposals.",
        )
    if context.source_payload:
        return ProposalCheckResult(
            name="agent_payload",
            status="passed",
            severity="info",
            message="Agent proposal includes source payload for audit.",
        )
    return ProposalCheckResult(
        name="agent_payload",
        status="warning",
        severity="warning",
        message="Agent proposal has no source_payload; audit context is limited.",
    )


def _find_canonical_term(context: ProposalValidationContext) -> CanonicalTerm | None:
    return context.session.scalar(
        select(CanonicalTerm).where(
            CanonicalTerm.profile_id == context.profile.id,
            CanonicalTerm.normalized_value == context.normalized_canonical,
        )
    )


def _stop_list_targets_for(target: str) -> tuple[str, ...]:
    if target == "alias":
        return ("alias", "both")
    if target == "canonical":
        return ("canonical", "both")
    return ("alias", "canonical", "both")


PROPOSAL_CHECK_REGISTRY: tuple[ProposalChecker, ...] = (
    _check_shape,
    _check_canonical_state,
    _check_alias_state,
    _check_stop_list,
    _check_noise,
    _check_confidence,
    _check_idempotency_key,
    _check_agent_payload,
)

PROPOSAL_CHECK_NAMES = (
    "shape",
    "canonical_state",
    "alias_state",
    "stop_list",
    "noise",
    "confidence",
    "idempotency_key",
    "agent_payload",
)
