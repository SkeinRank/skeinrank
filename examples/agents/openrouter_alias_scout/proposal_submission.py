"""Safe validation/submission bridge for OpenRouter alias scout proposals.

The bridge connects model-created ``proposal_payload`` values to the existing
SkeinRank ``/v1/tools/validate-alias`` and ``/v1/tools/suggest-alias`` tools. It
classifies validation warnings before submission so the runner can avoid
duplicate proposals and route edge cases to manual review.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

try:  # pragma: no cover - import style depends on how the example is executed.
    from .security_profile import SecurityProfileConfig
    from .skeinrank_client import SkeinRankAgentClientError
except ImportError:  # pragma: no cover
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from security_profile import SecurityProfileConfig
    from skeinrank_client import SkeinRankAgentClientError

JsonDict = dict[str, Any]
VALIDATION_PASSING_STATUSES = ("passed",)
WARNING_STATUSES = ("warning",)
BLOCKED_STATUSES = ("blocked",)


class ProposalToolClient(Protocol):
    """Protocol for the SkeinRank client methods used by this bridge."""

    def validate_alias(
        self,
        *,
        canonical_value: str,
        alias_value: str,
        slot: str,
        binding_id: int | None = None,
        profile_name: str | None = None,
        confidence: float = 1.0,
        proposal_source_name: str | None = None,
        idempotency_key: str | None = None,
        source_payload: Mapping[str, Any] | None = None,
    ) -> Any: ...

    def suggest_alias(
        self,
        *,
        canonical_value: str,
        alias_value: str,
        slot: str,
        binding_id: int | None = None,
        profile_name: str | None = None,
        confidence: float = 1.0,
        context: str | None = None,
        proposal_source_name: str | None = None,
        idempotency_key: str | None = None,
        source_payload: Mapping[str, Any] | None = None,
    ) -> Any: ...


@dataclass(frozen=True)
class ProposalSubmissionConfig:
    """Controls safe validation and optional proposal submission."""

    max_proposals_per_run: int = 5
    min_confidence: float = 0.85
    require_validation_status: str = "passed"
    submit_enabled: bool = False
    stop_on_error: bool = False
    treat_existing_alias_as_idempotent: bool = True
    manual_review_on_warning: bool = True

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any] | None) -> "ProposalSubmissionConfig":
        """Create config from optional JSON config values."""

        if not raw:
            return cls()
        return cls(
            max_proposals_per_run=int(
                raw.get("max_proposals_per_run", cls.max_proposals_per_run)
            ),
            min_confidence=float(raw.get("min_confidence", cls.min_confidence)),
            require_validation_status=str(
                raw.get("require_validation_status", cls.require_validation_status)
            ),
            submit_enabled=bool(raw.get("submit_enabled", cls.submit_enabled)),
            stop_on_error=bool(raw.get("stop_on_error", cls.stop_on_error)),
            treat_existing_alias_as_idempotent=bool(
                raw.get(
                    "treat_existing_alias_as_idempotent",
                    cls.treat_existing_alias_as_idempotent,
                )
            ),
            manual_review_on_warning=bool(
                raw.get("manual_review_on_warning", cls.manual_review_on_warning)
            ),
        )


@dataclass(frozen=True)
class ValidationDecision:
    """Agent-side interpretation of a SkeinRank validation response."""

    category: str
    status: str
    submit_allowed: bool
    counts_as_validated: bool = True
    counts_as_passed: bool = False
    counts_as_idempotent: bool = False
    requires_manual_review: bool = False
    reason: str = ""

    def as_dict(self) -> JsonDict:
        """Return a JSON-serializable representation for reports."""

        return {
            "category": self.category,
            "status": self.status,
            "submit_allowed": self.submit_allowed,
            "counts_as_validated": self.counts_as_validated,
            "counts_as_passed": self.counts_as_passed,
            "counts_as_idempotent": self.counts_as_idempotent,
            "requires_manual_review": self.requires_manual_review,
            "reason": self.reason,
        }


def build_proposal_submission_plan(
    llm_review_report: Mapping[str, Any],
    *,
    submission_config: ProposalSubmissionConfig | None = None,
    submit: bool = False,
) -> JsonDict:
    """Build an offline plan for proposal validation/submission."""

    cfg = submission_config or ProposalSubmissionConfig()
    ready_payloads = extract_ready_proposal_payloads(llm_review_report, config=cfg)
    return {
        "schema_version": "skeinrank.agent_proposal_submission_plan.v1",
        "runner": "openrouter_alias_scout",
        "skeinrank_api_calls": False,
        "proposal_submission_requested": submit,
        "proposal_submission_enabled_by_config": cfg.submit_enabled,
        "max_proposals_per_run": cfg.max_proposals_per_run,
        "min_confidence": cfg.min_confidence,
        "require_validation_status": cfg.require_validation_status,
        "treat_existing_alias_as_idempotent": cfg.treat_existing_alias_as_idempotent,
        "manual_review_on_warning": cfg.manual_review_on_warning,
        "eligible_proposals": len(ready_payloads),
        "candidate_aliases": [payload["alias_value"] for payload in ready_payloads],
        "will_validate_aliases": True,
        "will_submit_aliases": bool(submit and cfg.submit_enabled),
        "safety": {
            "validate_before_submit": True,
            "snapshot_publish_enabled": False,
            "runtime_mutation_enabled": False,
            "direct_dictionary_write_enabled": False,
            "warning_classification_enabled": True,
        },
    }


def validate_and_optionally_submit_proposals(
    llm_review_report: Mapping[str, Any],
    *,
    client: ProposalToolClient,
    submission_config: ProposalSubmissionConfig | None = None,
    security_config: SecurityProfileConfig | None = None,
    submit: bool = False,
) -> JsonDict:
    """Validate proposal payloads and optionally submit pending proposals.

    ``submit`` is an explicit runtime flag. The config and security profile must
    also allow submission. Validation always runs before submission.
    """

    cfg = submission_config or ProposalSubmissionConfig()
    security = security_config or SecurityProfileConfig()
    _assert_submission_policy(cfg=cfg, security=security, submit=submit)

    ready_payloads = extract_ready_proposal_payloads(llm_review_report, config=cfg)
    results: list[JsonDict] = []
    for payload in ready_payloads:
        try:
            result = _validate_and_maybe_submit_one(
                payload,
                client=client,
                cfg=cfg,
                submit=submit,
            )
        except SkeinRankAgentClientError as exc:
            result = _error_result(payload, code="skeinrank_api_error", error=str(exc))
        except Exception as exc:  # pragma: no cover - defensive CLI boundary.
            result = _error_result(payload, code="unexpected_error", error=str(exc))
        results.append(result)
        if cfg.stop_on_error and result["status"] == "error":
            break

    summary = _summarize_results(results, ready_payload_count=len(ready_payloads))
    return {
        "schema_version": "skeinrank.agent_proposal_submission_report.v1",
        "runner": "openrouter_alias_scout",
        "skeinrank_api_calls": True,
        "proposal_submission_requested": submit,
        "proposal_submission_enabled": bool(submit and cfg.submit_enabled),
        "runtime_mutation_enabled": False,
        "snapshot_publish_enabled": False,
        "summary": summary,
        "results": results,
        "safety": {
            "validate_before_submit": True,
            "agent_may_mutate_runtime": False,
            "warning_classification_enabled": True,
            "blocked_actions": [
                "direct_dictionary_write",
                "snapshot_publish",
                "direct_git_push",
                "runtime_mutation",
            ],
        },
    }


def extract_ready_proposal_payloads(
    llm_review_report: Mapping[str, Any],
    *,
    config: ProposalSubmissionConfig | None = None,
) -> list[JsonDict]:
    """Return high-confidence proposal payloads from an LLM review report."""

    cfg = config or ProposalSubmissionConfig()
    payloads: list[JsonDict] = []
    for item in llm_review_report.get("reviewed_items", []):
        if not isinstance(item, Mapping):
            continue
        if item.get("proposal_ready_for_validation") is not True:
            continue
        payload = item.get("proposal_payload")
        if not isinstance(payload, Mapping):
            continue
        confidence = _safe_float(payload.get("confidence"), default=0.0)
        if confidence < cfg.min_confidence:
            continue
        payloads.append(dict(payload))
        if len(payloads) >= cfg.max_proposals_per_run:
            break
    return payloads


def classify_validation_decision(
    validation_response: Mapping[str, Any],
    *,
    payload: Mapping[str, Any] | None = None,
    config: ProposalSubmissionConfig | None = None,
) -> ValidationDecision:
    """Classify SkeinRank validation output for agent submission decisions.

    A warning can mean very different things. ``alias already maps to the
    requested canonical`` is an idempotent no-op, while slot mismatch or generic
    warnings require human review. This function keeps that policy outside the
    backend so the guarded flow does not change existing API behavior.
    """

    cfg = config or ProposalSubmissionConfig()
    summary = _extract_validation_summary(validation_response)
    status = str(summary.get("status", "unknown"))
    checks = _extract_validation_checks(summary)

    if status in VALIDATION_PASSING_STATUSES:
        return ValidationDecision(
            category="validation_passed",
            status=status,
            submit_allowed=True,
            counts_as_passed=True,
            reason="validation_status_passed",
        )

    if status in BLOCKED_STATUSES or _summary_has_blocked_checks(summary):
        return ValidationDecision(
            category="blocked",
            status=status,
            submit_allowed=False,
            requires_manual_review=True,
            reason=_first_blocking_reason(checks) or "validation_blocked",
        )

    if status in WARNING_STATUSES:
        if _has_slot_mismatch_warning(checks):
            return ValidationDecision(
                category="manual_review_required",
                status=status,
                submit_allowed=False,
                requires_manual_review=True,
                reason="slot_mismatch_warning",
            )
        if cfg.treat_existing_alias_as_idempotent and _is_existing_alias_same_canonical(
            checks, payload=payload
        ):
            return ValidationDecision(
                category="idempotent_existing_alias",
                status=status,
                submit_allowed=False,
                counts_as_passed=True,
                counts_as_idempotent=True,
                reason="alias_already_maps_to_requested_canonical",
            )
        if cfg.manual_review_on_warning:
            return ValidationDecision(
                category="manual_review_required",
                status=status,
                submit_allowed=False,
                requires_manual_review=True,
                reason="validation_warning_requires_review",
            )

    return ValidationDecision(
        category="validation_not_passing",
        status=status,
        submit_allowed=False,
        requires_manual_review=True,
        reason=f"validation_status_not_passing:{status}",
    )


def _validate_and_maybe_submit_one(
    payload: Mapping[str, Any],
    *,
    client: ProposalToolClient,
    cfg: ProposalSubmissionConfig,
    submit: bool,
) -> JsonDict:
    validation_response = client.validate_alias(**_validate_kwargs(payload))
    validation_summary = _extract_validation_summary(validation_response)
    validation_status = str(validation_summary.get("status", "unknown"))
    decision = classify_validation_decision(
        validation_response,
        payload=payload,
        config=cfg,
    )
    result: JsonDict = {
        "alias_value": payload.get("alias_value"),
        "canonical_value": payload.get("canonical_value"),
        "slot": payload.get("slot"),
        "confidence": payload.get("confidence"),
        "idempotency_key": payload.get("idempotency_key"),
        "validation_status": validation_status,
        "validation_decision": decision.as_dict(),
        "validation_response": validation_response,
        "submitted": False,
        "status": "validated",
    }
    if decision.category == "idempotent_existing_alias":
        result["status"] = "idempotent_existing_alias"
        result["submission_skipped_reason"] = decision.reason
        return result
    if decision.category == "blocked":
        result["status"] = "blocked"
        result["submission_skipped_reason"] = decision.reason
        return result
    if decision.category == "manual_review_required":
        result["status"] = "manual_review_required"
        result["submission_skipped_reason"] = decision.reason
        return result
    if not decision.submit_allowed:
        result["status"] = "validation_not_passing"
        result["submission_skipped_reason"] = decision.reason
        return result
    if not submit:
        result["submission_skipped_reason"] = "submit_flag_not_set"
        return result
    submission_response = client.suggest_alias(**_suggest_kwargs(payload))
    result["submitted"] = True
    result["status"] = "submitted"
    result["submission_response"] = submission_response
    result["created"] = _created_from_submission_response(submission_response)
    return result


def _validate_kwargs(payload: Mapping[str, Any]) -> JsonDict:
    kwargs = _common_tool_kwargs(payload)
    return kwargs


def _suggest_kwargs(payload: Mapping[str, Any]) -> JsonDict:
    kwargs = _common_tool_kwargs(payload)
    context = payload.get("context")
    if context:
        kwargs["context"] = str(context)
    return kwargs


def _common_tool_kwargs(payload: Mapping[str, Any]) -> JsonDict:
    required = ("canonical_value", "alias_value", "slot")
    missing = [name for name in required if not payload.get(name)]
    if missing:
        raise ValueError(f"Proposal payload is missing required fields: {missing}")
    kwargs: JsonDict = {
        "canonical_value": str(payload["canonical_value"]),
        "alias_value": str(payload["alias_value"]),
        "slot": str(payload["slot"]),
        "confidence": _safe_float(payload.get("confidence"), default=1.0),
    }
    for key in (
        "binding_id",
        "profile_name",
        "proposal_source_name",
        "idempotency_key",
        "source_payload",
    ):
        value = payload.get(key)
        if value is not None:
            kwargs[key] = value
    return kwargs


def _extract_validation_summary(response: Any) -> JsonDict:
    if isinstance(response, Mapping):
        summary = response.get("validation_summary")
        if isinstance(summary, Mapping):
            return dict(summary)
    return {"status": "unknown"}


def _extract_validation_checks(summary: Mapping[str, Any]) -> dict[str, JsonDict]:
    checks = summary.get("checks")
    if not isinstance(checks, Mapping):
        return {}
    extracted: dict[str, JsonDict] = {}
    for name, value in checks.items():
        if isinstance(value, Mapping):
            extracted[str(name)] = dict(value)
    return extracted


def _summary_has_blocked_checks(summary: Mapping[str, Any]) -> bool:
    counts = summary.get("counts")
    if isinstance(counts, Mapping) and int(counts.get("blocked") or 0) > 0:
        return True
    for check in _extract_validation_checks(summary).values():
        if str(check.get("status", "")).lower() == "blocked":
            return True
        if str(check.get("severity", "")).lower() == "blocked":
            return True
    return False


def _first_blocking_reason(checks: Mapping[str, Mapping[str, Any]]) -> str | None:
    for name, check in checks.items():
        status = str(check.get("status", "")).lower()
        severity = str(check.get("severity", "")).lower()
        if status == "blocked" or severity == "blocked":
            message = check.get("message")
            if message:
                return f"{name}:{message}"
            return name
    return None


def _is_existing_alias_same_canonical(
    checks: Mapping[str, Mapping[str, Any]], *, payload: Mapping[str, Any] | None
) -> bool:
    alias_state = checks.get("alias_state")
    if not isinstance(alias_state, Mapping):
        return False
    status = str(alias_state.get("status", "")).lower()
    message = str(alias_state.get("message", "")).lower()
    if status != "warning" or "already maps" not in message:
        return False
    details = alias_state.get("details")
    if not isinstance(details, Mapping) or payload is None:
        return True
    existing = _normalize_value(details.get("existing_canonical"))
    proposed = _normalize_value(payload.get("canonical_value"))
    return not existing or not proposed or existing == proposed


def _has_slot_mismatch_warning(checks: Mapping[str, Mapping[str, Any]]) -> bool:
    canonical_state = checks.get("canonical_state")
    if isinstance(canonical_state, Mapping):
        status = str(canonical_state.get("status", "")).lower()
        message = str(canonical_state.get("message", "")).lower()
        if status == "warning" and "slot differs" in message:
            return True
        details = canonical_state.get("details")
        if isinstance(details, Mapping):
            existing_slot = _normalize_value(details.get("existing_slot"))
            proposal_slot = _normalize_value(details.get("proposal_slot"))
            if existing_slot and proposal_slot and existing_slot != proposal_slot:
                return True
    return False


def _created_from_submission_response(response: Any) -> bool | None:
    if isinstance(response, Mapping) and isinstance(response.get("created"), bool):
        return bool(response["created"])
    return None


def _summarize_results(
    results: Sequence[Mapping[str, Any]], *, ready_payload_count: int
) -> JsonDict:
    summary = {
        "proposal_payloads_ready_for_validation": ready_payload_count,
        "validated": 0,
        "validation_passed": 0,
        "validation_warnings": 0,
        "validation_blocked": 0,
        "validation_not_passing": 0,
        "submitted": 0,
        "created": 0,
        "idempotent_retries": 0,
        "idempotent_existing_aliases": 0,
        "manual_review_required": 0,
        "blocked": 0,
        "errors": 0,
    }
    for result in results:
        status = str(result.get("status") or "")
        if status in {
            "validated",
            "submitted",
            "validation_not_passing",
            "idempotent_existing_alias",
            "manual_review_required",
            "blocked",
        }:
            summary["validated"] += 1
        validation_status = str(result.get("validation_status") or "")
        if validation_status == "passed":
            summary["validation_passed"] += 1
        elif validation_status == "warning":
            summary["validation_warnings"] += 1
        elif validation_status == "blocked":
            summary["validation_blocked"] += 1
        if status == "validation_not_passing":
            summary["validation_not_passing"] += 1
        if status == "idempotent_existing_alias":
            summary["idempotent_existing_aliases"] += 1
        if status == "manual_review_required":
            summary["manual_review_required"] += 1
        if status == "blocked":
            summary["blocked"] += 1
        if result.get("submitted"):
            summary["submitted"] += 1
            if result.get("created") is True:
                summary["created"] += 1
            elif result.get("created") is False:
                summary["idempotent_retries"] += 1
        if status == "error":
            summary["errors"] += 1
    return summary


def _assert_submission_policy(
    *, cfg: ProposalSubmissionConfig, security: SecurityProfileConfig, submit: bool
) -> None:
    if not submit:
        return
    if not cfg.submit_enabled:
        raise RuntimeError(
            "Proposal submission was requested, but proposal_submission.submit_enabled=false."
        )
    if not security.allow_proposal_submission:
        raise RuntimeError(
            "Proposal submission was requested, but "
            "security_profile.allow_proposal_submission=false."
        )
    if security.allow_runtime_mutation:
        raise RuntimeError(
            "Runtime mutation must remain disabled for this agent runner."
        )


def _error_result(payload: Mapping[str, Any], *, code: str, error: str) -> JsonDict:
    return {
        "alias_value": payload.get("alias_value"),
        "canonical_value": payload.get("canonical_value"),
        "slot": payload.get("slot"),
        "confidence": payload.get("confidence"),
        "idempotency_key": payload.get("idempotency_key"),
        "status": "error",
        "error_code": code,
        "error": error,
        "submitted": False,
    }


def _safe_float(value: Any, *, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalize_value(value: Any) -> str:
    return str(value or "").strip().lower()
