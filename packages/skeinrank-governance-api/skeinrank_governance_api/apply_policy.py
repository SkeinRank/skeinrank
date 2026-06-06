"""Apply policy and risk-level helpers for governance proposals.

The policy layer is intentionally side-effect free. It translates an existing
proposal validation summary plus stable proposal metadata into an operator-facing
risk decision that UI, review, and batch-apply flows can display without adding
new database columns.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from skeinrank_governance.models import GovernanceSuggestion, normalize_value

APPLY_POLICY_SCHEMA_VERSION = "skeinrank.apply_policy.v1"
APPLY_RISK_LEVELS = ("low", "medium", "high", "unknown")
APPLY_POLICY_DECISIONS = (
    "batch_approve_allowed",
    "review_required",
    "admin_or_reject",
    "unknown",
)

_HIGH_RISK_FLAGS = {
    "ambiguous",
    "ambiguous_alias",
    "conflict",
    "different_canonical",
    "stop_list",
    "unsafe",
    "short_alias",
    "manual_block",
    "prompt_like_instruction",
    "hidden_prompt_request",
    "secret_exfiltration_request",
    "tool_injection_request",
    "destructive_action_request",
    "html_instruction_comment",
}


@dataclass(frozen=True)
class ApplyPolicyResult:
    """Normalized apply policy decision for a proposal."""

    risk_level: str
    decision: str
    can_batch_apply: bool
    requires_reviewer: bool
    requires_admin: bool
    requires_warning_override: bool
    auto_apply_allowed: bool
    reasons: tuple[str, ...]
    signals: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": APPLY_POLICY_SCHEMA_VERSION,
            "risk_level": self.risk_level,
            "decision": self.decision,
            "can_batch_apply": self.can_batch_apply,
            "requires_reviewer": self.requires_reviewer,
            "requires_admin": self.requires_admin,
            "requires_warning_override": self.requires_warning_override,
            "auto_apply_allowed": self.auto_apply_allowed,
            "reasons": list(self.reasons),
            "signals": dict(self.signals),
        }


def build_apply_policy_summary(
    *,
    validation_summary: object,
    suggestion_type: str,
    canonical_value: str,
    alias_value: str | None,
    slot: str,
    confidence: float,
    proposal_source_type: str = "human",
    proposal_source_name: str | None = None,
    source_payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Classify proposal risk and return a stable JSON policy payload."""

    summary = validation_summary if isinstance(validation_summary, Mapping) else {}
    validation_status = _validation_status(summary)
    counts = _validation_counts(summary)
    checks = summary.get("checks") if isinstance(summary, Mapping) else None
    blocked_checks = _checks_with_status(checks, "blocked")
    warning_checks = _checks_with_status(checks, "warning")
    risk_flags = _risk_flags(source_payload) | _risk_flags_from_checks(checks)
    high_risk_flags = sorted(flag for flag in risk_flags if flag in _HIGH_RISK_FLAGS)
    normalized_alias = normalize_value(alias_value or "") if alias_value else None
    normalized_canonical = normalize_value(canonical_value)
    alias_length = len(normalized_alias or "")

    reasons: list[str] = []
    if validation_status == "blocked":
        reasons.append("validation_status_blocked")
    if blocked_checks:
        reasons.append("blocked_validation_checks")
    if high_risk_flags:
        reasons.append("high_risk_flags")
    if suggestion_type == "alias" and alias_length <= 1:
        reasons.append("very_short_alias")
    if confidence < 0.5:
        reasons.append("low_confidence")

    if reasons:
        risk_level = "high"
    else:
        if validation_status in {"warning", "unknown"}:
            reasons.append(f"validation_status_{validation_status}")
        if warning_checks:
            reasons.append("warning_validation_checks")
        if confidence < 0.85:
            reasons.append("confidence_below_low_risk_threshold")
        if risk_flags:
            reasons.append("risk_flags_present")
        if suggestion_type == "alias" and alias_length == 2:
            reasons.append("short_alias_requires_review")
        risk_level = "medium" if reasons else "low"

    if risk_level == "high":
        decision = "admin_or_reject"
        can_batch_apply = False
        requires_reviewer = True
        requires_admin = True
        requires_warning_override = False
    elif risk_level == "medium":
        decision = "review_required"
        can_batch_apply = False
        requires_reviewer = True
        requires_admin = False
        requires_warning_override = validation_status == "warning" or bool(
            warning_checks
        )
    else:
        decision = "batch_approve_allowed"
        can_batch_apply = True
        requires_reviewer = True
        requires_admin = False
        requires_warning_override = False
        reasons.append("validation_passed_low_risk_thresholds")

    signals = {
        "validation_status": validation_status,
        "validation_counts": counts,
        "blocked_checks": blocked_checks,
        "warning_checks": warning_checks,
        "confidence": confidence,
        "confidence_threshold_low_risk": 0.85,
        "suggestion_type": suggestion_type,
        "normalized_alias": normalized_alias,
        "alias_length": alias_length,
        "normalized_canonical": normalized_canonical,
        "slot": slot.strip().upper(),
        "proposal_source_type": proposal_source_type,
        "proposal_source_name": proposal_source_name,
        "risk_flags": sorted(risk_flags),
    }
    return ApplyPolicyResult(
        risk_level=risk_level,
        decision=decision,
        can_batch_apply=can_batch_apply,
        requires_reviewer=requires_reviewer,
        requires_admin=requires_admin,
        requires_warning_override=requires_warning_override,
        auto_apply_allowed=False,
        reasons=tuple(dict.fromkeys(reasons)),
        signals=signals,
    ).to_dict()


