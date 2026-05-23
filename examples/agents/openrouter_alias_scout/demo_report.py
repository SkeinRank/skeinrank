"""End-to-end local demo report for the OpenRouter alias scout example.

Patch 40K stitches together the deterministic local stages from patches 40H and
40I: failed-query candidate discovery, evidence sampling, compact candidate
packs, and review prompt preparation. It intentionally does not call OpenRouter,
Elasticsearch, or SkeinRank API endpoints.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

try:  # pragma: no cover - import style depends on how the example is executed.
    from .candidate_discovery import (
        AliasCandidate,
        CandidateDiscoveryConfig,
        build_candidate_fact_pack,
        discover_alias_candidates,
    )
    from .evidence_sampler import (
        EvidenceSamplerConfig,
        EvidenceWindow,
        build_candidate_evidence_pack,
        sample_evidence_windows,
    )
    from .prompts import build_alias_review_prompt
except ImportError:  # pragma: no cover
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from candidate_discovery import (
        AliasCandidate,
        CandidateDiscoveryConfig,
        build_candidate_fact_pack,
        discover_alias_candidates,
    )
    from evidence_sampler import (
        EvidenceSamplerConfig,
        EvidenceWindow,
        build_candidate_evidence_pack,
        sample_evidence_windows,
    )
    from prompts import build_alias_review_prompt

JsonDict = dict[str, Any]


@dataclass(frozen=True)
class DemoReportConfig:
    """Local-only run report settings."""

    max_candidates_for_review: int = 5
    include_prompt_previews: bool = False
    prompt_preview_chars: int = 800

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any] | None) -> "DemoReportConfig":
        """Create config from optional JSON config values."""

        if not raw:
            return cls()
        return cls(
            max_candidates_for_review=int(
                raw.get("max_candidates_for_review", cls.max_candidates_for_review)
            ),
            include_prompt_previews=bool(
                raw.get("include_prompt_previews", cls.include_prompt_previews)
            ),
            prompt_preview_chars=int(
                raw.get("prompt_preview_chars", cls.prompt_preview_chars)
            ),
        )


def build_alias_scout_demo_report(
    failed_queries: Sequence[Mapping[str, Any]],
    evidence_records: Sequence[Mapping[str, Any]],
    *,
    candidate_config: CandidateDiscoveryConfig | None = None,
    evidence_config: EvidenceSamplerConfig | None = None,
    demo_config: DemoReportConfig | None = None,
    binding_id: int | None = None,
    profile_name: str | None = None,
    proposal_source_name: str = "openrouter-alias-scout",
    openrouter_model: str = "openai/gpt-4o-mini",
) -> JsonDict:
    """Build a local E2E dry-run report for the alias scout workflow.

    The report is intentionally safe: it never submits proposals, never calls a
    model, and never mutates SkeinRank state. It only prepares the review queue
    that a later model/tool-execution patch can consume.
    """

    cfg = demo_config or DemoReportConfig()
    discovery_cfg = candidate_config or CandidateDiscoveryConfig()
    sampler_cfg = evidence_config or EvidenceSamplerConfig()
    candidates = discover_alias_candidates(failed_queries, config=discovery_cfg)
    scoped_candidates = candidates[: cfg.max_candidates_for_review]

    review_queue = [
        _build_review_item(
            candidate,
            evidence_records,
            evidence_config=sampler_cfg,
            demo_config=cfg,
            binding_id=binding_id,
            profile_name=profile_name,
            proposal_source_name=proposal_source_name,
        )
        for candidate in scoped_candidates
    ]
    ready_items = [
        item for item in review_queue if item["review_status"] == "ready_for_llm_review"
    ]
    total_windows = sum(int(item["evidence_windows_found"]) for item in review_queue)
    candidates_with_evidence = sum(
        1 for item in review_queue if int(item["evidence_windows_found"]) > 0
    )

    return {
        "schema_version": "skeinrank.agent_demo_report.v1",
        "runner": "openrouter_alias_scout",
        "dry_run": True,
        "llm_enabled": False,
        "openrouter_calls": False,
        "skeinrank_api_calls": False,
        "elasticsearch_calls": False,
        "proposal_submission_enabled": False,
        "proposals_submitted": 0,
        "openrouter_model": openrouter_model,
        "proposal_source_name": proposal_source_name,
        "binding_id": binding_id,
        "profile_name": profile_name,
        "input_summary": {
            "failed_queries_loaded": len(failed_queries),
            "evidence_records_loaded": len(evidence_records),
            "max_candidates_for_review": cfg.max_candidates_for_review,
        },
        "candidate_summary": {
            "candidates_discovered": len(candidates),
            "candidates_in_review_queue": len(review_queue),
            "candidates_with_evidence": candidates_with_evidence,
            "total_evidence_windows": total_windows,
            "top_surfaces": [candidate.surface for candidate in scoped_candidates],
        },
        "source_quality": {
            "ready_for_llm_review": len(ready_items),
            "needs_more_evidence": len(review_queue) - len(ready_items),
            "evidence_coverage": _safe_ratio(
                candidates_with_evidence, len(review_queue)
            ),
            "proposal_precision": None,
            "proposal_recall": None,
            "note": (
                "Offline demo signal only. Precision/recall require reviewed "
                "proposals or qrels in later patches."
            ),
        },
        "review_queue": review_queue,
        "safety": {
            "agent_may_mutate_runtime": False,
            "allowed_next_action": "model_review_then_skeinrank_validate_alias",
            "blocked_actions": [
                "direct_dictionary_write",
                "snapshot_publish",
                "direct_git_push",
            ],
        },
        "next_steps": [
            "Run model review only on review_queue candidate packs.",
            "Validate any propose judgment through /v1/tools/validate-alias.",
            "Submit only pending proposals through /v1/tools/suggest-alias.",
            "Keep snapshot publishing in the reviewed governance workflow.",
        ],
    }


def build_demo_review_prompt(
    failed_queries: Sequence[Mapping[str, Any]],
    evidence_records: Sequence[Mapping[str, Any]],
    *,
    candidate_config: CandidateDiscoveryConfig | None = None,
    evidence_config: EvidenceSamplerConfig | None = None,
    binding_id: int | None = None,
    profile_name: str | None = None,
) -> str:
    """Build the first real-sample review prompt without calling a model."""

    candidates = discover_alias_candidates(
        failed_queries, config=candidate_config or CandidateDiscoveryConfig()
    )
    if not candidates:
        raise RuntimeError("No candidates discovered from failed-query input.")
    windows = sample_evidence_windows(
        candidates[0].surface,
        evidence_records,
        config=evidence_config or EvidenceSamplerConfig(),
    )
    if windows:
        pack = build_candidate_evidence_pack(
            candidates[0],
            windows,
            binding_id=binding_id,
            profile_name=profile_name,
        )
    else:
        pack = build_candidate_fact_pack(
            candidates[0],
            binding_id=binding_id,
            profile_name=profile_name,
        )
    return build_alias_review_prompt(pack)


def _build_review_item(
    candidate: AliasCandidate,
    evidence_records: Sequence[Mapping[str, Any]],
    *,
    evidence_config: EvidenceSamplerConfig,
    demo_config: DemoReportConfig,
    binding_id: int | None,
    profile_name: str | None,
    proposal_source_name: str,
) -> JsonDict:
    windows = sample_evidence_windows(
        candidate.surface, evidence_records, config=evidence_config
    )
    if windows:
        candidate_pack = build_candidate_evidence_pack(
            candidate,
            windows,
            binding_id=binding_id,
            profile_name=profile_name,
        )
        review_status = "ready_for_llm_review"
    else:
        candidate_pack = build_candidate_fact_pack(
            candidate,
            binding_id=binding_id,
            profile_name=profile_name,
        )
        review_status = "needs_more_evidence"

    item: JsonDict = {
        "candidate_alias": candidate.surface,
        "review_status": review_status,
        "score": round(candidate.score, 4),
        "weighted_count": round(candidate.weighted_count, 4),
        "document_frequency": candidate.document_frequency,
        "discovery_reasons": list(candidate.reasons),
        "evidence_windows_found": len(windows),
        "evidence_total_chars": sum(len(window.text) for window in windows),
        "idempotency_key": make_review_idempotency_key(
            source_name=proposal_source_name,
            binding_id=binding_id,
            profile_name=profile_name,
            candidate_alias=candidate.surface,
        ),
        "candidate_pack": candidate_pack,
        "evidence_preview": [_compact_window(window) for window in windows[:3]],
    }
    if demo_config.include_prompt_previews:
        prompt = build_alias_review_prompt(candidate_pack)
        item["review_prompt_preview"] = _truncate(
            prompt, demo_config.prompt_preview_chars
        )
    return item


def make_review_idempotency_key(
    *,
    source_name: str,
    binding_id: int | None,
    profile_name: str | None,
    candidate_alias: str,
) -> str:
    """Build a deterministic key for future review/proposal retries."""

    scope = (
        f"binding:{binding_id}"
        if binding_id is not None
        else f"profile:{profile_name or 'unknown'}"
    )
    digest = sha256(candidate_alias.strip().lower().encode("utf-8")).hexdigest()[:16]
    return f"{source_name}:{scope}:candidate:{digest}"


def _compact_window(window: EvidenceWindow) -> JsonDict:
    return {
        "source_id": window.source_id,
        "source_type": window.source_type,
        "field": window.field,
        "text": window.text,
    }


def _safe_ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)


def _truncate(text: str, max_chars: int) -> str:
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    return f"{text[: max_chars - 3]}..."
