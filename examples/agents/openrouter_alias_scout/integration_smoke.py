"""Full offline integration smoke test for the OpenRouter alias scout.

Patch 42A turns the manually tested contour into one reproducible smoke report:

    demo report -> synthetic LLM review -> synthetic validation -> proposal inbox
    -> approved apply plan -> snapshot evaluation -> cycle-style manifest

The smoke is intentionally network-free. It does not call OpenRouter,
Elasticsearch, or the SkeinRank API, and it never mutates runtime state. Live
checks remain covered by the explicit 41B/41I commands.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:  # pragma: no cover - import style depends on execution mode.
    from .agent_evaluation import AgentEvaluationConfig, build_agent_evaluation_report
    from .approved_apply import (
        ApprovedApplyConfig,
        build_approved_proposals_apply_plan,
        build_snapshot_evaluation_report,
    )
    from .candidate_discovery import CandidateDiscoveryConfig
    from .canonical_hints import CanonicalHintsConfig
    from .demo_report import DemoReportConfig, build_alias_scout_demo_report
    from .evidence_sampler import EvidenceSamplerConfig
    from .proposal_inbox import ProposalInboxConfig, build_proposal_inbox_report
    from .proposal_submission import ProposalSubmissionConfig
    from .scheduled_runner import ScheduledRunnerConfig, build_scheduled_cycle_report
except ImportError:  # pragma: no cover
    from agent_evaluation import AgentEvaluationConfig, build_agent_evaluation_report
    from approved_apply import (
        ApprovedApplyConfig,
        build_approved_proposals_apply_plan,
        build_snapshot_evaluation_report,
    )
    from candidate_discovery import CandidateDiscoveryConfig
    from canonical_hints import CanonicalHintsConfig
    from demo_report import DemoReportConfig, build_alias_scout_demo_report
    from evidence_sampler import EvidenceSamplerConfig
    from proposal_inbox import ProposalInboxConfig, build_proposal_inbox_report
    from proposal_submission import ProposalSubmissionConfig
    from scheduled_runner import ScheduledRunnerConfig, build_scheduled_cycle_report

JsonDict = dict[str, Any]


@dataclass(frozen=True)
class FullIntegrationSmokeConfig:
    """Controls the network-free 42A end-to-end smoke test."""

    artifacts_dir: Path
    max_candidates: int = 3
    approve_ready_proposals: bool = True
    write_artifacts: bool = True
    include_snapshot_artifacts: bool = True
    confidence: float = 0.91
    run_id_prefix: str = "full-agent-smoke"

    @classmethod
    def from_mapping(
        cls, raw: Mapping[str, Any] | None, *, base_dir: Path | None = None
    ) -> "FullIntegrationSmokeConfig":
        data = dict(raw or {})
        raw_artifacts_dir = Path(str(data.get("artifacts_dir", "reports/integration")))
        if base_dir is not None and not raw_artifacts_dir.is_absolute():
            raw_artifacts_dir = base_dir / raw_artifacts_dir
        return cls(
            artifacts_dir=raw_artifacts_dir,
            max_candidates=int(data.get("max_candidates", cls.max_candidates)),
            approve_ready_proposals=bool(
                data.get("approve_ready_proposals", cls.approve_ready_proposals)
            ),
            write_artifacts=bool(data.get("write_artifacts", cls.write_artifacts)),
            include_snapshot_artifacts=bool(
                data.get("include_snapshot_artifacts", cls.include_snapshot_artifacts)
            ),
            confidence=float(data.get("confidence", cls.confidence)),
            run_id_prefix=str(data.get("run_id_prefix", cls.run_id_prefix)),
        )

    def with_overrides(
        self, *, artifacts_dir: Path | None = None, max_candidates: int | None = None
    ) -> "FullIntegrationSmokeConfig":
        return FullIntegrationSmokeConfig(
            artifacts_dir=artifacts_dir or self.artifacts_dir,
            max_candidates=self.max_candidates
            if max_candidates is None
            else max_candidates,
            approve_ready_proposals=self.approve_ready_proposals,
            write_artifacts=self.write_artifacts,
            include_snapshot_artifacts=self.include_snapshot_artifacts,
            confidence=self.confidence,
            run_id_prefix=self.run_id_prefix,
        )

    def to_plan(self) -> JsonDict:
        """Return a network-free plan for the full smoke contour."""

        return {
            "schema_version": "skeinrank.agent_full_integration_smoke_plan.v1",
            "runner": "openrouter_alias_scout",
            "artifacts_dir": str(self.artifacts_dir),
            "max_candidates": self.max_candidates,
            "approve_ready_proposals": self.approve_ready_proposals,
            "write_artifacts": self.write_artifacts,
            "include_snapshot_artifacts": self.include_snapshot_artifacts,
            "synthetic_confidence": self.confidence,
            "stages": [
                "demo_report",
                "synthetic_llm_review_report",
                "synthetic_validation_report",
                "proposal_inbox_report",
                "approved_apply_plan",
                "snapshot_evaluation_report",
                "agent_evaluation_report",
                "scheduled_cycle_summary",
            ],
            "safe_defaults": {
                "openrouter_calls": False,
                "elasticsearch_calls": False,
                "skeinrank_api_calls": False,
                "proposal_submission_enabled": False,
                "runtime_mutation_enabled": False,
                "snapshot_publish_enabled": False,
            },
        }


def build_full_integration_smoke_report(
    *,
    failed_queries: Sequence[Mapping[str, Any]],
    evidence_records: Sequence[Mapping[str, Any]],
    smoke_config: FullIntegrationSmokeConfig,
    candidate_config: CandidateDiscoveryConfig,
    evidence_config: EvidenceSamplerConfig,
    demo_config: DemoReportConfig,
    canonical_hints_config: CanonicalHintsConfig,
    proposal_submission_config: ProposalSubmissionConfig,
    proposal_inbox_config: ProposalInboxConfig,
    approved_apply_config: ApprovedApplyConfig,
    evaluation_config: AgentEvaluationConfig,
    scheduled_config: ScheduledRunnerConfig,
    binding_id: int | None,
    profile_name: str | None,
    proposal_source_name: str,
    openrouter_model: str,
) -> JsonDict:
    """Run the full network-free integration smoke and return one report."""

    run_id = _make_run_id(smoke_config.run_id_prefix)
    artifacts: list[JsonDict] = []

    demo_report = build_alias_scout_demo_report(
        list(failed_queries),
        list(evidence_records),
        candidate_config=candidate_config,
        evidence_config=evidence_config,
        demo_config=demo_config,
        canonical_hints_config=canonical_hints_config,
        binding_id=binding_id,
        profile_name=profile_name,
        proposal_source_name=proposal_source_name,
        openrouter_model=openrouter_model,
    )
    _write_artifact_if_enabled(
        smoke_config, run_id, "demo_report", demo_report, artifacts
    )

    llm_report = build_synthetic_llm_review_report(
        demo_report,
        max_candidates=smoke_config.max_candidates,
        confidence=smoke_config.confidence,
        profile_name=profile_name,
        proposal_source_name=proposal_source_name,
        openrouter_model=openrouter_model,
    )
    _write_artifact_if_enabled(
        smoke_config, run_id, "llm_review_report", llm_report, artifacts
    )

    validation_report = build_synthetic_validation_report(
        llm_report,
        submission_config=proposal_submission_config,
    )
    _write_artifact_if_enabled(
        smoke_config, run_id, "proposal_submission_report", validation_report, artifacts
    )

    decisions = (
        build_synthetic_review_decisions(llm_report)
        if smoke_config.approve_ready_proposals
        else []
    )
    inbox_report = build_proposal_inbox_report(
        llm_review_report=llm_report,
        proposal_submission_report=validation_report,
        review_decisions=decisions,
        config=proposal_inbox_config,
    )
    _write_artifact_if_enabled(
        smoke_config, run_id, "proposal_inbox_report", inbox_report, artifacts
    )

    apply_plan = build_approved_proposals_apply_plan(
        inbox_report, config=approved_apply_config
    )
    _write_artifact_if_enabled(
        smoke_config, run_id, "approved_apply_plan", apply_plan, artifacts
    )

    before_snapshot, after_snapshot = ({}, {})
    if smoke_config.include_snapshot_artifacts:
        before_snapshot, after_snapshot = build_synthetic_snapshots(apply_plan)
    snapshot_eval_report = build_snapshot_evaluation_report(
        apply_plan=apply_plan,
        before_snapshot=before_snapshot or None,
        after_snapshot=after_snapshot or None,
    )
    _write_artifact_if_enabled(
        smoke_config,
        run_id,
        "snapshot_evaluation_report",
        snapshot_eval_report,
        artifacts,
    )

    evaluation_report = build_agent_evaluation_report(
        demo_report=demo_report,
        llm_review_report=llm_report,
        outcome_records=[],
        evaluation_config=evaluation_config,
    )
    _write_artifact_if_enabled(
        smoke_config, run_id, "evaluation_report", evaluation_report, artifacts
    )

    steps = _build_steps(
        demo_report=demo_report,
        llm_report=llm_report,
        validation_report=validation_report,
        inbox_report=inbox_report,
        apply_plan=apply_plan,
        snapshot_eval_report=snapshot_eval_report,
        evaluation_report=evaluation_report,
    )
    cycle_report = build_scheduled_cycle_report(
        config=scheduled_config,
        run_id=run_id,
        artifacts=artifacts,
        steps=steps,
        reports={
            "demo_report": demo_report,
            "llm_review_report": llm_report,
            "proposal_submission_report": validation_report,
            "proposal_inbox_report": inbox_report,
            "approved_apply_plan": apply_plan,
            "snapshot_evaluation_report": snapshot_eval_report,
            "evaluation_report": evaluation_report,
        },
    )
    _write_artifact_if_enabled(
        smoke_config, run_id, "cycle_report", cycle_report, artifacts
    )

    quality_gate = _quality_gate(
        llm_report=llm_report,
        validation_report=validation_report,
        inbox_report=inbox_report,
        apply_plan=apply_plan,
        snapshot_eval_report=snapshot_eval_report,
    )
    return {
        "schema_version": "skeinrank.agent_full_integration_smoke.v1",
        "runner": "openrouter_alias_scout",
        "run_id": run_id,
        "status": quality_gate["status"],
        "quality_gate": quality_gate,
        "artifacts_dir": str(smoke_config.artifacts_dir),
        "artifacts": artifacts,
        "summary": {
            "candidates_discovered": demo_report.get("candidate_summary", {}).get(
                "candidates_discovered", 0
            ),
            "candidates_in_review_queue": demo_report.get("candidate_summary", {}).get(
                "candidates_in_review_queue", 0
            ),
            "llm_proposals_prepared": llm_report.get("llm_review_summary", {}).get(
                "proposals_prepared", 0
            ),
            "validated": validation_report.get("summary", {}).get("validated", 0),
            "inbox_items_total": inbox_report.get("summary", {}).get("items_total", 0),
            "approved_operations": apply_plan.get("summary", {}).get(
                "approved_operations", 0
            ),
            "snapshot_eval_enabled": snapshot_eval_report.get(
                "snapshot_eval_enabled", False
            ),
            "cycle_status": cycle_report.get("status"),
        },
        "stage_schemas": {
            "demo_report": demo_report.get("schema_version"),
            "llm_review_report": llm_report.get("schema_version"),
            "proposal_submission_report": validation_report.get("schema_version"),
            "proposal_inbox_report": inbox_report.get("schema_version"),
            "approved_apply_plan": apply_plan.get("schema_version"),
            "snapshot_evaluation_report": snapshot_eval_report.get("schema_version"),
            "evaluation_report": evaluation_report.get("schema_version"),
            "cycle_report": cycle_report.get("schema_version"),
        },
        "safety": {
            "openrouter_calls": False,
            "elasticsearch_calls": False,
            "skeinrank_api_calls": False,
            "proposal_submission_enabled": False,
            "runtime_mutation_enabled": False,
            "snapshot_publish_enabled": False,
        },
        "next_steps": [
            "Run the same contour with --agent-cycle-live-llm for live OpenRouter review.",
            "Run validation against a local SkeinRank API before enabling submit smoke.",
            "Use generated reports as fixtures for Docker/Elasticsearch validation scenarios.",
        ],
    }


def build_synthetic_llm_review_report(
    demo_report: Mapping[str, Any],
    *,
    max_candidates: int,
    confidence: float,
    profile_name: str | None,
    proposal_source_name: str,
    openrouter_model: str,
) -> JsonDict:
    """Create a deterministic proposal-ready LLM report from a demo report."""

    reviewed_items: list[JsonDict] = []
    for item in (demo_report.get("review_queue") or [])[:max_candidates]:
        if not isinstance(item, Mapping):
            continue
        pack = item.get("candidate_pack")
        if not isinstance(pack, Mapping):
            continue
        candidate_alias = str(
            item.get("candidate_alias") or pack.get("candidate_alias")
        )
        canonical_value = str(pack.get("possible_canonical") or "")
        if not candidate_alias or not canonical_value:
            continue
        slot = pack.get("slot")
        item_confidence = _hint_confidence(pack, default=confidence)
        idempotency_key = str(item.get("idempotency_key") or "")
        proposal_payload = {
            "profile_name": profile_name or pack.get("profile_name"),
            "binding_id": pack.get("binding_id"),
            "alias_value": candidate_alias,
            "canonical_value": canonical_value,
            "slot": slot,
            "confidence": item_confidence,
            "context": f"Synthetic 42A smoke proposal for {candidate_alias}.",
            "proposal_source_name": proposal_source_name,
            "idempotency_key": idempotency_key,
            "source_payload": dict(pack),
        }
        reviewed_items.append(
            {
                "candidate_alias": candidate_alias,
                "idempotency_key": idempotency_key,
                "judgment": {
                    "action": "propose",
                    "alias_value": candidate_alias,
                    "canonical_value": canonical_value,
                    "slot": slot,
                    "confidence": item_confidence,
                    "context": proposal_payload["context"],
                    "reason": (
                        "Synthetic smoke judgment based on canonical hints and "
                        "sample evidence."
                    ),
                    "risk_flags": [],
                },
                "openrouter_response_id": None,
                "openrouter_usage": None,
                "cache": {"enabled": False, "hit": False, "written": False},
                "proposal_payload": proposal_payload,
                "proposal_ready_for_validation": True,
            }
        )

    return {
        "schema_version": "skeinrank.agent_llm_review_report.v1",
        "runner": "openrouter_alias_scout",
        "llm_enabled": False,
        "openrouter_calls": False,
        "openrouter_model": openrouter_model,
        "proposal_submission_enabled": False,
        "proposals_submitted": 0,
        "candidate_summary": dict(demo_report.get("candidate_summary") or {}),
        "input_summary": dict(demo_report.get("input_summary") or {}),
        "llm_review_summary": {
            "actions": {"propose": len(reviewed_items)},
            "cache_hits": 0,
            "candidates_sent_to_model": len(reviewed_items),
            "live_openrouter_calls": 0,
            "min_confidence_to_prepare_proposal": 0.0,
            "proposals_prepared": len(reviewed_items),
            "skipped_due_to_budget": 0,
        },
        "reviewed_items": reviewed_items,
        "skeinrank_api_calls": False,
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
    }


def build_synthetic_validation_report(
    llm_review_report: Mapping[str, Any],
    *,
    submission_config: ProposalSubmissionConfig,
) -> JsonDict:
    """Create a deterministic passed validation report without API calls."""

    results: list[JsonDict] = []
    for item in llm_review_report.get("reviewed_items") or []:
        if not isinstance(item, Mapping):
            continue
        payload = item.get("proposal_payload")
        if not isinstance(payload, Mapping):
            continue
        confidence = float(payload.get("confidence") or 0.0)
        if confidence < submission_config.min_confidence:
            continue
        validation_summary = {
            "schema_version": "skeinrank.proposal_validation.v1",
            "status": "passed",
            "counts": {"passed": 8, "warning": 0, "blocked": 0, "skipped": 0},
            "checks": {
                "shape": {"status": "passed", "severity": "info"},
                "canonical_state": {"status": "passed", "severity": "info"},
                "alias_state": {"status": "passed", "severity": "info"},
                "confidence": {"status": "passed", "severity": "info"},
                "idempotency_key": {"status": "passed", "severity": "info"},
                "agent_payload": {"status": "passed", "severity": "info"},
                "noise": {"status": "passed", "severity": "info"},
                "stop_list": {"status": "passed", "severity": "info"},
            },
        }
        results.append(
            {
                "alias_value": payload.get("alias_value"),
                "canonical_value": payload.get("canonical_value"),
                "slot": payload.get("slot"),
                "confidence": confidence,
                "idempotency_key": payload.get("idempotency_key"),
                "validation_status": "passed",
                "validation_decision": {
                    "category": "validation_passed",
                    "status": "passed",
                    "submit_allowed": True,
                    "counts_as_validated": True,
                    "counts_as_passed": True,
                    "counts_as_idempotent": False,
                    "requires_manual_review": False,
                    "reason": "synthetic_smoke_validation_passed",
                },
                "validation_response": {
                    "profile_name": payload.get("profile_name"),
                    "binding_id": payload.get("binding_id"),
                    "alias_value": payload.get("alias_value"),
                    "canonical_value": payload.get("canonical_value"),
                    "slot": payload.get("slot"),
                    "confidence": confidence,
                    "proposal_source_name": payload.get("proposal_source_name"),
                    "idempotency_key": payload.get("idempotency_key"),
                    "validation_summary": validation_summary,
                },
                "submitted": False,
                "status": "validated",
                "submission_skipped_reason": "offline_smoke_does_not_submit",
                "proposal_payload": dict(payload),
            }
        )

    return {
        "schema_version": "skeinrank.agent_proposal_submission_report.v1",
        "runner": "openrouter_alias_scout",
        "skeinrank_api_calls": False,
        "proposal_submission_requested": False,
        "proposal_submission_enabled": False,
        "runtime_mutation_enabled": False,
        "snapshot_publish_enabled": False,
        "summary": {
            "proposal_payloads_ready_for_validation": len(results),
            "validated": len(results),
            "validation_passed": len(results),
            "validation_warnings": 0,
            "validation_blocked": 0,
            "validation_not_passing": 0,
            "submitted": 0,
            "created": 0,
            "errors": 0,
            "idempotent_existing_aliases": 0,
            "manual_review_required": 0,
            "blocked": 0,
            "idempotent_retries": 0,
        },
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


def build_synthetic_review_decisions(
    llm_review_report: Mapping[str, Any], *, reviewer: str = "smoke-test"
) -> list[JsonDict]:
    """Approve all proposal-ready payloads for an offline apply-plan smoke."""

    decisions: list[JsonDict] = []
    for item in llm_review_report.get("reviewed_items") or []:
        if not isinstance(item, Mapping):
            continue
        payload = item.get("proposal_payload")
        if not isinstance(payload, Mapping):
            continue
        decisions.append(
            {
                "candidate_alias": payload.get("alias_value"),
                "idempotency_key": payload.get("idempotency_key"),
                "action": "approve",
                "reviewer": reviewer,
                "comment": "42A offline integration smoke approval.",
            }
        )
    return decisions


def build_synthetic_snapshots(
    apply_plan: Mapping[str, Any],
) -> tuple[JsonDict, JsonDict]:
    """Build minimal before/after snapshot artifacts for approved operations."""

    before_terms: dict[tuple[str, str | None], set[str]] = {}
    after_terms: dict[tuple[str, str | None], set[str]] = {}
    for operation in apply_plan.get("operations") or []:
        if not isinstance(operation, Mapping):
            continue
        canonical = str(operation.get("canonical_value") or "")
        alias = str(
            operation.get("candidate_alias") or operation.get("alias_value") or ""
        )
        slot = operation.get("slot")
        if not canonical or not alias:
            continue
        key = (canonical, str(slot) if slot else None)
        before_terms.setdefault(key, set())
        after_terms.setdefault(key, set()).add(alias)

    return _terms_snapshot(before_terms), _terms_snapshot(after_terms)


def _terms_snapshot(values: Mapping[tuple[str, str | None], set[str]]) -> JsonDict:
    terms = []
    for (canonical, slot), aliases in sorted(values.items()):
        terms.append(
            {
                "canonical_value": canonical,
                "slot": slot,
                "aliases": sorted(aliases),
            }
        )
    return {"terms": terms}


def _build_steps(
    *,
    demo_report: Mapping[str, Any],
    llm_report: Mapping[str, Any],
    validation_report: Mapping[str, Any],
    inbox_report: Mapping[str, Any],
    apply_plan: Mapping[str, Any],
    snapshot_eval_report: Mapping[str, Any],
    evaluation_report: Mapping[str, Any],
) -> list[JsonDict]:
    return [
        {
            "name": "demo_report",
            "status": "completed",
            "network_calls": False,
            "summary": demo_report.get("candidate_summary"),
        },
        {
            "name": "synthetic_llm_review",
            "status": "completed",
            "network_calls": False,
            "summary": llm_report.get("llm_review_summary"),
        },
        {
            "name": "synthetic_validation",
            "status": "completed",
            "network_calls": False,
            "summary": validation_report.get("summary"),
        },
        {
            "name": "proposal_inbox",
            "status": "completed",
            "network_calls": False,
            "summary": inbox_report.get("summary"),
        },
        {
            "name": "approved_apply_plan",
            "status": "completed",
            "network_calls": False,
            "summary": apply_plan.get("summary"),
        },
        {
            "name": "snapshot_evaluation",
            "status": "completed",
            "network_calls": False,
            "snapshot_eval_enabled": snapshot_eval_report.get("snapshot_eval_enabled"),
        },
        {
            "name": "evaluation_report",
            "status": "completed",
            "network_calls": False,
            "quality_gate": evaluation_report.get("quality_gate"),
        },
    ]


def _quality_gate(
    *,
    llm_report: Mapping[str, Any],
    validation_report: Mapping[str, Any],
    inbox_report: Mapping[str, Any],
    apply_plan: Mapping[str, Any],
    snapshot_eval_report: Mapping[str, Any],
) -> JsonDict:
    reasons: list[str] = []
    if (
        int(llm_report.get("llm_review_summary", {}).get("proposals_prepared") or 0)
        <= 0
    ):
        reasons.append("no_proposals_prepared")
    if int(validation_report.get("summary", {}).get("errors") or 0) > 0:
        reasons.append("validation_errors")
    if int(inbox_report.get("summary", {}).get("approved") or 0) <= 0:
        reasons.append("no_approved_inbox_items")
    if int(apply_plan.get("summary", {}).get("approved_operations") or 0) <= 0:
        reasons.append("no_approved_apply_operations")
    if snapshot_eval_report.get("snapshot_eval_enabled") is not True:
        reasons.append("snapshot_eval_not_enabled")
    return {
        "status": "passed" if not reasons else "needs_review",
        "reasons": reasons or ["full_offline_contour_passed"],
    }


def _write_artifact_if_enabled(
    config: FullIntegrationSmokeConfig,
    run_id: str,
    name: str,
    payload: Mapping[str, Any],
    artifacts: list[JsonDict],
) -> None:
    if not config.write_artifacts:
        return
    config.artifacts_dir.mkdir(parents=True, exist_ok=True)
    path = config.artifacts_dir / f"{run_id}.{name}.json"
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    artifacts.append(
        {
            "name": name,
            "path": str(path),
            "schema_version": payload.get("schema_version"),
        }
    )


def _make_run_id(prefix: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_prefix = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in prefix)
    return f"{safe_prefix}-{stamp}"


def _hint_confidence(pack: Mapping[str, Any], *, default: float) -> float:
    hint = pack.get("canonical_hint")
    if isinstance(hint, Mapping):
        try:
            return float(hint.get("confidence", default))
        except (TypeError, ValueError):
            return default
    return default
