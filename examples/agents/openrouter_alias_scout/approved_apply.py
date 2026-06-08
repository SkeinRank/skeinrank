"""Offline approved-proposal apply planning and snapshot evaluation.

The agent runner stays out of production mutation. It consumes the proposal inbox
and local review decisions, builds a governed apply plan for approved items, and
optionally compares before/after snapshot artifacts. Backend apply endpoints,
direct dictionary writes, and snapshot publishing are not called from this
module.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

JsonDict = dict[str, Any]


@dataclass(frozen=True)
class ApprovedApplyConfig:
    """Controls offline approved proposal apply planning."""

    max_items: int = 50
    approved_statuses: tuple[str, ...] = ("approved",)
    include_item_details: bool = True
    before_snapshot_path: Path | None = None
    after_snapshot_path: Path | None = None

    @classmethod
    def from_mapping(
        cls, raw: Mapping[str, Any] | None, *, base_dir: Path | None = None
    ) -> "ApprovedApplyConfig":
        """Create config from optional JSON config values."""

        if not raw:
            return cls()
        before_path = _optional_path(raw.get("before_snapshot_path"), base_dir)
        after_path = _optional_path(raw.get("after_snapshot_path"), base_dir)
        statuses = raw.get("approved_statuses", cls.approved_statuses)
        if isinstance(statuses, str):
            statuses = [statuses]
        return cls(
            max_items=int(raw.get("max_items", cls.max_items)),
            approved_statuses=tuple(str(item) for item in statuses),
            include_item_details=bool(
                raw.get("include_item_details", cls.include_item_details)
            ),
            before_snapshot_path=before_path,
            after_snapshot_path=after_path,
        )

    def with_overrides(
        self,
        *,
        before_snapshot_path: Path | None = None,
        after_snapshot_path: Path | None = None,
        max_items: int | None = None,
    ) -> "ApprovedApplyConfig":
        """Return config with CLI overrides applied."""

        return ApprovedApplyConfig(
            max_items=self.max_items if max_items is None else max_items,
            approved_statuses=self.approved_statuses,
            include_item_details=self.include_item_details,
            before_snapshot_path=(
                self.before_snapshot_path
                if before_snapshot_path is None
                else before_snapshot_path
            ),
            after_snapshot_path=(
                self.after_snapshot_path
                if after_snapshot_path is None
                else after_snapshot_path
            ),
        )

    def to_plan(self) -> JsonDict:
        """Return a network-free apply/snapshot plan."""

        return {
            "schema_version": "skeinrank.agent_approved_apply_plan.v1",
            "runner": "openrouter_alias_scout",
            "openrouter_calls": False,
            "skeinrank_api_calls": False,
            "runtime_mutation_enabled": False,
            "snapshot_publish_enabled": False,
            "max_items": self.max_items,
            "approved_statuses": list(self.approved_statuses),
            "include_item_details": self.include_item_details,
            "before_snapshot_path": (
                str(self.before_snapshot_path) if self.before_snapshot_path else None
            ),
            "after_snapshot_path": (
                str(self.after_snapshot_path) if self.after_snapshot_path else None
            ),
            "safety": {
                "apply_is_offline": True,
                "direct_dictionary_write_enabled": False,
                "snapshot_publish_enabled": False,
                "runtime_mutation_enabled": False,
                "requires_governed_backend_apply": True,
            },
        }


def build_approved_proposals_apply_plan(
    proposal_inbox_report: Mapping[str, Any],
    *,
    config: ApprovedApplyConfig | None = None,
) -> JsonDict:
    """Build an offline apply plan from a proposal inbox report."""

    cfg = config or ApprovedApplyConfig()
    approved_statuses = {status.lower() for status in cfg.approved_statuses}
    items = _inbox_items(proposal_inbox_report)[: cfg.max_items]

    operations: list[JsonDict] = []
    skipped: list[JsonDict] = []
    for item in items:
        review_status = str(item.get("review_status") or "").lower()
        if review_status in approved_statuses:
            operations.append(
                _build_apply_operation(item, include_details=cfg.include_item_details)
            )
        else:
            skipped.append(_build_skip_record(item, review_status))

    summary = {
        "inbox_items_seen": len(items),
        "approved_operations": len(operations),
        "skipped_items": len(skipped),
        "idempotent_noops": sum(
            1 for item in items if item.get("review_status") == "idempotent_noop"
        ),
        "manual_review_items": sum(
            1 for item in items if item.get("review_status") == "pending_review"
        ),
        "rejected_items": sum(
            1 for item in items if item.get("review_status") == "rejected"
        ),
    }
    return {
        "schema_version": "skeinrank.agent_approved_apply_plan.v1",
        "runner": "openrouter_alias_scout",
        "openrouter_calls": False,
        "skeinrank_api_calls": False,
        "runtime_mutation_enabled": False,
        "snapshot_publish_enabled": False,
        "summary": summary,
        "operations": operations,
        "skipped": skipped,
        "next_steps": [
            (
                "Apply approved operations through the governed backend workflow, "
                "not directly from the agent runner."
            ),
            "Create a new snapshot only after approved proposals are applied by policy.",
            "Run before/after snapshot evaluation before publishing runtime artifacts.",
        ],
        "safety": {
            "apply_is_offline": True,
            "agent_may_mutate_runtime": False,
            "blocked_actions": [
                "direct_dictionary_write",
                "snapshot_publish",
                "direct_git_push",
                "runtime_mutation",
            ],
        },
    }


def build_snapshot_evaluation_report(
    *,
    apply_plan: Mapping[str, Any] | None = None,
    before_snapshot: Mapping[str, Any] | None = None,
    after_snapshot: Mapping[str, Any] | None = None,
) -> JsonDict:
    """Build an offline before/after snapshot evaluation report."""

    operations = _apply_operations(apply_plan or {})
    if before_snapshot is None or after_snapshot is None:
        return {
            "schema_version": "skeinrank.agent_snapshot_evaluation_report.v1",
            "runner": "openrouter_alias_scout",
            "openrouter_calls": False,
            "skeinrank_api_calls": False,
            "runtime_mutation_enabled": False,
            "snapshot_publish_enabled": False,
            "snapshot_eval_enabled": False,
            "reason": "before and after snapshot artifacts are required for concrete diff metrics.",
            "apply_plan_summary": dict((apply_plan or {}).get("summary") or {}),
            "approved_operations": len(operations),
            "requires": [
                "approved apply plan",
                "before snapshot artifact",
                "after snapshot artifact",
                "optional qrels or sample-query set for retrieval metrics",
            ],
            "safety": _offline_snapshot_safety(),
        }

    before_aliases = _snapshot_alias_map(before_snapshot)
    after_aliases = _snapshot_alias_map(after_snapshot)
    diff = _diff_alias_maps(before_aliases, after_aliases)
    coverage = _approved_operation_coverage(operations, after_aliases)
    return {
        "schema_version": "skeinrank.agent_snapshot_evaluation_report.v1",
        "runner": "openrouter_alias_scout",
        "openrouter_calls": False,
        "skeinrank_api_calls": False,
        "runtime_mutation_enabled": False,
        "snapshot_publish_enabled": False,
        "snapshot_eval_enabled": True,
        "apply_plan_summary": dict((apply_plan or {}).get("summary") or {}),
        "alias_diff": diff,
        "approved_operation_coverage": coverage,
        "quality_gate": _snapshot_quality_gate(diff, coverage),
        "retrieval_metrics": {
            "enabled": False,
            "reason": "qrels/sample-query evaluation is outside this apply plan.",
        },
        "safety": _offline_snapshot_safety(),
    }


def load_json_report(path: Path | None) -> JsonDict | None:
    """Load a JSON report if a path is provided."""

    if path is None:
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise ValueError(f"Expected JSON object report at {path}")
    return dict(value)


def _optional_path(value: Any, base_dir: Path | None) -> Path | None:
    if not value:
        return None
    path = Path(str(value))
    if base_dir is not None and not path.is_absolute():
        return base_dir / path
    return path


def _inbox_items(report: Mapping[str, Any]) -> list[JsonDict]:
    items = report.get("items")
    if not isinstance(items, list):
        return []
    return [dict(item) for item in items if isinstance(item, Mapping)]


def _build_apply_operation(
    item: Mapping[str, Any], *, include_details: bool
) -> JsonDict:
    operation: JsonDict = {
        "operation": "apply_alias_proposal",
        "candidate_alias": item.get("candidate_alias"),
        "canonical_value": item.get("canonical_value"),
        "slot": item.get("slot"),
        "confidence": item.get("confidence"),
        "idempotency_key": item.get("idempotency_key"),
        "review_status": item.get("review_status"),
        "recommended_backend_flow": [
            "load approved proposal",
            "apply to profile through governed backend service",
            "create new snapshot",
            "run snapshot before/after evaluation",
        ],
        "status": "ready_for_governed_apply",
    }
    decision = item.get("review_decision")
    if isinstance(decision, Mapping):
        operation["review_decision"] = dict(decision)
    if include_details:
        for key in (
            "evidence_preview",
            "llm_judgment",
            "validation_category",
            "validation_reason",
        ):
            if key in item:
                operation[key] = item[key]
    return operation


def _build_skip_record(item: Mapping[str, Any], review_status: str) -> JsonDict:
    return {
        "candidate_alias": item.get("candidate_alias"),
        "canonical_value": item.get("canonical_value"),
        "idempotency_key": item.get("idempotency_key"),
        "review_status": review_status or "unknown",
        "reason": _skip_reason(review_status),
    }


def _skip_reason(review_status: str) -> str:
    return {
        "idempotent_noop": "alias already exists or no apply operation is needed",
        "pending_review": "human or policy review has not approved this proposal yet",
        "rejected": "review decision rejected this proposal",
        "edited": "edited proposals must be revalidated before governed apply",
        "deferred": "more evidence is required before apply",
        "blocked": "validator or policy blocked this proposal",
    }.get(review_status, "not_approved_for_apply")


def _apply_operations(plan: Mapping[str, Any]) -> list[JsonDict]:
    operations = plan.get("operations")
    if not isinstance(operations, list):
        return []
    return [dict(item) for item in operations if isinstance(item, Mapping)]


def _snapshot_alias_map(snapshot: Mapping[str, Any]) -> dict[str, JsonDict]:
    aliases: dict[str, JsonDict] = {}
    raw_aliases = snapshot.get("aliases")
    if isinstance(raw_aliases, Mapping):
        for alias, value in raw_aliases.items():
            if isinstance(value, Mapping):
                canonical = value.get("canonical") or value.get("canonical_value")
                slot = value.get("slot")
            else:
                canonical = value
                slot = None
            aliases[_norm(alias)] = {
                "alias": str(alias),
                "canonical_value": str(canonical) if canonical is not None else None,
                "slot": str(slot) if slot is not None else None,
            }
    terms = snapshot.get("terms")
    if isinstance(terms, list):
        for term in terms:
            if not isinstance(term, Mapping):
                continue
            canonical = term.get("canonical_value") or term.get("canonical")
            slot = term.get("slot")
            for alias in term.get("aliases") or []:
                aliases[_norm(alias)] = {
                    "alias": str(alias),
                    "canonical_value": str(canonical)
                    if canonical is not None
                    else None,
                    "slot": str(slot) if slot is not None else None,
                }
    return aliases


def _diff_alias_maps(
    before: Mapping[str, JsonDict], after: Mapping[str, JsonDict]
) -> JsonDict:
    before_keys = set(before)
    after_keys = set(after)
    added = sorted(after_keys - before_keys)
    removed = sorted(before_keys - after_keys)
    changed = sorted(
        key
        for key in before_keys & after_keys
        if _alias_signature(before[key]) != _alias_signature(after[key])
    )
    unchanged = sorted((before_keys & after_keys) - set(changed))
    return {
        "added_aliases": [_public_alias(after[key]) for key in added],
        "removed_aliases": [_public_alias(before[key]) for key in removed],
        "changed_aliases": [
            {"before": _public_alias(before[key]), "after": _public_alias(after[key])}
            for key in changed
        ],
        "counts": {
            "before_aliases": len(before),
            "after_aliases": len(after),
            "added": len(added),
            "removed": len(removed),
            "changed": len(changed),
            "unchanged": len(unchanged),
        },
    }


def _approved_operation_coverage(
    operations: Sequence[Mapping[str, Any]], after_aliases: Mapping[str, JsonDict]
) -> JsonDict:
    covered: list[JsonDict] = []
    missing: list[JsonDict] = []
    changed_target: list[JsonDict] = []
    for operation in operations:
        alias = str(operation.get("candidate_alias") or "")
        canonical = str(operation.get("canonical_value") or "")
        after = after_aliases.get(_norm(alias))
        if after is None:
            missing.append({"alias": alias, "expected_canonical": canonical})
            continue
        if _norm(after.get("canonical_value")) != _norm(canonical):
            changed_target.append(
                {
                    "alias": alias,
                    "expected_canonical": canonical,
                    "actual_canonical": after.get("canonical_value"),
                }
            )
            continue
        covered.append({"alias": alias, "canonical_value": canonical})
    total = len(operations)
    return {
        "approved_operations": total,
        "covered": covered,
        "missing": missing,
        "changed_target": changed_target,
        "coverage_rate": (len(covered) / total) if total else None,
    }


def _snapshot_quality_gate(
    diff: Mapping[str, Any], coverage: Mapping[str, Any]
) -> JsonDict:
    reasons: list[str] = []
    status = "ready_for_publish_review"
    if coverage.get("missing"):
        status = "needs_review"
        reasons.append("approved_aliases_missing_from_after_snapshot")
    if coverage.get("changed_target"):
        status = "needs_review"
        reasons.append("approved_aliases_map_to_unexpected_canonical")
    counts = diff.get("counts") if isinstance(diff.get("counts"), Mapping) else {}
    if counts.get("removed", 0):
        status = "needs_review"
        reasons.append("snapshot_removed_aliases")
    if not reasons:
        reasons.append("approved_aliases_covered")
    return {"status": status, "reasons": reasons}


def _alias_signature(value: Mapping[str, Any]) -> tuple[str | None, str | None]:
    return (_norm(value.get("canonical_value")), _norm(value.get("slot")))


def _public_alias(value: Mapping[str, Any]) -> JsonDict:
    return {
        "alias": value.get("alias"),
        "canonical_value": value.get("canonical_value"),
        "slot": value.get("slot"),
    }


def _norm(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _offline_snapshot_safety() -> JsonDict:
    return {
        "evaluation_is_offline": True,
        "agent_may_mutate_runtime": False,
        "blocked_actions": [
            "direct_dictionary_write",
            "snapshot_publish",
            "direct_git_push",
            "runtime_mutation",
        ],
    }
