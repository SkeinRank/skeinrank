"""Cost-safe OpenRouter live pilot orchestration for the alias scout.

Live mode stays small and explicit. The pilot can call OpenRouter, but proposal
validation/submission through SkeinRank remains opt-in and runtime mutation stays
blocked.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:  # pragma: no cover - import style depends on how the example is executed.
    from .alias_scout_workflow import (
        LlmReviewConfig,
        run_openrouter_llm_review_workflow,
    )
    from .budget_cache import AgentBudgetCacheConfig
    from .candidate_discovery import CandidateDiscoveryConfig
    from .canonical_hints import CanonicalHintsConfig
    from .demo_report import DemoReportConfig
    from .evidence_sampler import EvidenceSamplerConfig, load_jsonl_records
    from .model_provider import ChatCompletionProvider, provider_metadata
    from .openrouter_client import OpenRouterClient
    from .openrouter_tools import get_openrouter_tool_schemas
    from .proposal_submission import (
        ProposalSubmissionConfig,
        build_proposal_submission_plan,
        validate_and_optionally_submit_proposals,
    )
    from .security_profile import SecurityProfileConfig
except ImportError:  # pragma: no cover
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from alias_scout_workflow import LlmReviewConfig, run_openrouter_llm_review_workflow
    from budget_cache import AgentBudgetCacheConfig
    from candidate_discovery import CandidateDiscoveryConfig
    from canonical_hints import CanonicalHintsConfig
    from demo_report import DemoReportConfig
    from evidence_sampler import EvidenceSamplerConfig, load_jsonl_records
    from model_provider import ChatCompletionProvider, provider_metadata
    from openrouter_client import OpenRouterClient
    from openrouter_tools import get_openrouter_tool_schemas
    from proposal_submission import (
        ProposalSubmissionConfig,
        build_proposal_submission_plan,
        validate_and_optionally_submit_proposals,
    )
    from security_profile import SecurityProfileConfig

JsonDict = dict[str, Any]
LIVE_PILOT_PLAN_VERSION = "skeinrank.openrouter_live_pilot_plan.v1"
LIVE_PILOT_REPORT_VERSION = "skeinrank.openrouter_live_pilot_report.v1"


@dataclass(frozen=True)
class OpenRouterLivePilotConfig:
    """Guardrails for manual live OpenRouter pilot runs."""

    max_candidates: int = 2
    max_llm_calls: int = 1
    max_proposals: int = 2
    max_run_cost_usd: float = 0.01
    validate_with_skeinrank: bool = False
    submit_proposals: bool = False
    force_refresh_cache: bool = False
    use_tools: bool = False
    reports_dir: str = "reports/live-pilot"

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any] | None) -> "OpenRouterLivePilotConfig":
        """Create live pilot config from optional JSON config values."""

        if not raw:
            return cls()
        return cls(
            max_candidates=int(raw.get("max_candidates", cls.max_candidates)),
            max_llm_calls=int(raw.get("max_llm_calls", cls.max_llm_calls)),
            max_proposals=int(raw.get("max_proposals", cls.max_proposals)),
            max_run_cost_usd=float(raw.get("max_run_cost_usd", cls.max_run_cost_usd)),
            validate_with_skeinrank=bool(
                raw.get("validate_with_skeinrank", cls.validate_with_skeinrank)
            ),
            submit_proposals=bool(raw.get("submit_proposals", cls.submit_proposals)),
            force_refresh_cache=bool(
                raw.get("force_refresh_cache", cls.force_refresh_cache)
            ),
            use_tools=bool(raw.get("use_tools", cls.use_tools)),
            reports_dir=str(raw.get("reports_dir", cls.reports_dir)),
        )

    def with_overrides(
        self,
        *,
        max_candidates: int | None = None,
        max_llm_calls: int | None = None,
        max_proposals: int | None = None,
        max_run_cost_usd: float | None = None,
        validate_with_skeinrank: bool | None = None,
        submit_proposals: bool | None = None,
        force_refresh_cache: bool | None = None,
        use_tools: bool | None = None,
    ) -> "OpenRouterLivePilotConfig":
        """Return a copy with CLI overrides applied."""

        return OpenRouterLivePilotConfig(
            max_candidates=self.max_candidates
            if max_candidates is None
            else max_candidates,
            max_llm_calls=self.max_llm_calls
            if max_llm_calls is None
            else max_llm_calls,
            max_proposals=self.max_proposals
            if max_proposals is None
            else max_proposals,
            max_run_cost_usd=self.max_run_cost_usd
            if max_run_cost_usd is None
            else max_run_cost_usd,
            validate_with_skeinrank=self.validate_with_skeinrank
            if validate_with_skeinrank is None
            else validate_with_skeinrank,
            submit_proposals=self.submit_proposals
            if submit_proposals is None
            else submit_proposals,
            force_refresh_cache=self.force_refresh_cache
            if force_refresh_cache is None
            else force_refresh_cache,
            use_tools=self.use_tools if use_tools is None else use_tools,
            reports_dir=self.reports_dir,
        )

    def to_dict(self) -> JsonDict:
        """Return a JSON-serializable config summary."""

        return {
            "max_candidates": self.max_candidates,
            "max_llm_calls": self.max_llm_calls,
            "max_proposals": self.max_proposals,
            "max_run_cost_usd": self.max_run_cost_usd,
            "validate_with_skeinrank": self.validate_with_skeinrank,
            "submit_proposals": self.submit_proposals,
            "force_refresh_cache": self.force_refresh_cache,
            "use_tools": self.use_tools,
            "reports_dir": self.reports_dir,
        }


def build_openrouter_live_pilot_plan(
    *,
    pilot_config: OpenRouterLivePilotConfig | None = None,
    openrouter_model: str,
    openrouter_api_key_env: str = "OPENROUTER_API_KEY",
    skeinrank_api_url: str,
    profile_name: str | None = None,
    binding_id: int | None = None,
    proposal_source_name: str = "openrouter-alias-scout",
) -> JsonDict:
    """Build an offline plan for a cost-safe live OpenRouter pilot."""

    cfg = pilot_config or OpenRouterLivePilotConfig()
    return {
        "schema_version": LIVE_PILOT_PLAN_VERSION,
        "runner": "openrouter_alias_scout",
        "openrouter_calls": False,
        "skeinrank_api_calls": False,
        "openrouter_model": openrouter_model,
        "model_provider": {
            "schema_version": "skeinrank.model_provider_metadata.v1",
            "provider_name": "openrouter",
            "provider_type": "openrouter",
            "model": openrouter_model,
            "chat_completion_interface": True,
        },
        "openrouter_api_key_env": openrouter_api_key_env,
        "skeinrank_api_url": skeinrank_api_url,
        "profile_name": profile_name,
        "binding_id": binding_id,
        "proposal_source_name": proposal_source_name,
        "pilot_config": cfg.to_dict(),
        "safety": {
            "requires_explicit_run_flag": True,
            "requires_openrouter_api_key": True,
            "validate_with_skeinrank_default": False,
            "submit_proposals_default": False,
            "snapshot_publish_enabled": False,
            "runtime_mutation_enabled": False,
            "direct_dictionary_write_enabled": False,
            "cost_guardrails_enabled": True,
        },
        "recommended_command": (
            "OPENROUTER_API_KEY=... python examples/agents/"
            "openrouter_alias_scout/run_alias_scout.py "
            "--run-openrouter-live-pilot --write-openrouter-live-pilot-report "
            "examples/agents/openrouter_alias_scout/reports/live-pilot/report.json"
        ),
    }


def run_openrouter_live_pilot(
    *,
    failed_queries: Sequence[Mapping[str, Any]],
    evidence_records_path: Path,
    openrouter_client: OpenRouterClient | None = None,
    model_provider: ChatCompletionProvider | None = None,
    pilot_config: OpenRouterLivePilotConfig | None = None,
    candidate_config: CandidateDiscoveryConfig | None = None,
    evidence_config: EvidenceSamplerConfig | None = None,
    demo_config: DemoReportConfig | None = None,
    canonical_hints_config: CanonicalHintsConfig | None = None,
    submission_config: ProposalSubmissionConfig | None = None,
    security_config: SecurityProfileConfig | None = None,
    skeinrank_client: Any | None = None,
    openrouter_model: str = "openai/gpt-4o-mini",
    profile_name: str | None = None,
    binding_id: int | None = None,
    proposal_source_name: str = "openrouter-alias-scout",
) -> JsonDict:
    """Run the live OpenRouter pilot with hard limits and optional API validation."""

    cfg = pilot_config or OpenRouterLivePilotConfig()
    provider = model_provider or openrouter_client
    if provider is None:
        raise RuntimeError(
            "A model provider or OpenRouter client is required for live pilot runs."
        )
    evidence_records = load_jsonl_records(
        evidence_records_path,
        limit=evidence_config.max_records if evidence_config else None,
    )
    llm_config = LlmReviewConfig(
        max_candidates=cfg.max_candidates,
        min_confidence_to_prepare_proposal=(
            submission_config.min_confidence if submission_config else 0.85
        ),
        temperature=0.0,
        max_tokens=700,
        include_tools=cfg.use_tools,
        response_format_json=True,
        submit_proposals=False,
    )
    budget_config = AgentBudgetCacheConfig(
        max_llm_calls_per_run=cfg.max_llm_calls,
        max_cost_usd_per_run=cfg.max_run_cost_usd,
        cache_enabled=True,
        force_refresh=cfg.force_refresh_cache,
    )
    llm_report = run_openrouter_llm_review_workflow(
        failed_queries,
        evidence_records,
        model_provider=provider,
        candidate_config=candidate_config,
        evidence_config=evidence_config,
        demo_config=demo_config,
        canonical_hints_config=canonical_hints_config,
        llm_config=llm_config,
        budget_cache_config=budget_config,
        binding_id=binding_id,
        profile_name=profile_name,
        proposal_source_name=proposal_source_name,
        openrouter_model=openrouter_model,
        tools=get_openrouter_tool_schemas() if cfg.use_tools else None,
    )
    effective_submission = _submission_config_for_pilot(submission_config, cfg)
    submission_plan = build_proposal_submission_plan(
        llm_report,
        submission_config=effective_submission,
        submit=cfg.submit_proposals,
    )
    submission_report: JsonDict | None = None
    if cfg.validate_with_skeinrank or cfg.submit_proposals:
        if skeinrank_client is None:
            raise RuntimeError(
                "SkeinRank client is required when validate_with_skeinrank or "
                "submit_proposals is enabled."
            )
        submission_report = validate_and_optionally_submit_proposals(
            llm_report,
            client=skeinrank_client,
            submission_config=effective_submission,
            security_config=security_config,
            submit=cfg.submit_proposals,
        )

    summary = _summarize_pilot(
        llm_report=llm_report,
        submission_plan=submission_plan,
        submission_report=submission_report,
    )
    status = _pilot_status(summary, submission_report=submission_report)
    return {
        "schema_version": LIVE_PILOT_REPORT_VERSION,
        "runner": "openrouter_alias_scout",
        "status": status,
        "openrouter_calls": True,
        "skeinrank_api_calls": bool(submission_report is not None),
        "openrouter_model": openrouter_model,
        "model_provider": provider_metadata(provider),
        "profile_name": profile_name,
        "binding_id": binding_id,
        "proposal_source_name": proposal_source_name,
        "pilot_config": cfg.to_dict(),
        "summary": summary,
        "llm_review_report": llm_report,
        "proposal_submission_plan": submission_plan,
        "proposal_submission_report": submission_report,
        "validated_pilot": build_openrouter_validated_pilot_diagnostics(
            pilot_config=cfg,
            summary=summary,
            submission_plan=submission_plan,
            submission_report=submission_report,
        ),
        "safety": {
            "agent_may_mutate_runtime": False,
            "snapshot_publish_enabled": False,
            "direct_dictionary_write_enabled": False,
            "proposal_validation_required_before_submission": True,
            "submit_proposals_explicit": cfg.submit_proposals,
            "runtime_mutation_blocked_actions": [
                "direct_dictionary_write",
                "snapshot_publish",
                "direct_git_push",
                "runtime_mutation",
            ],
        },
        "recommended_exit_code": 0 if status in {"passed", "needs_review"} else 2,
    }


def build_openrouter_validated_pilot_diagnostics(
    *,
    pilot_config: OpenRouterLivePilotConfig,
    summary: Mapping[str, Any],
    submission_plan: Mapping[str, Any],
    submission_report: Mapping[str, Any] | None,
) -> JsonDict:
    """Return operator-facing diagnostics for live validation mode.

    The validated pilot is explicit: OpenRouter may prepare
    proposals, but SkeinRank validation is still the only live backend action by
    default. Submission remains opt-in and runtime mutation stays blocked.
    """

    validation_enabled = bool(
        pilot_config.validate_with_skeinrank or pilot_config.submit_proposals
    )
    validation_results = []
    if isinstance(submission_report, Mapping):
        raw_results = submission_report.get("results")
        if isinstance(raw_results, Sequence) and not isinstance(
            raw_results, (str, bytes)
        ):
            validation_results = [
                dict(item) for item in raw_results if isinstance(item, Mapping)
            ]

    validation_attempts = (
        int(summary.get("validation_passed") or 0)
        + int(summary.get("validation_warning") or 0)
        + int(summary.get("validation_blocked") or 0)
    )
    validation_errors = int(summary.get("errors") or 0)
    eligible = int(submission_plan.get("eligible_proposals") or 0)
    live_calls = int(summary.get("live_openrouter_calls") or 0)
    submitted = int(summary.get("submitted") or 0)
    validation_passed = int(summary.get("validation_passed") or 0)
    validation_warning = int(summary.get("validation_warning") or 0)
    validation_blocked = int(summary.get("validation_blocked") or 0)
    idempotent_existing = int(summary.get("idempotent_existing_aliases") or 0)
    manual_review_required = _count_validation_results(
        validation_results, "manual_review_required"
    )
    validated = submission_report is not None
    validation_coverage = _safe_ratio(validation_attempts, eligible)
    pass_rate = _safe_ratio(validation_passed, validation_attempts)
    warning_rate = _safe_ratio(validation_warning, validation_attempts)
    blocked_rate = _safe_ratio(validation_blocked, validation_attempts)
    idempotent_rate = _safe_ratio(idempotent_existing, validation_attempts)
    manual_review_rate = _safe_ratio(manual_review_required, validation_attempts)

    quality_gates = [
        _validated_gate(
            "validated_pilot_openrouter_called",
            live_calls > 0,
            "OpenRouter produced at least one live review call.",
            {"live_openrouter_calls": live_calls},
        ),
        _validated_gate(
            "validated_pilot_skeinrank_validation_called",
            (not validation_enabled) or validated,
            "SkeinRank validation ran when live validation mode was requested.",
            {"validation_enabled": validation_enabled, "validated": validated},
        ),
        _validated_gate(
            "validated_pilot_validation_coverage",
            (not validation_enabled) or validation_coverage >= 1.0,
            "Every eligible proposal payload was validated by SkeinRank.",
            {
                "actual": validation_coverage,
                "expected": 1.0,
                "eligible_proposals": eligible,
                "validation_attempts": validation_attempts,
            },
        ),
        _validated_gate(
            "validated_pilot_no_validation_errors",
            validation_errors == 0,
            "The live validated pilot finished without validation API errors.",
            {"errors": validation_errors},
        ),
        _validated_gate(
            "validated_pilot_no_runtime_mutation",
            submitted == 0 or pilot_config.submit_proposals,
            "Validate-only mode did not submit pending proposals or mutate runtime.",
            {
                "submitted": submitted,
                "submit_proposals": pilot_config.submit_proposals,
            },
        ),
    ]
    return {
        "schema_version": "skeinrank.openrouter_validated_pilot.v1",
        "enabled": validation_enabled,
        "mode": "submit_pending" if pilot_config.submit_proposals else "validate_only",
        "validated": validated,
        "eligible_proposals": eligible,
        "validation_attempts": validation_attempts,
        "validation_results_total": len(validation_results),
        "metrics": {
            "live_openrouter_calls": live_calls,
            "validation_passed": validation_passed,
            "validation_warning": validation_warning,
            "validation_blocked": validation_blocked,
            "idempotent_existing_aliases": idempotent_existing,
            "manual_review_required": manual_review_required,
            "submitted": submitted,
            "errors": validation_errors,
            "validation_coverage": validation_coverage,
            "validation_pass_rate": pass_rate,
            "validation_warning_rate": warning_rate,
            "validation_blocked_rate": blocked_rate,
            "idempotent_existing_rate": idempotent_rate,
            "manual_review_rate": manual_review_rate,
        },
        "aliases": [
            {
                "alias": item.get("alias_value"),
                "canonical": item.get("canonical_value"),
                "slot": item.get("slot"),
                "status": item.get("status"),
                "validation_status": item.get("validation_status"),
                "decision": item.get("validation_decision"),
                "submitted": bool(item.get("submitted")),
                "error": item.get("error"),
            }
            for item in validation_results
        ],
        "quality_gates": quality_gates,
        "safety": {
            "validation_before_submission": True,
            "submit_proposals_explicit": pilot_config.submit_proposals,
            "runtime_mutation_enabled": False,
            "snapshot_publish_enabled": False,
            "direct_dictionary_write_enabled": False,
        },
    }


def _count_validation_results(
    validation_results: Sequence[Mapping[str, Any]], status: str
) -> int:
    return sum(1 for item in validation_results if item.get("status") == status)


def _safe_ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 1.0 if numerator == 0 else 0.0
    return round(numerator / denominator, 4)


def _validated_gate(
    name: str, passed: bool, message: str, details: Mapping[str, Any]
) -> JsonDict:
    return {
        "name": name,
        "status": "passed" if passed else "failed",
        "message": message,
        "details": dict(details),
    }


def _submission_config_for_pilot(
    submission_config: ProposalSubmissionConfig | None,
    pilot_config: OpenRouterLivePilotConfig,
) -> ProposalSubmissionConfig:
    base = submission_config or ProposalSubmissionConfig()
    return ProposalSubmissionConfig(
        max_proposals_per_run=min(
            base.max_proposals_per_run,
            max(0, pilot_config.max_proposals),
        ),
        min_confidence=base.min_confidence,
        require_validation_status=base.require_validation_status,
        submit_enabled=bool(pilot_config.submit_proposals),
        stop_on_error=base.stop_on_error,
        treat_existing_alias_as_idempotent=base.treat_existing_alias_as_idempotent,
        manual_review_on_warning=base.manual_review_on_warning,
    )


def _summarize_pilot(
    *,
    llm_report: Mapping[str, Any],
    submission_plan: Mapping[str, Any],
    submission_report: Mapping[str, Any] | None,
) -> JsonDict:
    review_summary = dict(llm_report.get("llm_review_summary") or {})
    budget_summary = dict(llm_report.get("budget_cache_summary") or {})
    usage = dict(budget_summary.get("usage") or {})
    summary: JsonDict = {
        "candidates_sent_to_model": int(
            review_summary.get("candidates_sent_to_model") or 0
        ),
        "proposals_prepared": int(review_summary.get("proposals_prepared") or 0),
        "eligible_proposals": int(submission_plan.get("eligible_proposals") or 0),
        "live_openrouter_calls": int(review_summary.get("live_openrouter_calls") or 0),
        "cache_hits": int(review_summary.get("cache_hits") or 0),
        "skipped_due_to_budget": int(review_summary.get("skipped_due_to_budget") or 0),
        "estimated_cost_usd": float(usage.get("estimated_cost_usd") or 0.0),
        "total_tokens": int(usage.get("total_tokens") or 0),
        "validation_passed": 0,
        "validation_warning": 0,
        "validation_blocked": 0,
        "idempotent_existing_aliases": 0,
        "submitted": 0,
        "errors": 0,
    }
    if submission_report is not None:
        submission_summary = dict(submission_report.get("summary") or {})
        summary.update(
            {
                "validation_passed": int(
                    submission_summary.get("validation_passed") or 0
                ),
                "validation_warning": int(
                    submission_summary.get("validation_warnings")
                    or submission_summary.get("validation_warning")
                    or 0
                ),
                "validation_blocked": int(
                    submission_summary.get("validation_blocked") or 0
                ),
                "idempotent_existing_aliases": int(
                    submission_summary.get("idempotent_existing_aliases") or 0
                ),
                "submitted": int(submission_summary.get("submitted") or 0),
                "errors": int(submission_summary.get("errors") or 0),
            }
        )
    return summary


def _pilot_status(
    summary: Mapping[str, Any], *, submission_report: Mapping[str, Any] | None
) -> str:
    if int(summary.get("errors") or 0) > 0:
        return "failed"
    if int(summary.get("candidates_sent_to_model") or 0) <= 0:
        return "needs_review"
    if int(summary.get("proposals_prepared") or 0) <= 0:
        return "needs_review"
    if (
        submission_report is not None
        and int(summary.get("validation_passed") or 0) <= 0
    ):
        return "needs_review"
    return "passed"
