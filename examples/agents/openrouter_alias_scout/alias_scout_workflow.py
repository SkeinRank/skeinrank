"""Stateful OpenRouter alias-scout workflow for Patch 40J.

This module is intentionally dependency-light. It models the same node boundaries
that a future LangGraph wrapper can use, but does not require `langgraph` at
runtime. The workflow executes model review only; it does not mutate SkeinRank
state unless a later patch explicitly enables validation/submission policies.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:  # pragma: no cover - import style depends on how the example is executed.
    from .candidate_discovery import CandidateDiscoveryConfig
    from .demo_report import DemoReportConfig, build_alias_scout_demo_report
    from .evidence_sampler import EvidenceSamplerConfig
    from .openrouter_client import (
        OpenRouterClient,
        extract_first_message_content,
    )
    from .prompts import SYSTEM_PROMPT, build_alias_review_prompt
    from .structured_output import (
        AliasReviewOutputError,
        judgment_to_proposal_payload,
        parse_alias_review_output,
    )
except ImportError:  # pragma: no cover
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from candidate_discovery import CandidateDiscoveryConfig
    from demo_report import DemoReportConfig, build_alias_scout_demo_report
    from evidence_sampler import EvidenceSamplerConfig
    from openrouter_client import OpenRouterClient, extract_first_message_content
    from prompts import SYSTEM_PROMPT, build_alias_review_prompt
    from structured_output import (
        AliasReviewOutputError,
        judgment_to_proposal_payload,
        parse_alias_review_output,
    )

JsonDict = dict[str, Any]
WORKFLOW_NODES = (
    "collect_failed_queries",
    "discover_candidates",
    "sample_evidence",
    "build_review_queue",
    "openrouter_review",
    "parse_structured_judgment",
    "prepare_proposal_payload",
    "write_run_report",
)


@dataclass(frozen=True)
class LlmReviewConfig:
    """OpenRouter execution settings for the alias scout workflow."""

    max_candidates: int = 3
    min_confidence_to_prepare_proposal: float = 0.75
    temperature: float = 0.0
    max_tokens: int = 700
    include_tools: bool = False
    response_format_json: bool = True
    submit_proposals: bool = False

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any] | None) -> "LlmReviewConfig":
        """Create config from optional JSON config values."""

        if not raw:
            return cls()
        return cls(
            max_candidates=int(raw.get("max_candidates", cls.max_candidates)),
            min_confidence_to_prepare_proposal=float(
                raw.get(
                    "min_confidence_to_prepare_proposal",
                    cls.min_confidence_to_prepare_proposal,
                )
            ),
            temperature=float(raw.get("temperature", cls.temperature)),
            max_tokens=int(raw.get("max_tokens", cls.max_tokens)),
            include_tools=bool(raw.get("include_tools", cls.include_tools)),
            response_format_json=bool(
                raw.get("response_format_json", cls.response_format_json)
            ),
            submit_proposals=bool(raw.get("submit_proposals", cls.submit_proposals)),
        )


def build_llm_review_plan(
    failed_queries: Sequence[Mapping[str, Any]],
    evidence_records: Sequence[Mapping[str, Any]],
    *,
    candidate_config: CandidateDiscoveryConfig | None = None,
    evidence_config: EvidenceSamplerConfig | None = None,
    demo_config: DemoReportConfig | None = None,
    llm_config: LlmReviewConfig | None = None,
    binding_id: int | None = None,
    profile_name: str | None = None,
    proposal_source_name: str = "openrouter-alias-scout",
    openrouter_model: str = "openai/gpt-4o-mini",
) -> JsonDict:
    """Build a dry-run plan for real OpenRouter review execution."""

    cfg = llm_config or LlmReviewConfig()
    demo_report = build_alias_scout_demo_report(
        failed_queries,
        evidence_records,
        candidate_config=candidate_config,
        evidence_config=evidence_config,
        demo_config=demo_config,
        binding_id=binding_id,
        profile_name=profile_name,
        proposal_source_name=proposal_source_name,
        openrouter_model=openrouter_model,
    )
    ready_queue = [
        item
        for item in demo_report["review_queue"]
        if item["review_status"] == "ready_for_llm_review"
    ][: cfg.max_candidates]
    return {
        "schema_version": "skeinrank.agent_llm_review_plan.v1",
        "runner": "openrouter_alias_scout",
        "llm_enabled": True,
        "openrouter_calls": False,
        "openrouter_model": openrouter_model,
        "proposal_submission_enabled": cfg.submit_proposals,
        "workflow_engine": "dependency_light_state_machine",
        "langgraph_ready": True,
        "workflow_nodes": list(WORKFLOW_NODES),
        "max_candidates": cfg.max_candidates,
        "candidates_ready_for_llm": len(ready_queue),
        "candidate_aliases": [item["candidate_alias"] for item in ready_queue],
        "safety": {
            "will_call_openrouter_when_llm_review_flag_is_used": True,
            "will_submit_proposals": cfg.submit_proposals,
            "default_submit_proposals": False,
        },
    }


def run_openrouter_llm_review_workflow(
    failed_queries: Sequence[Mapping[str, Any]],
    evidence_records: Sequence[Mapping[str, Any]],
    *,
    openrouter_client: OpenRouterClient,
    candidate_config: CandidateDiscoveryConfig | None = None,
    evidence_config: EvidenceSamplerConfig | None = None,
    demo_config: DemoReportConfig | None = None,
    llm_config: LlmReviewConfig | None = None,
    binding_id: int | None = None,
    profile_name: str | None = None,
    proposal_source_name: str = "openrouter-alias-scout",
    openrouter_model: str = "openai/gpt-4o-mini",
    tools: Sequence[Mapping[str, Any]] | None = None,
) -> JsonDict:
    """Run model review for ready candidates and return a structured report.

    This is the first live OpenRouter execution path. It deliberately stops at
    proposal payload preparation; later security/budget/evaluation patches can
    decide when to validate or submit proposals to SkeinRank.
    """

    cfg = llm_config or LlmReviewConfig()
    demo_report = build_alias_scout_demo_report(
        failed_queries,
        evidence_records,
        candidate_config=candidate_config,
        evidence_config=evidence_config,
        demo_config=demo_config,
        binding_id=binding_id,
        profile_name=profile_name,
        proposal_source_name=proposal_source_name,
        openrouter_model=openrouter_model,
    )
    ready_queue = [
        item
        for item in demo_report["review_queue"]
        if item["review_status"] == "ready_for_llm_review"
    ][: cfg.max_candidates]

    reviewed_items: list[JsonDict] = []
    counters: Counter[str] = Counter()
    for item in ready_queue:
        reviewed = _review_one_item(
            item,
            client=openrouter_client,
            cfg=cfg,
            openrouter_model=openrouter_model,
            proposal_source_name=proposal_source_name,
            binding_id=binding_id,
            profile_name=profile_name,
            tools=tools,
        )
        reviewed_items.append(reviewed)
        counters[str(reviewed["judgment"].get("action", "error"))] += 1

    prepared = [
        item
        for item in reviewed_items
        if item.get("proposal_payload") is not None
        and item.get("proposal_ready_for_validation") is True
    ]
    return {
        "schema_version": "skeinrank.agent_llm_review_report.v1",
        "runner": "openrouter_alias_scout",
        "llm_enabled": True,
        "openrouter_calls": True,
        "skeinrank_api_calls": False,
        "proposal_submission_enabled": cfg.submit_proposals,
        "proposals_submitted": 0,
        "openrouter_model": openrouter_model,
        "workflow_engine": "dependency_light_state_machine",
        "langgraph_ready": True,
        "workflow_nodes": list(WORKFLOW_NODES),
        "input_summary": demo_report["input_summary"],
        "candidate_summary": demo_report["candidate_summary"],
        "llm_review_summary": {
            "candidates_sent_to_model": len(reviewed_items),
            "proposals_prepared": len(prepared),
            "actions": dict(sorted(counters.items())),
            "min_confidence_to_prepare_proposal": (
                cfg.min_confidence_to_prepare_proposal
            ),
        },
        "reviewed_items": reviewed_items,
        "safety": {
            "agent_may_mutate_runtime": False,
            "proposal_payloads_require_skeinrank_validation": True,
            "blocked_actions": [
                "direct_dictionary_write",
                "snapshot_publish",
                "direct_git_push",
            ],
        },
    }


def _review_one_item(
    item: Mapping[str, Any],
    *,
    client: OpenRouterClient,
    cfg: LlmReviewConfig,
    openrouter_model: str,
    proposal_source_name: str,
    binding_id: int | None,
    profile_name: str | None,
    tools: Sequence[Mapping[str, Any]] | None,
) -> JsonDict:
    candidate_pack = item["candidate_pack"]
    prompt = build_alias_review_prompt(candidate_pack)
    response = client.create_chat_completion(
        model=openrouter_model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        temperature=cfg.temperature,
        max_tokens=cfg.max_tokens,
        tools=tools if cfg.include_tools else None,
        response_format={"type": "json_object"} if cfg.response_format_json else None,
    )
    content = extract_first_message_content(response)
    try:
        judgment = parse_alias_review_output(content)
        judgment_payload = judgment.to_dict()
        parse_error: str | None = None
    except AliasReviewOutputError as exc:
        judgment = None
        judgment_payload = {
            "action": "error",
            "confidence": 0.0,
            "reason": "Model response failed strict structured-output validation.",
            "risk_flags": ["parse_error"],
        }
        parse_error = str(exc)

    proposal_payload: JsonDict | None = None
    proposal_ready = False
    if judgment is not None and judgment.action == "propose":
        if judgment.confidence >= cfg.min_confidence_to_prepare_proposal:
            proposal_payload = judgment_to_proposal_payload(
                judgment,
                binding_id=binding_id,
                profile_name=profile_name,
                proposal_source_name=proposal_source_name,
                idempotency_key=str(item["idempotency_key"]),
                source_payload=candidate_pack,
            )
            proposal_ready = True

    reviewed: JsonDict = {
        "candidate_alias": item["candidate_alias"],
        "idempotency_key": item["idempotency_key"],
        "judgment": judgment_payload,
        "proposal_ready_for_validation": proposal_ready,
        "proposal_payload": proposal_payload,
        "openrouter_response_id": response.get("id"),
        "openrouter_usage": response.get("usage"),
    }
    if parse_error:
        reviewed["parse_error"] = parse_error
    return reviewed
