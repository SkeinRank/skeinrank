"""Reference OpenRouter alias scout runner skeleton.

Patch 40F intentionally keeps this runner LLM-free. It proves the agent-side
configuration, input loading, idempotency key strategy, and SkeinRank REST client
without introducing LangGraph/CrewAI or calling OpenRouter yet.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

try:  # pragma: no cover - import style depends on how the example is executed.
    from .agent_evaluation import (
        AgentEvaluationConfig,
        build_agent_evaluation_report,
        load_evaluation_outcomes,
        load_json_report,
    )
    from .agent_run_tracking import (
        AgentRunTrackingConfig,
        build_agent_run_tracking_report,
    )
    from .alias_scout_workflow import (
        LlmReviewConfig,
        build_llm_review_plan,
        run_openrouter_llm_review_workflow,
    )
    from .approved_apply import (
        ApprovedApplyConfig,
        build_approved_proposals_apply_plan,
        build_snapshot_evaluation_report,
    )
    from .approved_apply import (
        load_json_report as load_apply_json_report,
    )
    from .artifact_standard import (
        ArtifactStandardConfig,
        discover_artifact_files,
        write_artifact_manifest,
    )
    from .budget_cache import (
        AgentBudgetCacheConfig,
        build_budget_cache_plan,
        clear_llm_review_cache,
    )
    from .candidate_discovery import (
        CandidateDiscoveryConfig,
        build_candidate_discovery_report,
        build_candidate_fact_pack,
        discover_alias_candidates,
    )
    from .canonical_hints import (
        CanonicalHintsConfig,
        build_canonical_hints_report,
        enrich_candidate_pack_with_canonical_hints,
    )
    from .demo_report import (
        DemoReportConfig,
        build_alias_scout_demo_report,
        build_demo_review_prompt,
    )
    from .deployment_recipe import (
        AgentDeploymentConfig,
        build_agent_deployment_recipe,
    )
    from .elasticsearch_source import (
        ElasticsearchSourceClient,
        ElasticsearchSourceConfig,
        build_elasticsearch_evidence_report,
        collect_elasticsearch_evidence_records,
    )
    from .evidence_sampler import (
        EvidenceSamplerConfig,
        build_candidate_evidence_pack,
        build_evidence_sampling_report,
        load_jsonl_records,
        sample_evidence_windows,
    )
    from .integration_smoke import (
        FullIntegrationSmokeConfig,
        build_full_integration_smoke_report,
    )
    from .new_alias_smoke import (
        NewAliasSmokeConfig,
        build_new_alias_smoke_llm_report,
        build_new_alias_smoke_plan,
        run_new_alias_smoke_test,
    )
    from .openrouter_client import OpenRouterClient
    from .openrouter_tools import get_openrouter_tool_schemas
    from .prompts import (
        SYSTEM_PROMPT,
        build_alias_review_prompt,
        build_sample_candidate_pack,
    )
    from .proposal_inbox import (
        ProposalInboxConfig,
        build_proposal_inbox_report,
        load_review_decisions,
    )
    from .proposal_submission import (
        ProposalSubmissionConfig,
        build_proposal_submission_plan,
        validate_and_optionally_submit_proposals,
    )
    from .real_es_validation import (
        RealElasticsearchValidationConfig,
        index_real_elasticsearch_validation_docs,
        run_real_elasticsearch_validation_scenario,
        write_real_elasticsearch_validation_fixtures,
    )
    from .scheduled_runner import (
        ScheduledRunnerConfig,
        build_scheduled_cycle_report,
        make_scheduled_run_id,
        write_cycle_artifact,
        write_cycle_manifest,
    )
    from .security_profile import (
        SecurityProfileConfig,
        assert_security_allows_llm_review,
        build_security_profile_report,
    )
    from .skeinrank_client import SkeinRankAgentClient
except ImportError:  # pragma: no cover
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from agent_evaluation import (
        AgentEvaluationConfig,
        build_agent_evaluation_report,
        load_evaluation_outcomes,
        load_json_report,
    )
    from agent_run_tracking import (
        AgentRunTrackingConfig,
        build_agent_run_tracking_report,
    )
    from alias_scout_workflow import (
        LlmReviewConfig,
        build_llm_review_plan,
        run_openrouter_llm_review_workflow,
    )
    from approved_apply import (
        ApprovedApplyConfig,
        build_approved_proposals_apply_plan,
        build_snapshot_evaluation_report,
    )
    from approved_apply import (
        load_json_report as load_apply_json_report,
    )
    from artifact_standard import (
        ArtifactStandardConfig,
        discover_artifact_files,
        write_artifact_manifest,
    )
    from budget_cache import (
        AgentBudgetCacheConfig,
        build_budget_cache_plan,
        clear_llm_review_cache,
    )
    from candidate_discovery import (
        CandidateDiscoveryConfig,
        build_candidate_discovery_report,
        build_candidate_fact_pack,
        discover_alias_candidates,
    )
    from canonical_hints import (
        CanonicalHintsConfig,
        build_canonical_hints_report,
        enrich_candidate_pack_with_canonical_hints,
    )
    from demo_report import (
        DemoReportConfig,
        build_alias_scout_demo_report,
        build_demo_review_prompt,
    )
    from deployment_recipe import (
        AgentDeploymentConfig,
        build_agent_deployment_recipe,
    )
    from elasticsearch_source import (
        ElasticsearchSourceClient,
        ElasticsearchSourceConfig,
        build_elasticsearch_evidence_report,
        collect_elasticsearch_evidence_records,
    )
    from evidence_sampler import (
        EvidenceSamplerConfig,
        build_candidate_evidence_pack,
        build_evidence_sampling_report,
        load_jsonl_records,
        sample_evidence_windows,
    )
    from integration_smoke import (
        FullIntegrationSmokeConfig,
        build_full_integration_smoke_report,
    )
    from new_alias_smoke import (
        NewAliasSmokeConfig,
        build_new_alias_smoke_llm_report,
        build_new_alias_smoke_plan,
        run_new_alias_smoke_test,
    )
    from openrouter_client import OpenRouterClient
    from openrouter_tools import get_openrouter_tool_schemas
    from prompts import (
        SYSTEM_PROMPT,
        build_alias_review_prompt,
        build_sample_candidate_pack,
    )
    from proposal_inbox import (
        ProposalInboxConfig,
        build_proposal_inbox_report,
        load_review_decisions,
    )
    from proposal_submission import (
        ProposalSubmissionConfig,
        build_proposal_submission_plan,
        validate_and_optionally_submit_proposals,
    )
    from real_es_validation import (
        RealElasticsearchValidationConfig,
        index_real_elasticsearch_validation_docs,
        run_real_elasticsearch_validation_scenario,
        write_real_elasticsearch_validation_fixtures,
    )
    from scheduled_runner import (
        ScheduledRunnerConfig,
        build_scheduled_cycle_report,
        make_scheduled_run_id,
        write_cycle_artifact,
        write_cycle_manifest,
    )
    from security_profile import (
        SecurityProfileConfig,
        assert_security_allows_llm_review,
        build_security_profile_report,
    )
    from skeinrank_client import SkeinRankAgentClient

JsonDict = dict[str, Any]


@dataclass(frozen=True)
class AgentRunnerConfig:
    """Runtime config for the reference alias scout runner."""

    skeinrank_api_url: str
    skeinrank_role: str
    api_token_env: str | None
    openrouter_api_key_env: str
    openrouter_model: str
    default_profile_name: str | None
    default_binding_id: int | None
    proposal_source_name: str
    failed_queries_path: Path
    evidence_records_path: Path
    evaluation_outcomes_path: Path | None
    max_queries_per_run: int
    candidate_discovery: CandidateDiscoveryConfig
    canonical_hints: CanonicalHintsConfig
    evidence_sampler: EvidenceSamplerConfig
    elasticsearch_source: ElasticsearchSourceConfig
    agent_tracking: AgentRunTrackingConfig
    demo_report: DemoReportConfig
    llm_review: LlmReviewConfig
    budget_cache: AgentBudgetCacheConfig
    security_profile: SecurityProfileConfig
    evaluation: AgentEvaluationConfig
    deployment: AgentDeploymentConfig
    proposal_submission: ProposalSubmissionConfig
    proposal_inbox: ProposalInboxConfig
    approved_apply: ApprovedApplyConfig
    new_alias_smoke: NewAliasSmokeConfig
    scheduled_runner: ScheduledRunnerConfig
    artifact_standard: ArtifactStandardConfig
    integration_smoke: FullIntegrationSmokeConfig
    real_elasticsearch_validation: RealElasticsearchValidationConfig
    openrouter_base_url: str
    openrouter_app_title: str
    openrouter_http_referer: str | None
    dry_run: bool = True

    @classmethod
    def from_file(cls, path: Path) -> "AgentRunnerConfig":
        raw = json.loads(path.read_text(encoding="utf-8"))
        base_dir = path.parent
        repo_root = base_dir.parents[2] if len(base_dir.parents) >= 3 else base_dir
        failed_queries = Path(
            raw.get("failed_queries_path", "failed_queries.example.jsonl")
        )
        if not failed_queries.is_absolute():
            failed_queries = base_dir / failed_queries
        evidence_records = Path(
            raw.get("evidence_records_path", "evidence_records.example.jsonl")
        )
        if not evidence_records.is_absolute():
            evidence_records = base_dir / evidence_records
        raw_evaluation_outcomes = raw.get("evaluation_outcomes_path")
        evaluation_outcomes: Path | None = None
        if raw_evaluation_outcomes:
            evaluation_outcomes = Path(str(raw_evaluation_outcomes))
            if not evaluation_outcomes.is_absolute():
                evaluation_outcomes = base_dir / evaluation_outcomes
        binding_id = raw.get("default_binding_id")
        return cls(
            skeinrank_api_url=str(
                os.getenv(
                    "SKEINRANK_AGENT_API_URL",
                    raw.get("skeinrank_api_url", "http://127.0.0.1:8010"),
                )
            ),
            skeinrank_role=str(
                os.getenv(
                    "SKEINRANK_AGENT_ROLE", raw.get("skeinrank_role", "contributor")
                )
            ),
            api_token_env=raw.get("api_token_env", "SKEINRANK_AGENT_API_TOKEN"),
            openrouter_api_key_env=str(
                raw.get("openrouter_api_key_env", "OPENROUTER_API_KEY")
            ),
            openrouter_model=str(
                os.getenv(
                    "OPENROUTER_MODEL",
                    raw.get("openrouter_model", "openai/gpt-4o-mini"),
                )
            ),
            default_profile_name=raw.get("default_profile_name"),
            default_binding_id=int(binding_id) if binding_id is not None else None,
            proposal_source_name=str(
                raw.get("proposal_source_name", "openrouter-alias-scout")
            ),
            failed_queries_path=failed_queries,
            evidence_records_path=evidence_records,
            evaluation_outcomes_path=evaluation_outcomes,
            max_queries_per_run=int(raw.get("max_queries_per_run", 50)),
            candidate_discovery=CandidateDiscoveryConfig.from_mapping(
                raw.get("candidate_discovery")
            ),
            canonical_hints=CanonicalHintsConfig.from_mapping(
                raw.get("canonical_hints")
            ),
            evidence_sampler=EvidenceSamplerConfig.from_mapping(
                raw.get("evidence_sampler")
            ),
            elasticsearch_source=ElasticsearchSourceConfig.from_mapping(
                raw.get("elasticsearch_source")
            ),
            agent_tracking=AgentRunTrackingConfig.from_mapping(
                raw.get("agent_tracking"), base_dir=base_dir
            ),
            demo_report=DemoReportConfig.from_mapping(raw.get("demo_report")),
            llm_review=LlmReviewConfig.from_mapping(raw.get("llm_review")),
            budget_cache=AgentBudgetCacheConfig.from_mapping(
                raw.get("budget_cache"), base_dir=base_dir
            ),
            security_profile=SecurityProfileConfig.from_mapping(
                raw.get("security_profile")
            ),
            evaluation=AgentEvaluationConfig.from_mapping(raw.get("evaluation")),
            deployment=AgentDeploymentConfig.from_mapping(
                raw.get("deployment"), repo_root=repo_root
            ),
            proposal_submission=ProposalSubmissionConfig.from_mapping(
                raw.get("proposal_submission")
            ),
            proposal_inbox=ProposalInboxConfig.from_mapping(
                raw.get("proposal_inbox"), base_dir=base_dir
            ),
            approved_apply=ApprovedApplyConfig.from_mapping(
                raw.get("approved_apply"), base_dir=base_dir
            ),
            new_alias_smoke=NewAliasSmokeConfig.from_mapping(
                raw.get("new_alias_smoke")
            ),
            scheduled_runner=ScheduledRunnerConfig.from_mapping(
                raw.get("scheduled_runner"), base_dir=base_dir
            ),
            artifact_standard=ArtifactStandardConfig.from_mapping(
                raw.get("artifact_standard"), base_dir=base_dir
            ),
            integration_smoke=FullIntegrationSmokeConfig.from_mapping(
                raw.get("integration_smoke"), base_dir=base_dir
            ),
            real_elasticsearch_validation=(
                RealElasticsearchValidationConfig.from_mapping(
                    raw.get("real_elasticsearch_validation"), base_dir=base_dir
                )
            ),
            openrouter_base_url=str(
                os.getenv(
                    "OPENROUTER_BASE_URL",
                    raw.get("openrouter_base_url", "https://openrouter.ai/api/v1"),
                )
            ),
            openrouter_app_title=str(
                raw.get("openrouter_app_title", "SkeinRank OpenRouter Alias Scout")
            ),
            openrouter_http_referer=raw.get("openrouter_http_referer"),
            dry_run=bool(raw.get("dry_run", True)),
        )

    def api_token(self) -> str | None:
        """Read the configured SkeinRank API token from the environment."""

        return os.getenv(self.api_token_env) if self.api_token_env else None

    def openrouter_api_key(self) -> str | None:
        """Read the configured OpenRouter API key from the environment."""

        return os.getenv(self.openrouter_api_key_env)


def load_failed_queries(path: Path, *, limit: int | None = None) -> list[JsonDict]:
    """Load failed-query examples from JSONL for future candidate discovery."""

    rows: list[JsonDict] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), 1
    ):
        if not line.strip():
            continue
        value = json.loads(line)
        if isinstance(value, str):
            value = {"query": value}
        if not isinstance(value, dict) or not value.get("query"):
            raise ValueError(f"Invalid failed query row at {path}:{line_number}")
        rows.append(value)
        if limit is not None and len(rows) >= limit:
            break
    return rows


def make_candidate_idempotency_key(
    *, source_name: str, binding_id: int | None, profile_name: str | None, query: str
) -> str:
    """Build a deterministic retry key for future proposals derived from a query."""

    scope = (
        f"binding:{binding_id}"
        if binding_id is not None
        else f"profile:{profile_name or 'unknown'}"
    )
    digest = sha256(query.strip().lower().encode("utf-8")).hexdigest()[:16]
    return f"{source_name}:{scope}:query:{digest}"


def build_run_plan(
    config: AgentRunnerConfig, failed_queries: list[JsonDict]
) -> JsonDict:
    """Return a deterministic dry-run plan for the agent foundation step."""

    scoped_queries = failed_queries[: config.max_queries_per_run]
    return {
        "schema_version": "skeinrank.agent_run_plan.v1",
        "runner": "openrouter_alias_scout",
        "llm_enabled": False,
        "dry_run": config.dry_run,
        "skeinrank_api_url": config.skeinrank_api_url,
        "openrouter_model": config.openrouter_model,
        "proposal_source_name": config.proposal_source_name,
        "default_profile_name": config.default_profile_name,
        "default_binding_id": config.default_binding_id,
        "queries_loaded": len(scoped_queries),
        "candidate_discovery_enabled": True,
        "evidence_sampling_enabled": True,
        "evidence_records_path": str(config.evidence_records_path),
        "budget_cache_enabled": config.budget_cache.cache_enabled,
        "max_llm_calls_per_run": config.budget_cache.max_llm_calls_per_run,
        "next_steps": [
            "Patch 40G added OpenRouter tool schemas and prompts.",
            "Patch 40H added candidate discovery and pruning.",
            "Patch 40I added compact evidence sampling.",
            "Patch 40K adds the local E2E demo report.",
            "Patch 40J adds OpenRouter execution and a LangGraph-ready workflow.",
            "Patch 40L adds a service-account security profile.",
            "Patch 40M adds run budgets and JSON response caching.",
            "Patch 40N adds offline agent evaluation reports.",
            "Patch 40O adds a Docker Compose deployment recipe.",
            "Patch 41A adds canonical hints and stronger review packs.",
            "Patch 41B adds safe validation/submission of ready proposal payloads.",
            "Patch 41E adds an optional Elasticsearch evidence connector.",
            "Patch 41F adds local run/document tracking and content hashes.",
            "Patch 41G adds an offline proposal inbox/review workflow.",
            "Patch 41H adds approved-proposal apply planning and snapshot evaluation.",
            "Patch 41I adds scheduled/worker-mode agent cycle orchestration.",
            "Patch 42A adds a one-command full agent integration smoke test.",
            "Patch 42B adds a reproducible real Elasticsearch validation scenario.",
            "Patch 42C standardizes report/artifact manifests.",
        ],
        "sample_queries": [
            {
                "query": row["query"],
                "idempotency_key": make_candidate_idempotency_key(
                    source_name=config.proposal_source_name,
                    binding_id=config.default_binding_id,
                    profile_name=config.default_profile_name,
                    query=row["query"],
                ),
            }
            for row in scoped_queries[:5]
        ],
    }


def build_client(config: AgentRunnerConfig) -> SkeinRankAgentClient:
    """Create the REST client used by the runner."""

    return SkeinRankAgentClient(
        base_url=config.skeinrank_api_url,
        role=config.skeinrank_role,
        api_token=config.api_token(),
    )


def build_openrouter_client(config: AgentRunnerConfig) -> OpenRouterClient:
    """Create the OpenRouter client used by live LLM review."""

    api_key = config.openrouter_api_key()
    if not api_key:
        raise RuntimeError(
            f"OpenRouter API key is required. Set {config.openrouter_api_key_env} "
            "or use --print-llm-review-plan for an offline preview."
        )
    return OpenRouterClient(
        api_key=api_key,
        base_url=config.openrouter_base_url,
        app_title=config.openrouter_app_title,
        http_referer=config.openrouter_http_referer,
    )


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the SkeinRank alias scout skeleton."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).with_name("agent_config.example.json"),
        help="Path to agent config JSON.",
    )
    parser.add_argument(
        "--list-bindings",
        action="store_true",
        help="Call SkeinRank /v1/tools/bindings and print available contexts.",
    )
    parser.add_argument(
        "--dry-run-plan",
        action="store_true",
        help="Print the local dry-run plan without calling OpenRouter.",
    )
    parser.add_argument(
        "--print-tool-schemas",
        action="store_true",
        help="Print OpenRouter/OpenAI-compatible SkeinRank tool schemas.",
    )
    parser.add_argument(
        "--print-system-prompt",
        action="store_true",
        help="Print the alias scout system prompt.",
    )
    parser.add_argument(
        "--print-sample-review-prompt",
        action="store_true",
        help="Print a sample alias-review prompt for local inspection.",
    )
    parser.add_argument(
        "--print-canonical-hints",
        action="store_true",
        help="Print configured 41A canonical hints without network calls.",
    )
    parser.add_argument(
        "--discover-candidates",
        action="store_true",
        help="Mine alias-like candidates from failed-query JSONL without LLM calls.",
    )
    parser.add_argument(
        "--print-sample-candidate-pack",
        action="store_true",
        help="Print the top discovered candidate as a compact fact pack.",
    )
    parser.add_argument(
        "--sample-evidence",
        action="store_true",
        help=(
            "Sample compact evidence windows for discovered candidates without LLM "
            "calls."
        ),
    )
    parser.add_argument(
        "--print-sample-evidence-pack",
        action="store_true",
        help=(
            "Print the top candidate with sampled evidence windows as an "
            "LLM-ready pack."
        ),
    )
    parser.add_argument(
        "--print-elasticsearch-evidence-plan",
        action="store_true",
        help=(
            "Print the 41E Elasticsearch evidence connector plan without "
            "network calls."
        ),
    )
    parser.add_argument(
        "--sample-evidence-from-elasticsearch",
        action="store_true",
        help=(
            "Fetch Elasticsearch hits for discovered candidates and sample "
            "evidence windows."
        ),
    )
    parser.add_argument(
        "--write-elasticsearch-evidence-records",
        type=Path,
        help="Write normalized Elasticsearch evidence records to this JSONL path.",
    )
    parser.add_argument(
        "--elasticsearch-url",
        help="Override elasticsearch_source.url for this run.",
    )
    parser.add_argument(
        "--elasticsearch-index",
        help="Override elasticsearch_source.index for this run.",
    )
    parser.add_argument(
        "--elasticsearch-text-field",
        action="append",
        help="Override Elasticsearch text fields. Can be passed multiple times.",
    )
    parser.add_argument(
        "--elasticsearch-max-docs",
        type=int,
        help="Override elasticsearch_source.max_docs_per_candidate for this run.",
    )
    parser.add_argument(
        "--elasticsearch-api-key-env",
        help="Override the environment variable used for the optional ES API key.",
    )
    parser.add_argument(
        "--print-agent-tracking-plan",
        action="store_true",
        help="Print the 41F local run/document tracking plan without writing the ledger.",
    )
    parser.add_argument(
        "--write-agent-tracking-report",
        type=Path,
        help="Write a 41F run/document tracking report to this JSON path.",
    )
    parser.add_argument(
        "--append-agent-tracking-ledger",
        action="store_true",
        help="Append document visit entries to the configured local tracking ledger.",
    )
    parser.add_argument(
        "--agent-tracking-ledger",
        type=Path,
        help="Override agent_tracking.ledger_path for this run.",
    )
    parser.add_argument(
        "--run-demo-report",
        action="store_true",
        help="Run the local E2E candidate/evidence demo and print a JSON report.",
    )
    parser.add_argument(
        "--write-demo-report",
        type=Path,
        help="Write the local E2E demo report to this JSON path.",
    )
    parser.add_argument(
        "--print-demo-review-prompt",
        action="store_true",
        help="Print the first real-sample review prompt without calling OpenRouter.",
    )
    parser.add_argument(
        "--print-llm-review-plan",
        action="store_true",
        help=(
            "Print the OpenRouter/LangGraph-ready review plan without calling "
            "OpenRouter."
        ),
    )
    parser.add_argument(
        "--llm-review",
        action="store_true",
        help=(
            "Call OpenRouter for structured alias judgments. Requires the "
            "configured OPENROUTER_API_KEY env var."
        ),
    )
    parser.add_argument(
        "--write-llm-review-report",
        type=Path,
        help="Call OpenRouter and write the LLM review report to this JSON path.",
    )
    parser.add_argument(
        "--model",
        help="Override the configured OpenRouter model for this run.",
    )
    parser.add_argument(
        "--max-candidates",
        type=int,
        help="Override llm_review.max_candidates for this run.",
    )
    parser.add_argument(
        "--print-security-profile",
        action="store_true",
        help="Print the sanitized agent security profile without network calls.",
    )
    parser.add_argument(
        "--check-security-profile",
        action="store_true",
        help="Validate the sanitized agent security profile and exit non-zero on errors.",
    )
    parser.add_argument(
        "--print-budget-cache-plan",
        action="store_true",
        help="Print the 40M run budget/cache plan without network calls.",
    )
    parser.add_argument(
        "--clear-llm-cache",
        action="store_true",
        help="Delete the configured local LLM response cache and print a report.",
    )
    parser.add_argument(
        "--max-llm-calls",
        type=int,
        help="Override budget_cache.max_llm_calls_per_run for this run.",
    )
    parser.add_argument(
        "--max-run-cost-usd",
        type=float,
        help="Override budget_cache.max_cost_usd_per_run for this run.",
    )
    parser.add_argument(
        "--no-llm-cache",
        action="store_true",
        help="Disable the local LLM response cache for this run.",
    )
    parser.add_argument(
        "--force-refresh-cache",
        action="store_true",
        help="Ignore existing cached LLM responses and refresh them when live calls run.",
    )
    parser.add_argument(
        "--run-evaluation-report",
        action="store_true",
        help="Build an offline 40N agent evaluation report and print JSON.",
    )
    parser.add_argument(
        "--write-evaluation-report",
        type=Path,
        help="Write the offline 40N agent evaluation report to this JSON path.",
    )
    parser.add_argument(
        "--llm-review-report",
        type=Path,
        help="Evaluate an existing skeinrank.agent_llm_review_report.v1 JSON file.",
    )
    parser.add_argument(
        "--evaluation-outcomes",
        type=Path,
        help="Optional JSONL with human/policy outcomes for accepted/rejected counts.",
    )
    parser.add_argument(
        "--print-deployment-recipe",
        action="store_true",
        help="Print the 40O Docker Compose deployment recipe without network calls.",
    )
    parser.add_argument(
        "--write-deployment-recipe",
        type=Path,
        help="Write the 40O deployment recipe JSON to this path.",
    )
    parser.add_argument(
        "--print-proposal-submission-plan",
        action="store_true",
        help="Preview validation/submission for a saved LLM review report without API calls.",
    )
    parser.add_argument(
        "--validate-ready-proposals",
        action="store_true",
        help="Validate ready proposal payloads through /v1/tools/validate-alias.",
    )
    parser.add_argument(
        "--submit-ready-proposals",
        action="store_true",
        help=(
            "Validate and then submit ready payloads through /v1/tools/suggest-alias. "
            "Requires explicit proposal/security config changes."
        ),
    )
    parser.add_argument(
        "--write-proposal-submission-report",
        type=Path,
        help="Write the 41B validation/submission report to this JSON path.",
    )
    parser.add_argument(
        "--print-proposal-inbox-plan",
        action="store_true",
        help="Print the 41G offline proposal inbox/review plan.",
    )
    parser.add_argument(
        "--build-proposal-inbox",
        action="store_true",
        help="Build the 41G proposal review inbox from saved reports.",
    )
    parser.add_argument(
        "--write-proposal-inbox",
        type=Path,
        help="Write the 41G proposal review inbox JSON to this path.",
    )
    parser.add_argument(
        "--proposal-submission-report",
        type=Path,
        help="Saved skeinrank.agent_proposal_submission_report.v1 JSON input.",
    )
    parser.add_argument(
        "--review-decisions",
        type=Path,
        help="Optional JSONL with local approve/reject/edit/defer review decisions.",
    )
    parser.add_argument(
        "--max-inbox-items",
        type=int,
        help="Override proposal_inbox.max_items for this run.",
    )
    parser.add_argument(
        "--print-approved-apply-plan",
        action="store_true",
        help="Print the 41H offline approved-proposal apply plan config.",
    )
    parser.add_argument(
        "--build-approved-apply-plan",
        action="store_true",
        help="Build the 41H approved-proposal apply plan from a proposal inbox report.",
    )
    parser.add_argument(
        "--write-approved-apply-plan",
        type=Path,
        help="Write the 41H approved-proposal apply plan JSON to this path.",
    )
    parser.add_argument(
        "--proposal-inbox-report",
        type=Path,
        help="Saved skeinrank.agent_proposal_inbox.v1 JSON input for 41H apply planning.",
    )
    parser.add_argument(
        "--run-snapshot-evaluation",
        action="store_true",
        help="Build a 41H offline snapshot evaluation report.",
    )
    parser.add_argument(
        "--write-snapshot-evaluation-report",
        type=Path,
        help="Write the 41H snapshot evaluation report JSON to this path.",
    )
    parser.add_argument(
        "--approved-apply-plan",
        type=Path,
        help="Saved skeinrank.agent_approved_apply_plan.v1 JSON input for snapshot evaluation.",
    )
    parser.add_argument(
        "--before-snapshot",
        type=Path,
        help="Optional before snapshot artifact JSON for 41H snapshot evaluation.",
    )
    parser.add_argument(
        "--after-snapshot",
        type=Path,
        help="Optional after snapshot artifact JSON for 41H snapshot evaluation.",
    )
    parser.add_argument(
        "--max-apply-items",
        type=int,
        help="Override approved_apply.max_items for this run.",
    )

    parser.add_argument(
        "--print-scheduled-runner-plan",
        action="store_true",
        help="Print the 41I scheduled/worker-mode agent cycle plan.",
    )
    parser.add_argument(
        "--run-agent-cycle",
        action="store_true",
        help="Run a safe scheduled agent cycle and print the cycle report.",
    )
    parser.add_argument(
        "--write-agent-cycle-report",
        type=Path,
        help="Run a scheduled agent cycle and write the final cycle report to this JSON path.",
    )
    parser.add_argument(
        "--agent-cycle-artifacts-dir",
        type=Path,
        help="Override scheduled_runner.artifacts_dir for this run.",
    )
    parser.add_argument(
        "--agent-cycle-live-llm",
        action="store_true",
        help="Allow the scheduled cycle to call OpenRouter for LLM review.",
    )
    parser.add_argument(
        "--agent-cycle-validate-proposals",
        action="store_true",
        help="Allow the scheduled cycle to validate ready proposal payloads through SkeinRank.",
    )
    parser.add_argument(
        "--agent-cycle-submit-proposals",
        action="store_true",
        help=(
            "Allow the scheduled cycle to submit validated proposals. Requires "
            "safe proposal/security config and never publishes snapshots."
        ),
    )
    parser.add_argument(
        "--agent-cycle-append-tracking-ledger",
        action="store_true",
        help="Append document visit entries during the scheduled cycle.",
    )
    parser.add_argument(
        "--agent-cycle-fail-on-needs-review",
        action="store_true",
        help="Return the configured needs-review exit code when the cycle needs human review.",
    )

    parser.add_argument(
        "--print-integration-smoke-plan",
        action="store_true",
        help="Print the 42A full agent integration smoke-test plan.",
    )
    parser.add_argument(
        "--run-integration-smoke-test",
        action="store_true",
        help="Run a network-free full agent integration smoke test and print JSON.",
    )
    parser.add_argument(
        "--write-integration-smoke-report",
        type=Path,
        help="Run the 42A smoke test and write the report to this JSON path.",
    )
    parser.add_argument(
        "--integration-smoke-artifacts-dir",
        type=Path,
        help="Override integration_smoke.artifacts_dir for this run.",
    )

    parser.add_argument(
        "--print-real-elasticsearch-validation-plan",
        action="store_true",
        help="Print the 42B real Elasticsearch validation scenario plan.",
    )
    parser.add_argument(
        "--write-real-elasticsearch-validation-fixtures",
        action="store_true",
        help="Write 42B sample ES docs, failed queries, outcomes, mapping, and bulk NDJSON.",
    )
    parser.add_argument(
        "--index-real-elasticsearch-validation-docs",
        action="store_true",
        help="Explicitly index 42B sample docs into the configured Elasticsearch index.",
    )
    parser.add_argument(
        "--run-real-elasticsearch-validation",
        action="store_true",
        help="Run the 42B read-only validation scenario against Elasticsearch.",
    )
    parser.add_argument(
        "--write-real-elasticsearch-validation-report",
        type=Path,
        help="Run 42B and write the validation scenario report to this JSON path.",
    )
    parser.add_argument(
        "--real-es-validation-artifacts-dir",
        type=Path,
        help="Override real_elasticsearch_validation.artifacts_dir for this run.",
    )
    parser.add_argument(
        "--real-es-validation-reset-index",
        action="store_true",
        help="Allow the 42B indexing command to delete/recreate the validation index.",
    )

    parser.add_argument(
        "--print-artifacts-standard-plan",
        action="store_true",
        help="Print the 42C reports/artifacts standard plan.",
    )
    parser.add_argument(
        "--write-artifacts-manifest",
        type=Path,
        help=(
            "Write or repair a 42C manifest for an existing run folder. The path "
            "is the output manifest path; use --artifacts-run-id to select the run."
        ),
    )
    parser.add_argument(
        "--artifacts-root-dir",
        type=Path,
        help="Override artifact_standard.root_dir for 42C artifact commands.",
    )
    parser.add_argument(
        "--artifacts-run-id",
        help="Run id used by 42C manifest repair/backfill commands.",
    )

    parser.add_argument(
        "--print-new-alias-smoke-plan",
        action="store_true",
        help="Preview the 41D controlled new-alias smoke test without API calls.",
    )
    parser.add_argument(
        "--write-new-alias-smoke-llm-report",
        type=Path,
        help="Write a proposal-ready smoke LLM report for the configured new alias.",
    )
    parser.add_argument(
        "--run-new-alias-smoke-test",
        action="store_true",
        help="Validate the configured new-alias smoke payload through SkeinRank.",
    )
    parser.add_argument(
        "--submit-new-alias-smoke-test",
        action="store_true",
        help=(
            "Explicitly create a pending proposal for the configured new alias "
            "and verify idempotent retry. Does not publish snapshots or mutate runtime."
        ),
    )
    parser.add_argument(
        "--write-new-alias-smoke-report",
        type=Path,
        help="Write the 41D new-alias smoke test report to this JSON path.",
    )
    return parser.parse_args(argv)


def _llm_review_config_from_args(
    config: AgentRunnerConfig, args: argparse.Namespace
) -> LlmReviewConfig:
    if args.max_candidates is None:
        return config.llm_review
    return LlmReviewConfig(
        max_candidates=args.max_candidates,
        min_confidence_to_prepare_proposal=(
            config.llm_review.min_confidence_to_prepare_proposal
        ),
        temperature=config.llm_review.temperature,
        max_tokens=config.llm_review.max_tokens,
        include_tools=config.llm_review.include_tools,
        response_format_json=config.llm_review.response_format_json,
        submit_proposals=config.llm_review.submit_proposals,
    )


def _budget_cache_config_from_args(
    config: AgentRunnerConfig, args: argparse.Namespace
) -> AgentBudgetCacheConfig:
    cache_enabled = False if args.no_llm_cache else None
    return config.budget_cache.with_overrides(
        max_llm_calls_per_run=args.max_llm_calls,
        max_cost_usd_per_run=args.max_run_cost_usd,
        cache_enabled=cache_enabled,
        force_refresh=True if args.force_refresh_cache else None,
    )


def build_security_report_for_config(config: AgentRunnerConfig) -> JsonDict:
    """Build the sanitized 40L security profile report for CLI/tests."""

    return build_security_profile_report(
        security_config=config.security_profile,
        skeinrank_api_url=config.skeinrank_api_url,
        skeinrank_role=config.skeinrank_role,
        api_token_env=config.api_token_env,
        openrouter_api_key_env=config.openrouter_api_key_env,
        proposal_source_name=config.proposal_source_name,
        dry_run=config.dry_run,
        llm_submit_proposals=config.llm_review.submit_proposals,
    )


def _load_evaluation_outcomes_for_args(
    config: AgentRunnerConfig, args: argparse.Namespace
) -> list[JsonDict]:
    path = args.evaluation_outcomes or config.evaluation_outcomes_path
    if path is None:
        return []
    return load_evaluation_outcomes(path)


def build_deployment_recipe_for_config(config: AgentRunnerConfig) -> JsonDict:
    """Build the offline 40O deployment recipe for the current config."""

    return build_agent_deployment_recipe(
        config.deployment,
        skeinrank_api_url=config.skeinrank_api_url,
        openrouter_model=config.openrouter_model,
        proposal_submission_enabled=config.llm_review.submit_proposals,
        runtime_mutation_enabled=config.security_profile.allow_runtime_mutation,
        required_role=config.security_profile.required_role,
        cache_enabled=config.budget_cache.cache_enabled,
        max_llm_calls_per_run=config.budget_cache.max_llm_calls_per_run,
        max_cost_usd_per_run=config.budget_cache.max_cost_usd_per_run,
    )


def _load_llm_review_report_for_proposals(args: argparse.Namespace) -> JsonDict:
    if args.llm_review_report is None:
        raise RuntimeError(
            "--llm-review-report is required for proposal validation/submission."
        )
    return load_json_report(args.llm_review_report)


def build_proposal_submission_plan_for_args(
    config: AgentRunnerConfig, args: argparse.Namespace
) -> JsonDict:
    """Build the offline 41B proposal submission plan for CLI/tests."""

    return build_proposal_submission_plan(
        _load_llm_review_report_for_proposals(args),
        submission_config=config.proposal_submission,
        submit=bool(args.submit_ready_proposals),
    )


def run_proposal_submission_for_args(
    config: AgentRunnerConfig, args: argparse.Namespace
) -> JsonDict:
    """Validate and optionally submit proposals through the SkeinRank tools API."""

    return validate_and_optionally_submit_proposals(
        _load_llm_review_report_for_proposals(args),
        client=build_client(config),
        submission_config=config.proposal_submission,
        security_config=config.security_profile,
        submit=bool(args.submit_ready_proposals),
    )


def _proposal_inbox_config_from_args(
    config: AgentRunnerConfig, args: argparse.Namespace
) -> ProposalInboxConfig:
    """Apply CLI overrides to the 41G offline proposal inbox config."""

    return config.proposal_inbox.with_overrides(
        review_decisions_path=args.review_decisions,
        max_items=args.max_inbox_items,
    )


def build_proposal_inbox_for_args(
    config: AgentRunnerConfig, args: argparse.Namespace
) -> JsonDict:
    """Build the 41G offline proposal inbox from saved reports."""

    if args.llm_review_report is None and args.proposal_submission_report is None:
        raise RuntimeError(
            "--llm-review-report or --proposal-submission-report is required "
            "to build the proposal inbox."
        )
    inbox_config = _proposal_inbox_config_from_args(config, args)
    llm_report = (
        load_json_report(args.llm_review_report) if args.llm_review_report else None
    )
    submission_report = (
        load_json_report(args.proposal_submission_report)
        if args.proposal_submission_report
        else None
    )
    decisions = load_review_decisions(inbox_config.review_decisions_path)
    return build_proposal_inbox_report(
        llm_review_report=llm_report,
        proposal_submission_report=submission_report,
        review_decisions=decisions,
        config=inbox_config,
    )


def build_proposal_inbox_plan_for_config(config: AgentRunnerConfig) -> JsonDict:
    """Build the offline 41G proposal inbox plan for CLI/tests."""

    return config.proposal_inbox.to_plan()


def _approved_apply_config_from_args(
    config: AgentRunnerConfig, args: argparse.Namespace
) -> ApprovedApplyConfig:
    """Apply CLI overrides to the 41H approved apply config."""

    return config.approved_apply.with_overrides(
        before_snapshot_path=args.before_snapshot,
        after_snapshot_path=args.after_snapshot,
        max_items=args.max_apply_items,
    )


def build_approved_apply_plan_for_args(
    config: AgentRunnerConfig, args: argparse.Namespace
) -> JsonDict:
    """Build the 41H offline approved-proposal apply plan."""

    if args.proposal_inbox_report is None:
        raise RuntimeError(
            "--proposal-inbox-report is required for 41H apply planning."
        )
    inbox_report = load_apply_json_report(args.proposal_inbox_report)
    return build_approved_proposals_apply_plan(
        inbox_report or {}, config=_approved_apply_config_from_args(config, args)
    )


def build_approved_apply_config_plan_for_args(
    config: AgentRunnerConfig, args: argparse.Namespace
) -> JsonDict:
    """Build the 41H offline apply/evaluation config plan."""

    return _approved_apply_config_from_args(config, args).to_plan()


def build_snapshot_evaluation_for_args(
    config: AgentRunnerConfig, args: argparse.Namespace
) -> JsonDict:
    """Build the 41H offline snapshot evaluation report."""

    apply_plan = (
        load_apply_json_report(args.approved_apply_plan)
        if args.approved_apply_plan
        else None
    )
    before_path = args.before_snapshot or config.approved_apply.before_snapshot_path
    after_path = args.after_snapshot or config.approved_apply.after_snapshot_path
    before_snapshot = load_apply_json_report(before_path) if before_path else None
    after_snapshot = load_apply_json_report(after_path) if after_path else None
    return build_snapshot_evaluation_report(
        apply_plan=apply_plan,
        before_snapshot=before_snapshot,
        after_snapshot=after_snapshot,
    )


def build_new_alias_smoke_plan_for_config(
    config: AgentRunnerConfig, args: argparse.Namespace
) -> JsonDict:
    """Build the offline 41D new-alias smoke plan."""

    return build_new_alias_smoke_plan(
        config.new_alias_smoke,
        submit=bool(args.submit_new_alias_smoke_test),
    )


def run_new_alias_smoke_for_config(
    config: AgentRunnerConfig, args: argparse.Namespace
) -> JsonDict:
    """Run the 41D controlled new-alias validate/submit smoke test."""

    return run_new_alias_smoke_test(
        client=build_client(config),
        config=config.new_alias_smoke,
        submit=bool(args.submit_new_alias_smoke_test),
    )


def _artifact_standard_config_from_args(
    config: AgentRunnerConfig, args: argparse.Namespace
) -> ArtifactStandardConfig:
    """Apply CLI overrides to the 42C report/artifact standard config."""

    return config.artifact_standard.with_overrides(root_dir=args.artifacts_root_dir)


def build_artifacts_standard_plan_for_args(
    config: AgentRunnerConfig, args: argparse.Namespace
) -> JsonDict:
    """Build the network-free 42C artifact standard plan."""

    return _artifact_standard_config_from_args(config, args).to_plan()


def write_artifacts_manifest_for_args(
    config: AgentRunnerConfig, args: argparse.Namespace
) -> JsonDict:
    """Write or repair a manifest for an existing standardized run folder."""

    artifact_config = _artifact_standard_config_from_args(config, args)
    run_id = args.artifacts_run_id
    if not run_id:
        if args.write_artifacts_manifest is None:
            raise ValueError("--artifacts-run-id is required for manifest repair")
        run_id = args.write_artifacts_manifest.parent.name
    artifacts = discover_artifact_files(artifact_config, run_id)
    manifest = write_artifact_manifest(
        config=artifact_config,
        run_id=run_id,
        artifacts=artifacts,
        cycle_report=None,
        status="manifest_repaired",
    )
    if args.write_artifacts_manifest is not None:
        args.write_artifacts_manifest.parent.mkdir(parents=True, exist_ok=True)
        args.write_artifacts_manifest.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return manifest


def _scheduled_runner_config_from_args(
    config: AgentRunnerConfig, args: argparse.Namespace
) -> ScheduledRunnerConfig:
    """Apply CLI overrides to the 41I scheduled/worker-mode config."""

    return config.scheduled_runner.with_overrides(
        artifacts_dir=args.agent_cycle_artifacts_dir,
        live_llm_review_enabled=True if args.agent_cycle_live_llm else None,
        validate_proposals_enabled=(
            True if args.agent_cycle_validate_proposals else None
        ),
        submit_proposals_enabled=True if args.agent_cycle_submit_proposals else None,
        append_tracking_ledger=(
            True if args.agent_cycle_append_tracking_ledger else None
        ),
        fail_on_needs_review=(True if args.agent_cycle_fail_on_needs_review else None),
    )


def build_scheduled_runner_plan_for_args(
    config: AgentRunnerConfig, args: argparse.Namespace
) -> JsonDict:
    """Build a network-free 41I scheduled/worker-mode plan."""

    return _scheduled_runner_config_from_args(config, args).to_plan()


def run_scheduled_agent_cycle_for_config(
    config: AgentRunnerConfig,
    failed_queries: list[JsonDict],
    args: argparse.Namespace,
) -> tuple[JsonDict, int]:
    """Run one safe scheduled agent cycle and return report + exit code."""

    scheduled_config = _scheduled_runner_config_from_args(config, args)
    run_id = make_scheduled_run_id(cycle_name=scheduled_config.cycle_name)
    artifacts: list[JsonDict] = []
    steps: list[JsonDict] = []
    reports: dict[str, JsonDict | None] = {}

    def store(name: str, report: JsonDict | None) -> None:
        reports[name] = report
        if report is None:
            return
        if scheduled_config.write_artifacts:
            path = write_cycle_artifact(
                artifacts_dir=scheduled_config.artifacts_dir,
                run_id=run_id,
                name=name,
                payload=report,
            )
            run_dir = scheduled_config.artifacts_dir / run_id
            try:
                relative_path = str(path.relative_to(run_dir))
            except ValueError:
                relative_path = str(path)
            artifacts.append(
                {
                    "name": name,
                    "path": str(path),
                    "relative_path": relative_path,
                    "schema_version": report.get("schema_version"),
                    "size_bytes": path.stat().st_size if path.exists() else None,
                }
            )

    evidence_records = load_jsonl_records(
        config.evidence_records_path, limit=config.evidence_sampler.max_records
    )
    demo_report = build_alias_scout_demo_report(
        failed_queries,
        evidence_records,
        candidate_config=config.candidate_discovery,
        evidence_config=config.evidence_sampler,
        demo_config=config.demo_report,
        canonical_hints_config=config.canonical_hints,
        binding_id=config.default_binding_id,
        profile_name=config.default_profile_name,
        proposal_source_name=config.proposal_source_name,
        openrouter_model=args.model or config.openrouter_model,
    )
    store("demo_report", demo_report)
    steps.append(
        {
            "name": "demo_report",
            "status": "completed",
            "network_calls": False,
            "candidates_in_review_queue": demo_report.get("candidate_summary", {}).get(
                "candidates_in_review_queue"
            ),
        }
    )

    tracking_report = build_agent_tracking_report_for_config(
        config,
        failed_queries,
        args,
        append_ledger=scheduled_config.append_tracking_ledger,
    )
    store("tracking_report", tracking_report)
    steps.append(
        {
            "name": "tracking_report",
            "status": "completed",
            "network_calls": False,
            "ledger_appended": scheduled_config.append_tracking_ledger,
        }
    )

    llm_report: JsonDict | None = None
    if scheduled_config.live_llm_review_enabled:
        llm_config = _llm_review_config_from_args(config, args)
        budget_config = _budget_cache_config_from_args(config, args)
        assert_security_allows_llm_review(
            security_config=config.security_profile,
            skeinrank_role=config.skeinrank_role,
            api_token_env=config.api_token_env,
            llm_submit_proposals=llm_config.submit_proposals,
        )
        llm_report = run_openrouter_llm_review_workflow(
            failed_queries,
            evidence_records,
            openrouter_client=build_openrouter_client(config),
            candidate_config=config.candidate_discovery,
            evidence_config=config.evidence_sampler,
            demo_config=config.demo_report,
            canonical_hints_config=config.canonical_hints,
            llm_config=llm_config,
            budget_cache_config=budget_config,
            binding_id=config.default_binding_id,
            profile_name=config.default_profile_name,
            proposal_source_name=config.proposal_source_name,
            openrouter_model=args.model or config.openrouter_model,
            tools=get_openrouter_tool_schemas(),
        )
        store("llm_review_report", llm_report)
        steps.append(
            {
                "name": "llm_review",
                "status": "completed",
                "network_calls": True,
                "openrouter_calls": True,
                "summary": llm_report.get("llm_review_summary"),
            }
        )
    else:
        store("llm_review_report", None)
        steps.append(
            {
                "name": "llm_review",
                "status": "skipped",
                "reason": "agent_cycle_live_llm_not_enabled",
                "network_calls": False,
            }
        )

    submission_report: JsonDict | None = None
    if scheduled_config.validate_proposals_enabled:
        if llm_report is None:
            steps.append(
                {
                    "name": "proposal_validation",
                    "status": "skipped",
                    "reason": "llm_review_report_not_available",
                    "network_calls": False,
                }
            )
        else:
            submission_report = validate_and_optionally_submit_proposals(
                llm_report,
                client=build_client(config),
                submission_config=config.proposal_submission,
                security_config=config.security_profile,
                submit=scheduled_config.submit_proposals_enabled,
            )
            store("proposal_submission_report", submission_report)
            summary = submission_report.get("summary", {})
            needs_review = bool(summary.get("manual_review_required"))
            steps.append(
                {
                    "name": "proposal_validation",
                    "status": "needs_review" if needs_review else "completed",
                    "needs_review": needs_review,
                    "network_calls": True,
                    "skeinrank_api_calls": True,
                    "summary": summary,
                }
            )
    else:
        store("proposal_submission_report", None)
        steps.append(
            {
                "name": "proposal_validation",
                "status": "skipped",
                "reason": "agent_cycle_validate_proposals_not_enabled",
                "network_calls": False,
            }
        )

    inbox_report: JsonDict | None = None
    if scheduled_config.build_inbox_enabled and (llm_report or submission_report):
        decisions = load_review_decisions(config.proposal_inbox.review_decisions_path)
        inbox_report = build_proposal_inbox_report(
            llm_review_report=llm_report,
            proposal_submission_report=submission_report,
            review_decisions=decisions,
            config=config.proposal_inbox,
        )
        store("proposal_inbox_report", inbox_report)
        summary = inbox_report.get("summary", {})
        needs_review = bool(summary.get("pending_review") or summary.get("deferred"))
        steps.append(
            {
                "name": "proposal_inbox",
                "status": "needs_review" if needs_review else "completed",
                "needs_review": needs_review,
                "network_calls": False,
                "summary": summary,
            }
        )
    else:
        store("proposal_inbox_report", None)
        steps.append(
            {
                "name": "proposal_inbox",
                "status": "skipped",
                "reason": "no_llm_or_submission_report_available",
                "network_calls": False,
            }
        )

    apply_plan: JsonDict | None = None
    if scheduled_config.build_apply_plan_enabled and inbox_report is not None:
        apply_plan = build_approved_proposals_apply_plan(
            inbox_report, config=config.approved_apply
        )
        store("approved_apply_plan", apply_plan)
        steps.append(
            {
                "name": "approved_apply_plan",
                "status": "completed",
                "network_calls": False,
                "summary": apply_plan.get("summary"),
            }
        )
    else:
        store("approved_apply_plan", None)
        steps.append(
            {
                "name": "approved_apply_plan",
                "status": "skipped",
                "reason": "proposal_inbox_not_available",
                "network_calls": False,
            }
        )

    snapshot_eval_report: JsonDict | None = None
    if scheduled_config.run_snapshot_evaluation_enabled:
        snapshot_eval_report = build_snapshot_evaluation_report(apply_plan=apply_plan)
        store("snapshot_evaluation_report", snapshot_eval_report)
        steps.append(
            {
                "name": "snapshot_evaluation",
                "status": "completed",
                "network_calls": False,
                "snapshot_eval_enabled": snapshot_eval_report.get(
                    "snapshot_eval_enabled"
                ),
            }
        )
    else:
        store("snapshot_evaluation_report", None)
        steps.append(
            {
                "name": "snapshot_evaluation",
                "status": "skipped",
                "reason": "scheduled_snapshot_eval_disabled",
                "network_calls": False,
            }
        )

    evaluation_report = build_agent_evaluation_report(
        demo_report=demo_report,
        llm_review_report=llm_report,
        outcome_records=_load_evaluation_outcomes_for_args(config, args),
        evaluation_config=config.evaluation,
    )
    store("evaluation_report", evaluation_report)
    gate_status = str(evaluation_report.get("quality_gate", {}).get("status") or "")
    steps.append(
        {
            "name": "evaluation_report",
            "status": "needs_review" if gate_status == "needs_review" else "completed",
            "needs_review": gate_status == "needs_review",
            "network_calls": False,
            "quality_gate": evaluation_report.get("quality_gate"),
        }
    )

    final_report = build_scheduled_cycle_report(
        config=scheduled_config,
        run_id=run_id,
        artifacts=artifacts,
        steps=steps,
        reports=reports,
    )
    store("cycle_report", final_report)
    manifest = write_cycle_manifest(
        artifacts_dir=scheduled_config.artifacts_dir,
        run_id=run_id,
        artifacts=artifacts,
        cycle_report=final_report,
    )
    final_report["artifact_manifest"] = {
        "path": str(scheduled_config.artifacts_dir / run_id / "manifest.json"),
        "schema_version": manifest.get("schema_version"),
        "artifact_count": manifest.get("artifact_count"),
    }
    return final_report, int(final_report.get("recommended_exit_code", 0))


def _integration_smoke_config_from_args(
    config: AgentRunnerConfig, args: argparse.Namespace
) -> FullIntegrationSmokeConfig:
    """Apply CLI overrides to the 42A full integration smoke config."""

    return config.integration_smoke.with_overrides(
        artifacts_dir=args.integration_smoke_artifacts_dir,
        max_candidates=args.max_candidates,
    )


def build_integration_smoke_plan_for_args(
    config: AgentRunnerConfig, args: argparse.Namespace
) -> JsonDict:
    """Build the network-free 42A smoke-test plan."""

    return _integration_smoke_config_from_args(config, args).to_plan()


def run_integration_smoke_for_config(
    config: AgentRunnerConfig,
    failed_queries: list[JsonDict],
    args: argparse.Namespace,
) -> JsonDict:
    """Run the network-free 42A full agent integration smoke test."""

    evidence_records = load_jsonl_records(
        config.evidence_records_path, limit=config.evidence_sampler.max_records
    )
    return build_full_integration_smoke_report(
        failed_queries=failed_queries,
        evidence_records=evidence_records,
        smoke_config=_integration_smoke_config_from_args(config, args),
        candidate_config=config.candidate_discovery,
        evidence_config=config.evidence_sampler,
        demo_config=config.demo_report,
        canonical_hints_config=config.canonical_hints,
        proposal_submission_config=config.proposal_submission,
        proposal_inbox_config=config.proposal_inbox,
        approved_apply_config=config.approved_apply,
        evaluation_config=config.evaluation,
        scheduled_config=config.scheduled_runner,
        binding_id=config.default_binding_id,
        profile_name=config.default_profile_name,
        proposal_source_name=config.proposal_source_name,
        openrouter_model=args.model or config.openrouter_model,
    )


def _real_elasticsearch_validation_config_from_args(
    config: AgentRunnerConfig, args: argparse.Namespace
) -> RealElasticsearchValidationConfig:
    """Apply CLI overrides to the 42B real Elasticsearch validation config."""

    return config.real_elasticsearch_validation.with_overrides(
        artifacts_dir=args.real_es_validation_artifacts_dir,
        max_candidates=args.max_candidates,
        reset_index=True if args.real_es_validation_reset_index else None,
    )


def build_real_elasticsearch_validation_plan_for_args(
    config: AgentRunnerConfig, args: argparse.Namespace
) -> JsonDict:
    """Build the network-free 42B real Elasticsearch validation scenario plan."""

    return _real_elasticsearch_validation_config_from_args(config, args).to_plan(
        source_config=_elasticsearch_source_config_from_args(config, args)
    )


def write_real_elasticsearch_validation_fixtures_for_args(
    config: AgentRunnerConfig, args: argparse.Namespace
) -> JsonDict:
    """Write 42B real Elasticsearch validation fixture files."""

    return write_real_elasticsearch_validation_fixtures(
        _real_elasticsearch_validation_config_from_args(config, args),
        source_config=_elasticsearch_source_config_from_args(config, args),
    )


def index_real_elasticsearch_validation_docs_for_args(
    config: AgentRunnerConfig, args: argparse.Namespace
) -> JsonDict:
    """Explicitly index 42B validation fixture docs into Elasticsearch."""

    source_config = _elasticsearch_source_config_from_args(config, args)
    return index_real_elasticsearch_validation_docs(
        config=_real_elasticsearch_validation_config_from_args(config, args),
        source_config=source_config,
        client=ElasticsearchSourceClient(source_config),
    )


def run_real_elasticsearch_validation_for_args(
    config: AgentRunnerConfig, args: argparse.Namespace
) -> JsonDict:
    """Run the 42B read-only real Elasticsearch validation scenario."""

    source_config = _elasticsearch_source_config_from_args(config, args)
    return run_real_elasticsearch_validation_scenario(
        config=_real_elasticsearch_validation_config_from_args(config, args),
        source_config=source_config,
        evidence_config=config.evidence_sampler,
        candidate_config=config.candidate_discovery,
        client=ElasticsearchSourceClient(source_config),
        binding_id=config.default_binding_id,
        profile_name=config.default_profile_name,
    )


def _elasticsearch_source_config_from_args(
    config: AgentRunnerConfig, args: argparse.Namespace
) -> ElasticsearchSourceConfig:
    """Apply CLI overrides to the optional 41E Elasticsearch connector config."""

    return config.elasticsearch_source.with_overrides(
        url=args.elasticsearch_url,
        index=args.elasticsearch_index,
        text_fields=args.elasticsearch_text_field,
        max_docs_per_candidate=args.elasticsearch_max_docs,
        api_key_env=args.elasticsearch_api_key_env,
    )


def build_elasticsearch_evidence_plan_for_config(
    config: AgentRunnerConfig, args: argparse.Namespace
) -> JsonDict:
    """Build a network-free Elasticsearch evidence connector plan."""

    return _elasticsearch_source_config_from_args(config, args).to_plan()


def build_elasticsearch_evidence_report_for_config(
    config: AgentRunnerConfig,
    failed_queries: list[JsonDict],
    args: argparse.Namespace,
) -> JsonDict:
    """Fetch Elasticsearch evidence for discovered candidates and sample windows."""

    source_config = _elasticsearch_source_config_from_args(config, args)
    candidates = discover_alias_candidates(
        failed_queries, config=config.candidate_discovery
    )
    scoped_candidates = candidates[: config.demo_report.max_candidates_for_review]
    client = ElasticsearchSourceClient(source_config)
    return build_elasticsearch_evidence_report(
        scoped_candidates,
        client=client,
        source_config=source_config,
        evidence_config=config.evidence_sampler,
        binding_id=config.default_binding_id,
        profile_name=config.default_profile_name,
    )


def write_elasticsearch_evidence_records_for_config(
    config: AgentRunnerConfig,
    failed_queries: list[JsonDict],
    args: argparse.Namespace,
) -> JsonDict:
    """Fetch Elasticsearch hits and write normalized records as JSONL."""

    if args.write_elasticsearch_evidence_records is None:
        raise RuntimeError("--write-elasticsearch-evidence-records path is required")
    source_config = _elasticsearch_source_config_from_args(config, args)
    candidates = discover_alias_candidates(
        failed_queries, config=config.candidate_discovery
    )
    scoped_candidates = candidates[: config.demo_report.max_candidates_for_review]
    records = collect_elasticsearch_evidence_records(
        scoped_candidates,
        client=ElasticsearchSourceClient(source_config),
        source_config=source_config,
    )
    args.write_elasticsearch_evidence_records.parent.mkdir(parents=True, exist_ok=True)
    with args.write_elasticsearch_evidence_records.open("w", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record, sort_keys=True) + "\n")
    return {
        "schema_version": "skeinrank.agent_elasticsearch_evidence_export.v1",
        "runner": "openrouter_alias_scout",
        "elasticsearch_calls": True,
        "openrouter_calls": False,
        "skeinrank_api_calls": False,
        "records_written": len(records),
        "path": str(args.write_elasticsearch_evidence_records),
        "index": source_config.index,
        "text_fields": list(source_config.text_fields),
    }


def _agent_tracking_config_from_args(
    config: AgentRunnerConfig, args: argparse.Namespace
) -> AgentRunTrackingConfig:
    """Apply CLI overrides to the 41F local tracking config."""

    return config.agent_tracking.with_overrides(ledger_path=args.agent_tracking_ledger)


def build_agent_tracking_report_for_config(
    config: AgentRunnerConfig,
    failed_queries: list[JsonDict],
    args: argparse.Namespace,
    *,
    append_ledger: bool = False,
) -> JsonDict:
    """Build the 41F local agent run/document tracking report."""

    _ = failed_queries
    tracking_config = _agent_tracking_config_from_args(config, args)
    evidence_records = load_jsonl_records(
        config.evidence_records_path, limit=config.evidence_sampler.max_records
    )
    return build_agent_run_tracking_report(
        evidence_records,
        config=tracking_config,
        binding_id=config.default_binding_id,
        profile_name=config.default_profile_name,
        openrouter_model=args.model or config.openrouter_model,
        source_name="local_evidence_records",
        append_ledger=append_ledger,
    )


def build_evaluation_report_for_config(
    config: AgentRunnerConfig,
    failed_queries: list[JsonDict],
    args: argparse.Namespace,
) -> JsonDict:
    """Build the offline 40N evaluation report for CLI/tests."""

    evidence_records = load_jsonl_records(
        config.evidence_records_path, limit=config.evidence_sampler.max_records
    )
    demo_report = build_alias_scout_demo_report(
        failed_queries,
        evidence_records,
        candidate_config=config.candidate_discovery,
        evidence_config=config.evidence_sampler,
        demo_config=config.demo_report,
        canonical_hints_config=config.canonical_hints,
        binding_id=config.default_binding_id,
        profile_name=config.default_profile_name,
        proposal_source_name=config.proposal_source_name,
        openrouter_model=args.model or config.openrouter_model,
    )
    llm_report = (
        load_json_report(args.llm_review_report) if args.llm_review_report else None
    )
    outcome_records = _load_evaluation_outcomes_for_args(config, args)
    return build_agent_evaluation_report(
        demo_report=demo_report,
        llm_review_report=llm_report,
        outcome_records=outcome_records,
        evaluation_config=config.evaluation,
    )


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(list(sys.argv[1:] if argv is None else argv))
    config = AgentRunnerConfig.from_file(args.config)

    if args.print_elasticsearch_evidence_plan:
        report = build_elasticsearch_evidence_plan_for_config(config, args)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    if args.print_new_alias_smoke_plan:
        report = build_new_alias_smoke_plan_for_config(config, args)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    if args.write_new_alias_smoke_llm_report:
        report = build_new_alias_smoke_llm_report(config.new_alias_smoke)
        args.write_new_alias_smoke_llm_report.parent.mkdir(parents=True, exist_ok=True)
        args.write_new_alias_smoke_llm_report.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return 0

    if (
        args.run_new_alias_smoke_test
        or args.submit_new_alias_smoke_test
        or args.write_new_alias_smoke_report
    ):
        report = run_new_alias_smoke_for_config(config, args)
        if args.write_new_alias_smoke_report:
            args.write_new_alias_smoke_report.parent.mkdir(parents=True, exist_ok=True)
            args.write_new_alias_smoke_report.write_text(
                json.dumps(report, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        else:
            print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    if args.print_proposal_submission_plan:
        report = build_proposal_submission_plan_for_args(config, args)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    if args.validate_ready_proposals or args.submit_ready_proposals:
        report = run_proposal_submission_for_args(config, args)
        if args.write_proposal_submission_report:
            args.write_proposal_submission_report.parent.mkdir(
                parents=True, exist_ok=True
            )
            args.write_proposal_submission_report.write_text(
                json.dumps(report, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        else:
            print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    if args.print_proposal_inbox_plan:
        report = build_proposal_inbox_plan_for_config(config)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    if args.build_proposal_inbox or args.write_proposal_inbox:
        report = build_proposal_inbox_for_args(config, args)
        if args.write_proposal_inbox:
            args.write_proposal_inbox.parent.mkdir(parents=True, exist_ok=True)
            args.write_proposal_inbox.write_text(
                json.dumps(report, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        else:
            print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    if args.print_approved_apply_plan:
        report = build_approved_apply_config_plan_for_args(config, args)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    if args.build_approved_apply_plan or args.write_approved_apply_plan:
        report = build_approved_apply_plan_for_args(config, args)
        if args.write_approved_apply_plan:
            args.write_approved_apply_plan.parent.mkdir(parents=True, exist_ok=True)
            args.write_approved_apply_plan.write_text(
                json.dumps(report, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        else:
            print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    if args.run_snapshot_evaluation or args.write_snapshot_evaluation_report:
        report = build_snapshot_evaluation_for_args(config, args)
        if args.write_snapshot_evaluation_report:
            args.write_snapshot_evaluation_report.parent.mkdir(
                parents=True, exist_ok=True
            )
            args.write_snapshot_evaluation_report.write_text(
                json.dumps(report, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        else:
            print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    if args.print_deployment_recipe or args.write_deployment_recipe:
        report = build_deployment_recipe_for_config(config)
        if args.write_deployment_recipe:
            args.write_deployment_recipe.parent.mkdir(parents=True, exist_ok=True)
            args.write_deployment_recipe.write_text(
                json.dumps(report, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        else:
            print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    if args.print_scheduled_runner_plan:
        report = build_scheduled_runner_plan_for_args(config, args)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    if args.print_integration_smoke_plan:
        report = build_integration_smoke_plan_for_args(config, args)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    if args.print_real_elasticsearch_validation_plan:
        report = build_real_elasticsearch_validation_plan_for_args(config, args)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    if args.write_real_elasticsearch_validation_fixtures:
        report = write_real_elasticsearch_validation_fixtures_for_args(config, args)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    if args.index_real_elasticsearch_validation_docs:
        report = index_real_elasticsearch_validation_docs_for_args(config, args)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    if (
        args.run_real_elasticsearch_validation
        or args.write_real_elasticsearch_validation_report
    ):
        report = run_real_elasticsearch_validation_for_args(config, args)
        if args.write_real_elasticsearch_validation_report:
            args.write_real_elasticsearch_validation_report.parent.mkdir(
                parents=True, exist_ok=True
            )
            args.write_real_elasticsearch_validation_report.write_text(
                json.dumps(report, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        else:
            print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    if args.print_artifacts_standard_plan:
        report = build_artifacts_standard_plan_for_args(config, args)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    if args.write_artifacts_manifest:
        report = write_artifacts_manifest_for_args(config, args)
        if not args.write_artifacts_manifest:
            print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    if args.print_security_profile or args.check_security_profile:
        report = build_security_report_for_config(config)
        print(json.dumps(report, indent=2, sort_keys=True))
        if args.check_security_profile and report["status"] != "ok":
            return 2
        return 0

    if args.print_budget_cache_plan:
        budget_config = _budget_cache_config_from_args(config, args)
        print(
            json.dumps(build_budget_cache_plan(budget_config), indent=2, sort_keys=True)
        )
        return 0

    if args.clear_llm_cache:
        budget_config = _budget_cache_config_from_args(config, args)
        print(
            json.dumps(clear_llm_review_cache(budget_config), indent=2, sort_keys=True)
        )
        return 0

    failed_queries = load_failed_queries(
        config.failed_queries_path, limit=config.max_queries_per_run
    )

    if args.run_integration_smoke_test or args.write_integration_smoke_report:
        report = run_integration_smoke_for_config(config, failed_queries, args)
        if args.write_integration_smoke_report:
            args.write_integration_smoke_report.parent.mkdir(
                parents=True, exist_ok=True
            )
            args.write_integration_smoke_report.write_text(
                json.dumps(report, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        else:
            print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    if args.run_agent_cycle or args.write_agent_cycle_report:
        report, exit_code = run_scheduled_agent_cycle_for_config(
            config, failed_queries, args
        )
        if args.write_agent_cycle_report:
            args.write_agent_cycle_report.parent.mkdir(parents=True, exist_ok=True)
            args.write_agent_cycle_report.write_text(
                json.dumps(report, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        else:
            print(json.dumps(report, indent=2, sort_keys=True))
        return exit_code

    if args.print_agent_tracking_plan:
        print(
            json.dumps(
                _agent_tracking_config_from_args(config, args).to_plan(),
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    if args.write_agent_tracking_report or args.append_agent_tracking_ledger:
        report = build_agent_tracking_report_for_config(
            config,
            failed_queries,
            args,
            append_ledger=bool(args.append_agent_tracking_ledger),
        )
        if args.write_agent_tracking_report:
            args.write_agent_tracking_report.parent.mkdir(parents=True, exist_ok=True)
            args.write_agent_tracking_report.write_text(
                json.dumps(report, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        else:
            print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    if args.sample_evidence_from_elasticsearch:
        report = build_elasticsearch_evidence_report_for_config(
            config, failed_queries, args
        )
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    if args.write_elasticsearch_evidence_records:
        report = write_elasticsearch_evidence_records_for_config(
            config, failed_queries, args
        )
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    if args.run_evaluation_report or args.write_evaluation_report:
        report = build_evaluation_report_for_config(config, failed_queries, args)
        if args.write_evaluation_report:
            args.write_evaluation_report.parent.mkdir(parents=True, exist_ok=True)
            args.write_evaluation_report.write_text(
                json.dumps(report, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        else:
            print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    if args.print_tool_schemas:
        print(json.dumps(get_openrouter_tool_schemas(), indent=2, sort_keys=True))
        return 0

    if args.print_canonical_hints:
        print(
            json.dumps(
                build_canonical_hints_report(config.canonical_hints),
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    if args.print_system_prompt:
        print(SYSTEM_PROMPT)
        return 0

    if args.print_sample_review_prompt:
        sample_pack = build_sample_candidate_pack()
        print(build_alias_review_prompt(sample_pack))
        return 0

    if args.list_bindings:
        client = build_client(config)
        bindings = client.list_bindings(profile_name=config.default_profile_name)
        print(json.dumps(bindings, indent=2, sort_keys=True))
        return 0

    if args.discover_candidates:
        report = build_candidate_discovery_report(
            failed_queries,
            config=config.candidate_discovery,
            binding_id=config.default_binding_id,
            profile_name=config.default_profile_name,
        )
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    if args.print_sample_candidate_pack:
        candidates = discover_alias_candidates(
            failed_queries, config=config.candidate_discovery
        )
        if not candidates:
            raise RuntimeError("No candidates discovered from failed-query input.")
        pack = build_candidate_fact_pack(
            candidates[0],
            binding_id=config.default_binding_id,
            profile_name=config.default_profile_name,
        )
        pack = enrich_candidate_pack_with_canonical_hints(pack, config.canonical_hints)
        print(json.dumps(pack, indent=2, sort_keys=True))
        return 0

    if args.sample_evidence:
        candidates = discover_alias_candidates(
            failed_queries, config=config.candidate_discovery
        )
        evidence_records = load_jsonl_records(
            config.evidence_records_path, limit=config.evidence_sampler.max_records
        )
        report = build_evidence_sampling_report(
            candidates,
            evidence_records,
            config=config.evidence_sampler,
            binding_id=config.default_binding_id,
            profile_name=config.default_profile_name,
        )
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    if args.print_sample_evidence_pack:
        candidates = discover_alias_candidates(
            failed_queries, config=config.candidate_discovery
        )
        if not candidates:
            raise RuntimeError("No candidates discovered from failed-query input.")
        evidence_records = load_jsonl_records(
            config.evidence_records_path, limit=config.evidence_sampler.max_records
        )
        windows = sample_evidence_windows(
            candidates[0].surface, evidence_records, config=config.evidence_sampler
        )
        if not windows:
            raise RuntimeError("No evidence windows found for the top candidate.")
        pack = build_candidate_evidence_pack(
            candidates[0],
            windows,
            binding_id=config.default_binding_id,
            profile_name=config.default_profile_name,
        )
        pack = enrich_candidate_pack_with_canonical_hints(pack, config.canonical_hints)
        print(json.dumps(pack, indent=2, sort_keys=True))
        return 0

    if args.run_demo_report or args.write_demo_report:
        candidates_report_queries = failed_queries
        evidence_records = load_jsonl_records(
            config.evidence_records_path, limit=config.evidence_sampler.max_records
        )
        report = build_alias_scout_demo_report(
            candidates_report_queries,
            evidence_records,
            candidate_config=config.candidate_discovery,
            evidence_config=config.evidence_sampler,
            demo_config=config.demo_report,
            canonical_hints_config=config.canonical_hints,
            binding_id=config.default_binding_id,
            profile_name=config.default_profile_name,
            proposal_source_name=config.proposal_source_name,
            openrouter_model=config.openrouter_model,
        )
        if args.write_demo_report:
            args.write_demo_report.parent.mkdir(parents=True, exist_ok=True)
            args.write_demo_report.write_text(
                json.dumps(report, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        else:
            print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    if args.print_demo_review_prompt:
        evidence_records = load_jsonl_records(
            config.evidence_records_path, limit=config.evidence_sampler.max_records
        )
        print(
            build_demo_review_prompt(
                failed_queries,
                evidence_records,
                candidate_config=config.candidate_discovery,
                evidence_config=config.evidence_sampler,
                canonical_hints_config=config.canonical_hints,
                binding_id=config.default_binding_id,
                profile_name=config.default_profile_name,
            )
        )
        return 0

    if args.print_llm_review_plan:
        evidence_records = load_jsonl_records(
            config.evidence_records_path, limit=config.evidence_sampler.max_records
        )
        llm_config = _llm_review_config_from_args(config, args)
        budget_config = _budget_cache_config_from_args(config, args)
        plan = build_llm_review_plan(
            failed_queries,
            evidence_records,
            candidate_config=config.candidate_discovery,
            evidence_config=config.evidence_sampler,
            demo_config=config.demo_report,
            canonical_hints_config=config.canonical_hints,
            llm_config=llm_config,
            budget_cache_config=budget_config,
            binding_id=config.default_binding_id,
            profile_name=config.default_profile_name,
            proposal_source_name=config.proposal_source_name,
            openrouter_model=args.model or config.openrouter_model,
        )
        print(json.dumps(plan, indent=2, sort_keys=True))
        return 0

    if args.llm_review or args.write_llm_review_report:
        evidence_records = load_jsonl_records(
            config.evidence_records_path, limit=config.evidence_sampler.max_records
        )
        llm_config = _llm_review_config_from_args(config, args)
        budget_config = _budget_cache_config_from_args(config, args)
        assert_security_allows_llm_review(
            security_config=config.security_profile,
            skeinrank_role=config.skeinrank_role,
            api_token_env=config.api_token_env,
            llm_submit_proposals=llm_config.submit_proposals,
        )
        client = build_openrouter_client(config)
        report = run_openrouter_llm_review_workflow(
            failed_queries,
            evidence_records,
            openrouter_client=client,
            candidate_config=config.candidate_discovery,
            evidence_config=config.evidence_sampler,
            demo_config=config.demo_report,
            canonical_hints_config=config.canonical_hints,
            llm_config=llm_config,
            budget_cache_config=budget_config,
            binding_id=config.default_binding_id,
            profile_name=config.default_profile_name,
            proposal_source_name=config.proposal_source_name,
            openrouter_model=args.model or config.openrouter_model,
            tools=get_openrouter_tool_schemas(),
        )
        if args.write_llm_review_report:
            args.write_llm_review_report.parent.mkdir(parents=True, exist_ok=True)
            args.write_llm_review_report.write_text(
                json.dumps(report, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        else:
            print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    plan = build_run_plan(config, failed_queries)
    print(json.dumps(plan, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
