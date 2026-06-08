"""Agent evaluation loop for the OpenRouter alias-scout example.

The evaluation loop turns demo/LLM review reports into a deterministic quality
report. It is deliberately offline: it does not submit proposals, publish
snapshots, or call OpenRouter/SkeinRank APIs. The goal is to make agent quality
measurable before scheduled jobs use the runner.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

JsonDict = dict[str, Any]
_VALID_OUTCOMES = {
    "accepted",
    "rejected",
    "blocked",
    "ambiguous",
    "noisy",
    "conflict",
    "pending",
}


@dataclass(frozen=True)
class AgentEvaluationConfig:
    """Settings for local agent evaluation reports."""

    min_confidence_for_review_ready: float = 0.75
    include_reviewed_items: bool = True
    include_candidate_packs: bool = False
    max_items: int = 50
    qrels_enabled: bool = False
    snapshot_eval_enabled: bool = False

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any] | None) -> "AgentEvaluationConfig":
        """Create config from optional JSON config values."""

        if not raw:
            return cls()
        return cls(
            min_confidence_for_review_ready=float(
                raw.get(
                    "min_confidence_for_review_ready",
                    cls.min_confidence_for_review_ready,
                )
            ),
            include_reviewed_items=bool(
                raw.get("include_reviewed_items", cls.include_reviewed_items)
            ),
            include_candidate_packs=bool(
                raw.get("include_candidate_packs", cls.include_candidate_packs)
            ),
            max_items=int(raw.get("max_items", cls.max_items)),
            qrels_enabled=bool(raw.get("qrels_enabled", cls.qrels_enabled)),
            snapshot_eval_enabled=bool(
                raw.get("snapshot_eval_enabled", cls.snapshot_eval_enabled)
            ),
        )

    def to_report(self) -> JsonDict:
        """Return JSON-safe config metadata."""

        return {
            "min_confidence_for_review_ready": self.min_confidence_for_review_ready,
            "include_reviewed_items": self.include_reviewed_items,
            "include_candidate_packs": self.include_candidate_packs,
            "max_items": self.max_items,
            "qrels_enabled": self.qrels_enabled,
            "snapshot_eval_enabled": self.snapshot_eval_enabled,
        }


def load_json_report(path: Path) -> JsonDict:
    """Load a JSON report from disk."""

    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"Expected JSON object report at {path}")
    return raw


def load_evaluation_outcomes(path: Path) -> list[JsonDict]:
    """Load optional human/policy outcome rows from JSONL."""

    rows: list[JsonDict] = []
    if not path.exists():
        return rows
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), 1
    ):
        if not line.strip():
            continue
        raw = json.loads(line)
        if not isinstance(raw, dict):
            raise ValueError(f"Invalid outcome row at {path}:{line_number}")
        outcome = str(raw.get("outcome", "")).strip().lower()
        if outcome not in _VALID_OUTCOMES:
            raise ValueError(
                f"Invalid outcome {outcome!r} at {path}:{line_number}. "
                f"Expected one of {sorted(_VALID_OUTCOMES)}."
            )
        rows.append(dict(raw, outcome=outcome))
    return rows


def build_agent_evaluation_report(
    *,
    demo_report: Mapping[str, Any] | None = None,
    llm_review_report: Mapping[str, Any] | None = None,
    outcome_records: Sequence[Mapping[str, Any]] | None = None,
    evaluation_config: AgentEvaluationConfig | None = None,
) -> JsonDict:
    """Build a local evaluation report from demo/LLM review artifacts.

    The report can be produced after a dry-run demo or after a saved live LLM
    review report. Human/policy outcomes are optional and may be added later from
    proposal review exports. No external calls are performed.
    """

    cfg = evaluation_config or AgentEvaluationConfig()
    demo = dict(demo_report or {})
    llm_report = dict(llm_review_report or {})
    outcomes = [dict(row) for row in (outcome_records or [])]
    candidate_summary = _merge_candidate_summary(demo, llm_report)
    reviewed_items = _reviewed_items_from_reports(demo, llm_report)[: cfg.max_items]
    llm_quality = _build_llm_quality(llm_report, reviewed_items, cfg)
    outcome_summary = _build_outcome_summary(outcomes, reviewed_items)
    cost_summary = _build_cost_summary(llm_report)
    evidence_quality = _build_evidence_quality(demo, llm_report, reviewed_items)
    proposal_quality = _build_proposal_quality(llm_report, reviewed_items, outcomes)

    return {
        "schema_version": "skeinrank.agent_evaluation_report.v1",
        "runner": "openrouter_alias_scout",
        "evaluation_mode": "llm_review" if llm_report else "demo_dry_run",
        "openrouter_calls": False,
        "skeinrank_api_calls": False,
        "proposal_submission_enabled": False,
        "snapshot_publish_enabled": False,
        "runtime_mutation_enabled": False,
        "config": cfg.to_report(),
        "input_summary": {
            "demo_report_schema": demo.get("schema_version"),
            "llm_review_report_schema": llm_report.get("schema_version"),
            "outcome_records_loaded": len(outcomes),
            "reviewed_items_evaluated": len(reviewed_items),
        },
        "candidate_summary": candidate_summary,
        "evidence_quality": evidence_quality,
        "llm_quality": llm_quality,
        "proposal_quality": proposal_quality,
        "outcome_summary": outcome_summary,
        "cost_summary": cost_summary,
        "before_after_snapshot_evaluation": {
            "enabled": False,
            "reason": (
                "The offline evaluation report does not publish snapshots. Run snapshot before/after "
                "evaluation after approved proposals are applied in the governed flow."
            ),
            "requires": [
                "approved proposal batch",
                "before snapshot artifact",
                "after snapshot artifact",
                "optional qrels or sample-query set",
            ],
        },
        "quality_gate": _build_quality_gate(
            llm_quality, proposal_quality, outcome_summary
        ),
        "reviewed_items": _compact_reviewed_items(reviewed_items, cfg),
        "safety": {
            "agent_may_mutate_runtime": False,
            "evaluation_is_offline": True,
            "blocked_actions": [
                "direct_dictionary_write",
                "snapshot_publish",
                "direct_git_push",
                "runtime_mutation",
            ],
        },
        "next_steps": [
            "Use accepted/rejected/blocked outcomes to compare prompt/model versions.",
            "Keep proposal submission behind SkeinRank validation and security policy.",
            "Run snapshot before/after evaluation only after approved proposals are applied.",
        ],
    }


def _merge_candidate_summary(
    demo_report: Mapping[str, Any], llm_review_report: Mapping[str, Any]
) -> JsonDict:
    candidate_summary = {}
    for report in (demo_report, llm_review_report):
        raw = report.get("candidate_summary")
        if isinstance(raw, Mapping):
            candidate_summary.update(raw)
    return {
        "candidates_discovered": int(candidate_summary.get("candidates_discovered", 0)),
        "candidates_in_review_queue": int(
            candidate_summary.get("candidates_in_review_queue", 0)
        ),
        "candidates_with_evidence": int(
            candidate_summary.get("candidates_with_evidence", 0)
        ),
        "total_evidence_windows": int(
            candidate_summary.get("total_evidence_windows", 0)
        ),
        "top_surfaces": list(candidate_summary.get("top_surfaces", [])),
    }


def _reviewed_items_from_reports(
    demo_report: Mapping[str, Any], llm_review_report: Mapping[str, Any]
) -> list[JsonDict]:
    if isinstance(llm_review_report.get("reviewed_items"), list):
        return [
            dict(item)
            for item in llm_review_report["reviewed_items"]
            if isinstance(item, Mapping)
        ]
    if isinstance(demo_report.get("review_queue"), list):
        return [
            dict(item)
            for item in demo_report["review_queue"]
            if isinstance(item, Mapping)
        ]
    return []


def _build_llm_quality(
    llm_review_report: Mapping[str, Any],
    reviewed_items: Sequence[Mapping[str, Any]],
    cfg: AgentEvaluationConfig,
) -> JsonDict:
    actions: Counter[str] = Counter()
    parse_errors = 0
    high_confidence = 0
    proposal_ready = 0
    for item in reviewed_items:
        judgment = item.get("judgment")
        if isinstance(judgment, Mapping):
            action = str(judgment.get("action", "unknown"))
            actions[action] += 1
            if action == "error" or item.get("parse_error"):
                parse_errors += 1
            confidence = float(judgment.get("confidence", 0.0) or 0.0)
            if confidence >= cfg.min_confidence_for_review_ready:
                high_confidence += 1
        elif item.get("review_status"):
            actions[str(item.get("review_status"))] += 1
        if item.get("proposal_ready_for_validation") is True:
            proposal_ready += 1
    summary = llm_review_report.get("llm_review_summary")
    live_calls = 0
    cache_hits = 0
    skipped = 0
    if isinstance(summary, Mapping):
        live_calls = int(summary.get("live_openrouter_calls", 0) or 0)
        cache_hits = int(summary.get("cache_hits", 0) or 0)
        skipped = int(summary.get("skipped_due_to_budget", 0) or 0)
    return {
        "actions": dict(sorted(actions.items())),
        "items_reviewed": len(reviewed_items),
        "high_confidence_items": high_confidence,
        "parse_errors": parse_errors,
        "proposal_ready_for_validation": proposal_ready,
        "live_openrouter_calls": live_calls,
        "cache_hits": cache_hits,
        "skipped_due_to_budget": skipped,
        "needs_evidence_rate": _safe_ratio(
            actions.get("needs_evidence", 0), len(reviewed_items)
        ),
        "proposal_ready_rate": _safe_ratio(proposal_ready, len(reviewed_items)),
    }


def _build_evidence_quality(
    demo_report: Mapping[str, Any],
    llm_review_report: Mapping[str, Any],
    reviewed_items: Sequence[Mapping[str, Any]],
) -> JsonDict:
    candidate_summary = _merge_candidate_summary(demo_report, llm_review_report)
    items_with_evidence = int(candidate_summary.get("candidates_with_evidence", 0))
    review_queue = int(candidate_summary.get("candidates_in_review_queue", 0))
    if review_queue <= 0 and reviewed_items:
        review_queue = len(reviewed_items)
        items_with_evidence = sum(
            1
            for item in reviewed_items
            if int(item.get("evidence_windows_found", 0) or 0) > 0
        )
    return {
        "candidates_with_evidence": items_with_evidence,
        "candidates_in_review_queue": review_queue,
        "evidence_coverage": _safe_ratio(items_with_evidence, review_queue),
        "total_evidence_windows": candidate_summary.get("total_evidence_windows", 0),
    }


def _build_proposal_quality(
    llm_review_report: Mapping[str, Any],
    reviewed_items: Sequence[Mapping[str, Any]],
    outcome_records: Sequence[Mapping[str, Any]],
) -> JsonDict:
    prepared = sum(
        1 for item in reviewed_items if item.get("proposal_payload") is not None
    )
    ready = sum(
        1
        for item in reviewed_items
        if item.get("proposal_ready_for_validation") is True
    )
    summary = llm_review_report.get("llm_review_summary")
    if isinstance(summary, Mapping):
        prepared = int(summary.get("proposals_prepared", prepared) or 0)
    accepted = sum(1 for row in outcome_records if row.get("outcome") == "accepted")
    rejected = sum(1 for row in outcome_records if row.get("outcome") == "rejected")
    decided = accepted + rejected
    return {
        "proposals_prepared": prepared,
        "proposal_payloads_ready_for_validation": ready,
        "proposals_submitted": int(
            llm_review_report.get("proposals_submitted", 0) or 0
        ),
        "accepted_outcomes": accepted,
        "rejected_outcomes": rejected,
        "acceptance_rate": _safe_ratio(accepted, decided),
        "precision_proxy": _safe_ratio(accepted, decided),
        "note": (
            "Precision proxy uses optional human/policy outcomes. Retrieval metrics "
            "require qrels and snapshot before/after evaluation."
        ),
    }


def _build_outcome_summary(
    outcome_records: Sequence[Mapping[str, Any]],
    reviewed_items: Sequence[Mapping[str, Any]],
) -> JsonDict:
    counts: Counter[str] = Counter(
        str(row.get("outcome", "unknown")) for row in outcome_records
    )
    for name in sorted(_VALID_OUTCOMES):
        counts.setdefault(name, 0)
    reviewed_by_alias = {
        str(item.get("candidate_alias")): item for item in reviewed_items
    }
    unmatched = [
        str(row.get("candidate_alias", ""))
        for row in outcome_records
        if row.get("candidate_alias")
        and str(row.get("candidate_alias")) not in reviewed_by_alias
    ]
    return {
        "outcomes_loaded": len(outcome_records),
        "counts": dict(sorted(counts.items())),
        "unmatched_outcome_aliases": sorted(unmatched),
    }


def _build_cost_summary(llm_review_report: Mapping[str, Any]) -> JsonDict:
    budget_summary = llm_review_report.get("budget_cache_summary")
    if isinstance(budget_summary, Mapping):
        usage = budget_summary.get("usage")
        if isinstance(usage, Mapping):
            return {
                "prompt_tokens": int(usage.get("prompt_tokens", 0) or 0),
                "completion_tokens": int(usage.get("completion_tokens", 0) or 0),
                "total_tokens": int(usage.get("total_tokens", 0) or 0),
                "estimated_cost_usd": float(
                    usage.get("estimated_cost_usd", 0.0) or 0.0
                ),
                "cache_hits": int(budget_summary.get("cache_hits", 0) or 0),
                "cache_misses": int(budget_summary.get("cache_misses", 0) or 0),
            }
    totals = Counter()
    raw_items = llm_review_report.get("reviewed_items", [])
    if not isinstance(raw_items, list):
        raw_items = []
    for item in raw_items:
        if not isinstance(item, Mapping):
            continue
        usage = item.get("openrouter_usage")
        if not isinstance(usage, Mapping):
            continue
        totals["prompt_tokens"] += int(usage.get("prompt_tokens", 0) or 0)
        totals["completion_tokens"] += int(usage.get("completion_tokens", 0) or 0)
        totals["total_tokens"] += int(usage.get("total_tokens", 0) or 0)
        totals["estimated_cost_usd"] += float(usage.get("cost", 0.0) or 0.0)
    return {
        "prompt_tokens": int(totals["prompt_tokens"]),
        "completion_tokens": int(totals["completion_tokens"]),
        "total_tokens": int(totals["total_tokens"]),
        "estimated_cost_usd": round(float(totals["estimated_cost_usd"]), 8),
        "cache_hits": 0,
        "cache_misses": 0,
    }


def _build_quality_gate(
    llm_quality: Mapping[str, Any],
    proposal_quality: Mapping[str, Any],
    outcome_summary: Mapping[str, Any],
) -> JsonDict:
    parse_errors = int(llm_quality.get("parse_errors", 0) or 0)
    raw_counts = outcome_summary.get("counts")
    blocked = (
        int(raw_counts.get("blocked", 0)) if isinstance(raw_counts, Mapping) else 0
    )
    ready = int(proposal_quality.get("proposal_payloads_ready_for_validation", 0) or 0)
    status = "needs_review"
    reasons: list[str] = []
    if parse_errors:
        status = "blocked"
        reasons.append("model_parse_errors_present")
    if blocked:
        status = "blocked"
        reasons.append("blocked_outcomes_present")
    if ready and status != "blocked":
        status = "ready_for_validation"
        reasons.append("proposal_payloads_ready_for_validation")
    if not reasons:
        reasons.append("no_high_confidence_proposals_ready")
    return {"status": status, "reasons": reasons}


def _compact_reviewed_items(
    reviewed_items: Sequence[Mapping[str, Any]], cfg: AgentEvaluationConfig
) -> list[JsonDict]:
    if not cfg.include_reviewed_items:
        return []
    compact: list[JsonDict] = []
    for item in reviewed_items[: cfg.max_items]:
        judgment = (
            item.get("judgment") if isinstance(item.get("judgment"), Mapping) else {}
        )
        candidate_pack = (
            item.get("candidate_pack") if cfg.include_candidate_packs else None
        )
        row: JsonDict = {
            "candidate_alias": item.get("candidate_alias"),
            "review_status": item.get("review_status"),
            "judgment_action": (
                judgment.get("action") if isinstance(judgment, Mapping) else None
            ),
            "judgment_confidence": (
                judgment.get("confidence") if isinstance(judgment, Mapping) else None
            ),
            "proposal_ready_for_validation": item.get(
                "proposal_ready_for_validation", False
            ),
            "evidence_windows_found": item.get("evidence_windows_found"),
            "cache_hit": (
                item.get("cache", {}).get("hit")
                if isinstance(item.get("cache"), Mapping)
                else None
            ),
        }
        if candidate_pack is not None:
            row["candidate_pack"] = candidate_pack
        compact.append(row)
    return compact


def _safe_ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)
