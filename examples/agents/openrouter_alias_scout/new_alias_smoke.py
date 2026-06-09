"""Controlled new-alias proposal smoke test for the OpenRouter alias scout.

The smoke test proves the safe write path for a brand-new alias without requiring
a real OpenRouter call. The smoke report is shaped like the normal
``skeinrank.agent_llm_review_report.v1`` output, then uses the existing
SkeinRank tool endpoints:

1. ``POST /v1/tools/validate-alias``
2. ``POST /v1/tools/suggest-alias`` when explicitly requested
3. one optional idempotency retry against ``/v1/tools/suggest-alias``

The smoke test creates only a pending proposal. It never writes directly to the
dictionary, never publishes snapshots, and never mutates runtime artifacts.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

try:  # pragma: no cover - import style depends on how the example is executed.
    from .proposal_submission import (
        ProposalSubmissionConfig,
        classify_validation_decision,
    )
except ImportError:  # pragma: no cover
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from proposal_submission import (
        ProposalSubmissionConfig,
        classify_validation_decision,
    )

JsonDict = dict[str, Any]


class NewAliasSmokeClient(Protocol):
    """Subset of the SkeinRank client used by the smoke test."""

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
class NewAliasSmokeConfig:
    """Config for a deterministic new-alias smoke proposal."""

    profile_name: str = "infra_incidents"
    binding_id: int | None = None
    canonical_value: str = "postgresql"
    alias_value: str = "pgx"
    slot: str = "database"
    confidence: float = 0.91
    context: str = "Controlled smoke proposal for a new PostgreSQL alias."
    proposal_source_name: str = "openrouter-alias-scout-smoke"
    idempotency_key: str | None = None
    verify_idempotency_retry: bool = True
    source_type: str = "smoke_test"

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any] | None) -> "NewAliasSmokeConfig":
        """Create config from optional JSON config values."""

        if not raw:
            return cls()
        binding_id = raw.get("binding_id")
        return cls(
            profile_name=str(raw.get("profile_name", cls.profile_name)),
            binding_id=int(binding_id) if binding_id is not None else None,
            canonical_value=str(raw.get("canonical_value", cls.canonical_value)),
            alias_value=str(raw.get("alias_value", cls.alias_value)),
            slot=str(raw.get("slot", cls.slot)),
            confidence=float(raw.get("confidence", cls.confidence)),
            context=str(raw.get("context", cls.context)),
            proposal_source_name=str(
                raw.get("proposal_source_name", cls.proposal_source_name)
            ),
            idempotency_key=(
                str(raw["idempotency_key"]) if raw.get("idempotency_key") else None
            ),
            verify_idempotency_retry=bool(
                raw.get("verify_idempotency_retry", cls.verify_idempotency_retry)
            ),
            source_type=str(raw.get("source_type", cls.source_type)),
        )

    @property
    def resolved_idempotency_key(self) -> str:
        """Return a stable idempotency key for smoke runs."""

        if self.idempotency_key:
            return self.idempotency_key
        return (
            f"{self.proposal_source_name}:profile:{self.profile_name}:"
            f"alias:{self.alias_value}:canonical:{self.canonical_value}"
        )


def build_new_alias_smoke_llm_report(config: NewAliasSmokeConfig) -> JsonDict:
    """Build a proposal-ready LLM review report without calling OpenRouter."""

    payload = _proposal_payload(config)
    return {
        "schema_version": "skeinrank.agent_llm_review_report.v1",
        "runner": "openrouter_alias_scout",
        "llm_enabled": False,
        "openrouter_calls": False,
        "skeinrank_api_calls": False,
        "proposal_submission_enabled": False,
        "safety": {
            "agent_may_mutate_runtime": False,
            "proposal_payloads_require_skeinrank_validation": True,
            "blocked_actions": [
                "direct_dictionary_write",
                "snapshot_publish",
                "direct_git_push",
                "runtime_mutation",
            ],
        },
        "reviewed_items": [
            {
                "candidate_alias": config.alias_value,
                "proposal_ready_for_validation": True,
                "proposal_payload": payload,
                "judgment": {
                    "action": "propose",
                    "alias_value": config.alias_value,
                    "canonical_value": config.canonical_value,
                    "slot": config.slot,
                    "confidence": config.confidence,
                    "context": config.context,
                    "reason": "Controlled smoke fixture for validating safe proposal submission.",
                    "risk_flags": [],
                },
            }
        ],
    }


def build_new_alias_smoke_plan(
    config: NewAliasSmokeConfig, *, submit: bool = False
) -> JsonDict:
    """Build an offline smoke plan without network calls."""

    return {
        "schema_version": "skeinrank.agent_new_alias_smoke_plan.v1",
        "runner": "openrouter_alias_scout",
        "skeinrank_api_calls": False,
        "smoke_alias": config.alias_value,
        "canonical_value": config.canonical_value,
        "slot": config.slot,
        "profile_name": config.profile_name,
        "binding_id": config.binding_id,
        "idempotency_key": config.resolved_idempotency_key,
        "will_validate_alias": True,
        "will_submit_alias": submit,
        "will_verify_idempotency_retry": bool(
            submit and config.verify_idempotency_retry
        ),
        "safety": _smoke_safety(submit=submit),
    }


def run_new_alias_smoke_test(
    *,
    client: NewAliasSmokeClient,
    config: NewAliasSmokeConfig,
    submit: bool = False,
) -> JsonDict:
    """Run a controlled validate/submit/idempotency smoke test."""

    payload = _proposal_payload(config)
    validation_response = client.validate_alias(**_validate_kwargs(payload))
    decision = classify_validation_decision(
        validation_response,
        payload=payload,
        config=ProposalSubmissionConfig(
            min_confidence=0.0,
            submit_enabled=True,
            treat_existing_alias_as_idempotent=True,
            manual_review_on_warning=True,
        ),
    )
    result: JsonDict = {
        "alias_value": config.alias_value,
        "canonical_value": config.canonical_value,
        "slot": config.slot,
        "confidence": config.confidence,
        "idempotency_key": config.resolved_idempotency_key,
        "validation_decision": decision.as_dict(),
        "validation_response": validation_response,
        "status": decision.category,
        "submitted": False,
        "created": False,
        "idempotent_retry_verified": False,
    }

    if not submit:
        result["submission_skipped_reason"] = "submit_flag_not_set"
    elif decision.submit_allowed:
        submission_response = client.suggest_alias(**_suggest_kwargs(payload))
        result["submitted"] = True
        result["status"] = "submitted"
        result["submission_response"] = submission_response
        result["created"] = _created_from_response(submission_response)
        if config.verify_idempotency_retry:
            retry_response = client.suggest_alias(**_suggest_kwargs(payload))
            result["idempotency_retry_response"] = retry_response
            result["idempotent_retry_verified"] = (
                _created_from_response(retry_response) is False
            )
    else:
        result["submission_skipped_reason"] = decision.reason

    return {
        "schema_version": "skeinrank.agent_new_alias_smoke_report.v1",
        "runner": "openrouter_alias_scout",
        "skeinrank_api_calls": True,
        "proposal_submission_requested": submit,
        "runtime_mutation_enabled": False,
        "snapshot_publish_enabled": False,
        "safety": _smoke_safety(submit=submit),
        "summary": _summarize_smoke_result(result),
        "result": result,
    }


def _proposal_payload(config: NewAliasSmokeConfig) -> JsonDict:
    source_payload: JsonDict = {
        "source_type": config.source_type,
        "smoke_test": True,
        "candidate_alias": config.alias_value,
        "possible_canonical": config.canonical_value,
        "evidence": [
            f"{config.alias_value} observed in controlled validation smoke input.",
            f"Expected canonical mapping is {config.canonical_value}.",
        ],
    }
    payload: JsonDict = {
        "alias_value": config.alias_value,
        "canonical_value": config.canonical_value,
        "slot": config.slot,
        "confidence": config.confidence,
        "context": config.context,
        "profile_name": config.profile_name,
        "proposal_source_name": config.proposal_source_name,
        "idempotency_key": config.resolved_idempotency_key,
        "source_payload": source_payload,
    }
    if config.binding_id is not None:
        payload["binding_id"] = config.binding_id
    return payload


def _validate_kwargs(payload: Mapping[str, Any]) -> JsonDict:
    return {
        "canonical_value": str(payload["canonical_value"]),
        "alias_value": str(payload["alias_value"]),
        "slot": str(payload["slot"]),
        "binding_id": payload.get("binding_id"),
        "profile_name": payload.get("profile_name"),
        "confidence": float(payload.get("confidence", 1.0)),
        "proposal_source_name": payload.get("proposal_source_name"),
        "idempotency_key": payload.get("idempotency_key"),
        "source_payload": payload.get("source_payload"),
    }


def _suggest_kwargs(payload: Mapping[str, Any]) -> JsonDict:
    kwargs = _validate_kwargs(payload)
    context = payload.get("context")
    if context:
        kwargs["context"] = str(context)
    return kwargs


def _created_from_response(response: Any) -> bool | None:
    if isinstance(response, Mapping) and isinstance(response.get("created"), bool):
        return bool(response["created"])
    return None


def _summarize_smoke_result(result: Mapping[str, Any]) -> JsonDict:
    return {
        "validated": 1,
        "submitted": 1 if result.get("submitted") else 0,
        "created": 1 if result.get("created") is True else 0,
        "idempotent_retry_verified": 1
        if result.get("idempotent_retry_verified")
        else 0,
        "manual_review_required": 1
        if result.get("status") == "manual_review_required"
        else 0,
        "blocked": 1 if result.get("status") == "blocked" else 0,
        "idempotent_existing_alias": 1
        if result.get("status") == "idempotent_existing_alias"
        else 0,
    }


def _smoke_safety(*, submit: bool) -> JsonDict:
    return {
        "validate_before_submit": True,
        "submit_requires_explicit_flag": True,
        "submit_requested": submit,
        "agent_may_mutate_runtime": False,
        "direct_dictionary_write_enabled": False,
        "snapshot_publish_enabled": False,
        "runtime_mutation_enabled": False,
        "created_object_type": "pending_proposal" if submit else None,
    }