def ensure_apply_policy_summary(
    validation_summary: object,
    *,
    suggestion_type: str,
    canonical_value: str,
    alias_value: str | None,
    slot: str,
    confidence: float,
    proposal_source_type: str = "human",
    proposal_source_name: str | None = None,
    source_payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return validation summary enriched with risk level and apply policy."""

    if isinstance(validation_summary, Mapping):
        summary = dict(validation_summary)
    else:
        summary = {}
    policy = build_apply_policy_summary(
        validation_summary=summary,
        suggestion_type=suggestion_type,
        canonical_value=canonical_value,
        alias_value=alias_value,
        slot=slot,
        confidence=confidence,
        proposal_source_type=proposal_source_type,
        proposal_source_name=proposal_source_name,
        source_payload=source_payload,
    )
    summary["apply_policy"] = policy
    summary["risk_level"] = policy["risk_level"]
    summary["apply_policy_decision"] = policy["decision"]
    return summary


def apply_policy_for_suggestion(suggestion: GovernanceSuggestion) -> dict[str, Any]:
    """Return saved or computed apply policy for a suggestion."""

    summary = suggestion.validation_summary_json or {}
    if isinstance(summary, Mapping):
        policy = summary.get("apply_policy")
        if isinstance(policy, Mapping):
            normalized = _normalize_saved_policy(policy)
            if normalized is not None:
                return normalized
    return build_apply_policy_summary(
        validation_summary=summary,
        suggestion_type=suggestion.suggestion_type,
        canonical_value=suggestion.canonical_value,
        alias_value=suggestion.alias_value,
        slot=suggestion.slot,
        confidence=float(suggestion.confidence or 0.0),
        proposal_source_type=suggestion.proposal_source_type,
        proposal_source_name=suggestion.proposal_source_name,
        source_payload=suggestion.source_payload_json,
    )


def risk_level_for_suggestion(suggestion: GovernanceSuggestion) -> str:
    """Return normalized risk level for a suggestion."""

    return str(apply_policy_for_suggestion(suggestion).get("risk_level") or "unknown")


def apply_policy_allows_batch(policy: object) -> bool:
    """Return whether policy marks the proposal safe for normal batch apply."""

    return isinstance(policy, Mapping) and bool(policy.get("can_batch_apply"))


def apply_policy_requires_admin(policy: object) -> bool:
    """Return whether policy requires admin-level handling or rejection."""

    return isinstance(policy, Mapping) and bool(policy.get("requires_admin"))


def _validation_status(summary: Mapping[str, Any]) -> str:
    value = summary.get("status")
    if isinstance(value, str) and value.strip():
        return value.strip().lower()
    return "unknown"


def _validation_counts(summary: Mapping[str, Any]) -> dict[str, int]:
    counts = summary.get("counts")
    if not isinstance(counts, Mapping):
        return {}
    return {
        str(key): int(value) for key, value in counts.items() if isinstance(value, int)
    }


def _checks_with_status(checks: object, expected_status: str) -> list[str]:
    if not isinstance(checks, Mapping):
        return []
    names: list[str] = []
    for name, check in checks.items():
        if not isinstance(name, str) or not isinstance(check, Mapping):
            continue
        if check.get("status") == expected_status:
            names.append(name)
    return sorted(names)


def _risk_flags(source_payload: Mapping[str, Any] | None) -> set[str]:
    if not isinstance(source_payload, Mapping):
        return set()
    values: list[Any] = []
    for key in ("risk_flags", "flags"):
        raw = source_payload.get(key)
        if isinstance(raw, list):
            values.extend(raw)
    judgment = source_payload.get("llm_judgment")
    if isinstance(judgment, Mapping):
        raw = judgment.get("risk_flags")
        if isinstance(raw, list):
            values.extend(raw)
    return {str(value).strip().lower() for value in values if str(value).strip()}


def _risk_flags_from_checks(checks: object) -> set[str]:
    if not isinstance(checks, Mapping):
        return set()
    values: list[Any] = []
    for check in checks.values():
        if not isinstance(check, Mapping):
            continue
        details = check.get("details")
        if isinstance(details, Mapping):
            raw = details.get("risk_flags")
            if isinstance(raw, list):
                values.extend(raw)
            risk_summary = details.get("prompt_injection_risk")
            if isinstance(risk_summary, Mapping):
                raw = risk_summary.get("risk_flags")
                if isinstance(raw, list):
                    values.extend(raw)
    return {str(value).strip().lower() for value in values if str(value).strip()}


def _normalize_saved_policy(policy: Mapping[str, Any]) -> dict[str, Any] | None:
    risk_level = str(policy.get("risk_level") or "").strip().lower()
    decision = str(policy.get("decision") or "").strip().lower()
    if risk_level not in APPLY_RISK_LEVELS or decision not in APPLY_POLICY_DECISIONS:
        return None
    return {
        "schema_version": str(
            policy.get("schema_version") or APPLY_POLICY_SCHEMA_VERSION
        ),
        "risk_level": risk_level,
        "decision": decision,
        "can_batch_apply": bool(policy.get("can_batch_apply")),
        "requires_reviewer": bool(policy.get("requires_reviewer", True)),
        "requires_admin": bool(policy.get("requires_admin")),
        "requires_warning_override": bool(policy.get("requires_warning_override")),
        "auto_apply_allowed": bool(policy.get("auto_apply_allowed")) and False,
        "reasons": list(policy.get("reasons") or []),
        "signals": dict(policy.get("signals") or {}),
    }
