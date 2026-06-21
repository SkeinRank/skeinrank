"""Strict structured output helpers for alias scout model judgments."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

JsonDict = dict[str, Any]
AliasReviewAction = Literal["propose", "reject", "needs_evidence"]
_ALLOWED_ACTIONS = {"propose", "reject", "needs_evidence"}
_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)


class AliasReviewOutputError(ValueError):
    """Raised when an LLM judgment cannot be parsed or validated."""


@dataclass(frozen=True)
class AliasReviewJudgment:
    """Validated LLM judgment for one alias candidate."""

    action: AliasReviewAction
    confidence: float
    reason: str
    risk_flags: list[str] = field(default_factory=list)
    alias_value: str | None = None
    canonical_value: str | None = None
    slot: str | None = None
    context: str | None = None
    decision_trace: Mapping[str, Any] | None = None

    def to_dict(self) -> JsonDict:
        """Return a JSON-serializable representation."""

        payload: JsonDict = {
            "action": self.action,
            "confidence": self.confidence,
            "reason": self.reason,
            "risk_flags": list(self.risk_flags),
        }
        for key in ("alias_value", "canonical_value", "slot", "context"):
            value = getattr(self, key)
            if value is not None:
                payload[key] = value
        if self.decision_trace:
            payload["decision_trace"] = dict(self.decision_trace)
        return payload


def _loads_json_object(raw: str | Mapping[str, Any]) -> JsonDict:
    if isinstance(raw, Mapping):
        return dict(raw)
    if not isinstance(raw, str):
        raise AliasReviewOutputError(
            "Alias review output must be a JSON string or object."
        )

    stripped = raw.strip()
    if not stripped:
        raise AliasReviewOutputError("Alias review output is empty.")
    fence_match = _JSON_FENCE_RE.fullmatch(stripped)
    if fence_match:
        stripped = fence_match.group(1).strip()
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise AliasReviewOutputError(
            f"Alias review output is not valid JSON: {exc}"
        ) from exc
    if not isinstance(parsed, dict):
        raise AliasReviewOutputError("Alias review output must be a JSON object.")
    return parsed


def parse_alias_review_output(raw: str | Mapping[str, Any]) -> AliasReviewJudgment:
    """Parse and validate a strict alias-review model judgment."""

    payload = _loads_json_object(raw)
    action = str(payload.get("action", "")).strip()
    if action not in _ALLOWED_ACTIONS:
        raise AliasReviewOutputError(
            "Alias review action must be one of: propose, reject, needs_evidence."
        )

    try:
        confidence = float(payload.get("confidence"))
    except (TypeError, ValueError) as exc:
        raise AliasReviewOutputError(
            "Alias review confidence must be a number."
        ) from exc
    if not 0.0 <= confidence <= 1.0:
        raise AliasReviewOutputError("Alias review confidence must be between 0 and 1.")

    reason = str(payload.get("reason", "")).strip()
    if not reason:
        raise AliasReviewOutputError("Alias review reason is required.")

    risk_flags_raw = payload.get("risk_flags", [])
    if not isinstance(risk_flags_raw, list) or not all(
        isinstance(item, str) for item in risk_flags_raw
    ):
        raise AliasReviewOutputError(
            "Alias review risk_flags must be a list of strings."
        )
    risk_flags = [item.strip() for item in risk_flags_raw if item.strip()]

    alias_value = _optional_str(payload.get("alias_value"))
    canonical_value = _optional_str(payload.get("canonical_value"))
    slot = _optional_str(payload.get("slot"))
    context = _optional_str(payload.get("context"))
    decision_trace = _optional_mapping(payload.get("decision_trace"))

    if action == "propose":
        missing = [
            name
            for name, value in (
                ("alias_value", alias_value),
                ("canonical_value", canonical_value),
                ("slot", slot),
            )
            if not value
        ]
        if missing:
            raise AliasReviewOutputError(
                f"Propose judgments require: {', '.join(missing)}."
            )

    return AliasReviewJudgment(
        action=action,  # type: ignore[arg-type]
        confidence=confidence,
        reason=reason,
        risk_flags=risk_flags,
        alias_value=alias_value,
        canonical_value=canonical_value,
        slot=slot,
        context=context,
        decision_trace=decision_trace,
    )


def judgment_to_proposal_payload(
    judgment: AliasReviewJudgment,
    *,
    binding_id: int | None = None,
    profile_name: str | None = None,
    proposal_source_name: str,
    idempotency_key: str,
    source_payload: Mapping[str, Any] | None = None,
) -> JsonDict:
    """Convert a propose judgment into a SkeinRank suggest-alias payload."""

    if judgment.action != "propose":
        raise AliasReviewOutputError(
            "Only propose judgments can become proposal payloads."
        )
    if not judgment.alias_value or not judgment.canonical_value or not judgment.slot:
        raise AliasReviewOutputError(
            "Proposal payload requires alias, canonical, and slot."
        )

    payload: JsonDict = {
        "canonical_value": judgment.canonical_value,
        "alias_value": judgment.alias_value,
        "slot": judgment.slot,
        "confidence": judgment.confidence,
        "proposal_source_name": proposal_source_name,
        "idempotency_key": idempotency_key,
        "source_payload": dict(source_payload or {}),
    }
    if binding_id is not None:
        payload["binding_id"] = binding_id
    if profile_name is not None:
        payload["profile_name"] = profile_name
    if judgment.context:
        payload["context"] = judgment.context
    if judgment.decision_trace:
        payload["source_payload"]["model_decision_trace"] = dict(
            judgment.decision_trace
        )
    return payload


def _optional_mapping(value: Any) -> Mapping[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise AliasReviewOutputError("Alias review decision_trace must be an object.")
    return {str(key): item for key, item in value.items()}


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
