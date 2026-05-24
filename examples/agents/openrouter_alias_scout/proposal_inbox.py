"""Offline proposal inbox and review workflow for the OpenRouter alias scout.

Patch 41G intentionally keeps review workflow agent-side and offline. It turns
LLM review + validation/submission reports into a human-readable inbox with
review decisions that can be stored as JSONL. No backend routes, database
migrations, snapshots, or runtime mutation are introduced here.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

JsonDict = dict[str, Any]
ALLOWED_REVIEW_ACTIONS = {"approve", "reject", "edit", "defer"}


@dataclass(frozen=True)
class ProposalInboxConfig:
    """Controls local proposal inbox rendering and review decision loading."""

    max_items: int = 50
    evidence_preview_chars: int = 240
    include_source_payload: bool = False
    include_validation_response: bool = False
    review_decisions_path: Path | None = None

    @classmethod
    def from_mapping(
        cls, raw: Mapping[str, Any] | None, *, base_dir: Path | None = None
    ) -> "ProposalInboxConfig":
        """Create config from optional JSON config values."""

        if not raw:
            return cls()
        decisions_path: Path | None = None
        raw_path = raw.get("review_decisions_path")
        if raw_path:
            decisions_path = Path(str(raw_path))
            if base_dir is not None and not decisions_path.is_absolute():
                decisions_path = base_dir / decisions_path
        return cls(
            max_items=int(raw.get("max_items", cls.max_items)),
            evidence_preview_chars=int(
                raw.get("evidence_preview_chars", cls.evidence_preview_chars)
            ),
            include_source_payload=bool(
                raw.get("include_source_payload", cls.include_source_payload)
            ),
            include_validation_response=bool(
                raw.get("include_validation_response", cls.include_validation_response)
            ),
            review_decisions_path=decisions_path,
        )

    def with_overrides(
        self,
        *,
        review_decisions_path: Path | None = None,
        max_items: int | None = None,
    ) -> "ProposalInboxConfig":
        """Return config with CLI overrides applied."""

        return ProposalInboxConfig(
            max_items=self.max_items if max_items is None else max_items,
            evidence_preview_chars=self.evidence_preview_chars,
            include_source_payload=self.include_source_payload,
            include_validation_response=self.include_validation_response,
            review_decisions_path=(
                self.review_decisions_path
                if review_decisions_path is None
                else review_decisions_path
            ),
        )

    def to_plan(self) -> JsonDict:
        """Return a network-free inbox plan."""

        return {
            "schema_version": "skeinrank.agent_proposal_inbox_plan.v1",
            "runner": "openrouter_alias_scout",
            "openrouter_calls": False,
            "skeinrank_api_calls": False,
            "runtime_mutation_enabled": False,
            "snapshot_publish_enabled": False,
            "max_items": self.max_items,
            "evidence_preview_chars": self.evidence_preview_chars,
            "include_source_payload": self.include_source_payload,
            "include_validation_response": self.include_validation_response,
            "review_decisions_path": (
                str(self.review_decisions_path) if self.review_decisions_path else None
            ),
            "supported_review_actions": sorted(ALLOWED_REVIEW_ACTIONS),
            "safety": {
                "review_is_offline": True,
                "direct_dictionary_write_enabled": False,
                "snapshot_publish_enabled": False,
                "runtime_mutation_enabled": False,
            },
        }


def load_review_decisions(path: Path | None) -> list[JsonDict]:
    """Load optional local human/policy review decisions from JSONL."""

    if path is None or not path.exists():
        return []
    decisions: list[JsonDict] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), 1
    ):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, Mapping):
            raise ValueError(f"Invalid review decision at {path}:{line_number}")
        action = str(value.get("action", "")).strip().lower()
        if action not in ALLOWED_REVIEW_ACTIONS:
            raise ValueError(
                f"Invalid review action {action!r} at {path}:{line_number}. "
                f"Expected one of {sorted(ALLOWED_REVIEW_ACTIONS)}."
            )
        if not value.get("candidate_alias") and not value.get("idempotency_key"):
            raise ValueError(
                f"Review decision at {path}:{line_number} needs candidate_alias or "
                "idempotency_key."
            )
        decision = dict(value)
        decision["action"] = action
        decisions.append(decision)
    return decisions


def build_proposal_inbox_report(
    *,
    llm_review_report: Mapping[str, Any] | None = None,
    proposal_submission_report: Mapping[str, Any] | None = None,
    review_decisions: Sequence[Mapping[str, Any]] | None = None,
    config: ProposalInboxConfig | None = None,
) -> JsonDict:
    """Build a local review inbox from LLM and validation/submission reports."""

    cfg = config or ProposalInboxConfig()
    llm_items = _index_llm_items(llm_review_report or {})
    submission_results = _submission_results(proposal_submission_report or {})
    if not submission_results:
        submission_results = _submission_results_from_llm(llm_review_report or {})
    decisions = _index_review_decisions(review_decisions or [])

    inbox_items: list[JsonDict] = []
    for result in submission_results[: cfg.max_items]:
        key = _item_key(result)
        llm_item = (
            llm_items.get(key) or llm_items.get(str(result.get("alias_value"))) or {}
        )
        decision = _find_decision(result, decisions)
        inbox_items.append(_build_inbox_item(result, llm_item, decision, cfg))

    summary = _summarize_inbox(inbox_items, len(review_decisions or []))
    return {
        "schema_version": "skeinrank.agent_proposal_inbox.v1",
        "runner": "openrouter_alias_scout",
        "openrouter_calls": False,
        "skeinrank_api_calls": False,
        "runtime_mutation_enabled": False,
        "snapshot_publish_enabled": False,
        "summary": summary,
        "items": inbox_items,
        "next_steps": [
            "Review pending cards and write decisions to review_decisions.example.jsonl.",
            "Use approved decisions to drive a later governed apply/snapshot workflow.",
            "Keep direct dictionary writes and snapshot publishing outside the agent runner.",
        ],
        "safety": {
            "review_is_offline": True,
            "agent_may_mutate_runtime": False,
            "blocked_actions": [
                "direct_dictionary_write",
                "snapshot_publish",
                "direct_git_push",
                "runtime_mutation",
            ],
        },
    }


def _index_llm_items(report: Mapping[str, Any]) -> dict[str, JsonDict]:
    indexed: dict[str, JsonDict] = {}
    for raw in report.get("reviewed_items") or []:
        if not isinstance(raw, Mapping):
            continue
        item = dict(raw)
        key = str(item.get("idempotency_key") or item.get("candidate_alias") or "")
        if key:
            indexed[key] = item
        alias = str(item.get("candidate_alias") or "")
        if alias:
            indexed[alias] = item
    return indexed


def _submission_results(report: Mapping[str, Any]) -> list[JsonDict]:
    values = report.get("results")
    if not isinstance(values, list):
        return []
    return [dict(item) for item in values if isinstance(item, Mapping)]


def _submission_results_from_llm(report: Mapping[str, Any]) -> list[JsonDict]:
    results: list[JsonDict] = []
    for item in report.get("reviewed_items") or []:
        if not isinstance(item, Mapping):
            continue
        payload = item.get("proposal_payload")
        if not isinstance(payload, Mapping):
            continue
        results.append(
            {
                "alias_value": payload.get("alias_value")
                or item.get("candidate_alias"),
                "canonical_value": payload.get("canonical_value"),
                "slot": payload.get("slot"),
                "confidence": payload.get("confidence"),
                "idempotency_key": payload.get("idempotency_key"),
                "status": "ready_for_validation",
                "submitted": False,
                "proposal_payload": dict(payload),
            }
        )
    return results


def _index_review_decisions(
    decisions: Sequence[Mapping[str, Any]],
) -> dict[str, JsonDict]:
    indexed: dict[str, JsonDict] = {}
    for raw in decisions:
        decision = dict(raw)
        for key_name in ("idempotency_key", "candidate_alias"):
            value = decision.get(key_name)
            if value:
                indexed[str(value)] = decision
    return indexed


def _find_decision(
    item: Mapping[str, Any], decisions: Mapping[str, Mapping[str, Any]]
) -> JsonDict | None:
    for value in (item.get("idempotency_key"), item.get("alias_value")):
        if value and str(value) in decisions:
            return dict(decisions[str(value)])
    return None


def _build_inbox_item(
    result: Mapping[str, Any],
    llm_item: Mapping[str, Any],
    decision: Mapping[str, Any] | None,
    cfg: ProposalInboxConfig,
) -> JsonDict:
    payload = _extract_payload(result, llm_item)
    validation_decision = result.get("validation_decision")
    if not isinstance(validation_decision, Mapping):
        validation_decision = {}
    review_status = _review_status_for(result, validation_decision, decision)
    item: JsonDict = {
        "candidate_alias": result.get("alias_value") or result.get("candidate_alias"),
        "canonical_value": result.get("canonical_value")
        or payload.get("canonical_value"),
        "slot": result.get("slot") or payload.get("slot"),
        "confidence": result.get("confidence") or payload.get("confidence"),
        "idempotency_key": result.get("idempotency_key")
        or payload.get("idempotency_key"),
        "submission_status": result.get("status", "unknown"),
        "validation_status": result.get("validation_status"),
        "validation_category": validation_decision.get("category"),
        "validation_reason": validation_decision.get("reason"),
        "review_status": review_status,
        "submitted": bool(result.get("submitted")),
        "evidence_preview": _evidence_preview(payload, cfg.evidence_preview_chars),
        "known_conflicts": _known_conflicts(payload),
        "llm_judgment": _llm_judgment_summary(llm_item),
        "recommended_action": _recommended_action(review_status),
    }
    if decision is not None:
        item["review_decision"] = _clean_decision(decision)
    if cfg.include_source_payload and payload:
        item["source_payload"] = payload
    if cfg.include_validation_response and isinstance(
        result.get("validation_response"), Mapping
    ):
        item["validation_response"] = result["validation_response"]
    return item


def _extract_payload(
    result: Mapping[str, Any], llm_item: Mapping[str, Any]
) -> JsonDict:
    for source in (result.get("proposal_payload"), llm_item.get("proposal_payload")):
        if isinstance(source, Mapping):
            payload = dict(source)
            source_payload = payload.get("source_payload")
            if isinstance(source_payload, Mapping):
                payload.update({"source_payload": dict(source_payload)})
            return payload
    return {}


def _review_status_for(
    result: Mapping[str, Any],
    validation_decision: Mapping[str, Any],
    decision: Mapping[str, Any] | None,
) -> str:
    if decision is not None:
        action = str(decision.get("action", "")).lower()
        return {
            "approve": "approved",
            "reject": "rejected",
            "edit": "edited",
            "defer": "deferred",
        }.get(action, "decision_recorded")
    status = str(result.get("status") or "")
    category = str(validation_decision.get("category") or "")
    if status == "idempotent_existing_alias" or category == "idempotent_existing_alias":
        return "idempotent_noop"
    if status == "manual_review_required" or category == "manual_review_required":
        return "pending_review"
    if status == "blocked" or category == "blocked":
        return "blocked"
    if status == "submitted":
        return "submitted_pending_review"
    if status in {"validated", "validation_passed", "ready_for_validation"}:
        return "ready_for_submission"
    return "pending_review"


def _evidence_preview(payload: Mapping[str, Any], limit: int) -> list[JsonDict]:
    source_payload = payload.get("source_payload")
    if not isinstance(source_payload, Mapping):
        source_payload = payload
    windows = source_payload.get("evidence_windows")
    preview: list[JsonDict] = []
    if isinstance(windows, list):
        for window in windows[:3]:
            if not isinstance(window, Mapping):
                continue
            text = str(window.get("text") or "")
            preview.append(
                {
                    "source_id": window.get("source_id"),
                    "source_type": window.get("source_type"),
                    "field": window.get("field"),
                    "text": _truncate(text, limit),
                }
            )
    if preview:
        return preview
    evidence = source_payload.get("evidence")
    if isinstance(evidence, list):
        for text in evidence[:3]:
            preview.append({"text": _truncate(str(text), limit)})
    return preview


def _known_conflicts(payload: Mapping[str, Any]) -> list[str]:
    source_payload = payload.get("source_payload")
    if not isinstance(source_payload, Mapping):
        source_payload = payload
    conflicts = source_payload.get("known_conflicts")
    if isinstance(conflicts, list):
        return [str(item) for item in conflicts]
    return []


def _llm_judgment_summary(llm_item: Mapping[str, Any]) -> JsonDict | None:
    judgment = llm_item.get("judgment")
    if not isinstance(judgment, Mapping):
        return None
    return {
        "action": judgment.get("action"),
        "confidence": judgment.get("confidence"),
        "reason": judgment.get("reason"),
        "risk_flags": judgment.get("risk_flags") or [],
    }


def _recommended_action(review_status: str) -> str:
    return {
        "pending_review": "human_review",
        "ready_for_submission": "validate_then_submit_with_policy",
        "idempotent_noop": "no_action_needed",
        "blocked": "do_not_submit",
        "submitted_pending_review": "review_pending_proposal",
        "approved": "ready_for_governed_apply",
        "rejected": "do_not_apply",
        "edited": "revalidate_edited_payload",
        "deferred": "collect_more_evidence",
    }.get(review_status, "human_review")


def _clean_decision(decision: Mapping[str, Any]) -> JsonDict:
    cleaned = dict(decision)
    if "source_payload" in cleaned:
        cleaned.pop("source_payload")
    return cleaned


def _summarize_inbox(
    items: Sequence[Mapping[str, Any]], decisions_loaded: int
) -> JsonDict:
    review_statuses = Counter(
        str(item.get("review_status", "unknown")) for item in items
    )
    validation_categories = Counter(
        str(item.get("validation_category") or "unknown") for item in items
    )
    return {
        "items_total": len(items),
        "review_statuses": dict(sorted(review_statuses.items())),
        "validation_categories": dict(sorted(validation_categories.items())),
        "decisions_loaded": decisions_loaded,
        "pending_review": review_statuses.get("pending_review", 0),
        "approved": review_statuses.get("approved", 0),
        "rejected": review_statuses.get("rejected", 0),
        "edited": review_statuses.get("edited", 0),
        "idempotent_noop": review_statuses.get("idempotent_noop", 0),
        "blocked": review_statuses.get("blocked", 0),
    }


def _item_key(item: Mapping[str, Any]) -> str:
    return str(item.get("idempotency_key") or item.get("alias_value") or "")


def _truncate(text: str, limit: int) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: max(0, limit - 1)].rstrip() + "…"
