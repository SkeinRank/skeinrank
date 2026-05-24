"""Safe validation/submission bridge for OpenRouter alias scout proposals.

Patch 41B keeps the agent governed: model judgments can become proposal
payloads, but every payload must be validated through the existing SkeinRank
``/v1/tools/validate-alias`` endpoint before any optional submission through
``/v1/tools/suggest-alias``. Runtime mutation and snapshot publishing remain
out of scope for this runner.
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
        )


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
        "eligible_proposals": len(ready_payloads),
        "candidate_aliases": [payload["alias_value"] for payload in ready_payloads],
        "will_validate_aliases": True,
        "will_submit_aliases": bool(submit and cfg.submit_enabled),
        "safety": {
            "validate_before_submit": True,
            "snapshot_publish_enabled": False,
            "runtime_mutation_enabled": False,
            "direct_dictionary_write_enabled": False,
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
    result: JsonDict = {
        "alias_value": payload.get("alias_value"),
        "canonical_value": payload.get("canonical_value"),
        "slot": payload.get("slot"),
        "confidence": payload.get("confidence"),
        "idempotency_key": payload.get("idempotency_key"),
        "validation_status": validation_status,
        "validation_response": validation_response,
        "submitted": False,
        "status": "validated",
    }
    if validation_status != cfg.require_validation_status:
        result["status"] = "validation_not_passing"
        result["submission_skipped_reason"] = (
            "validation_status_mismatch:"
            f" expected {cfg.require_validation_status!r}, got {validation_status!r}"
        )
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
        "validation_not_passing": 0,
        "submitted": 0,
        "created": 0,
        "idempotent_retries": 0,
        "errors": 0,
    }
    for result in results:
        status = result.get("status")
        if status in {"validated", "submitted", "validation_not_passing"}:
            summary["validated"] += 1
        if result.get("validation_status") == "passed":
            summary["validation_passed"] += 1
        if status == "validation_not_passing":
            summary["validation_not_passing"] += 1
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
            "Proposal submission was requested, but security_profile.allow_proposal_submission=false."
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
