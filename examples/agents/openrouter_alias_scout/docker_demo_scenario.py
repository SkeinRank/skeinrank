"""Docker Compose full demo scenario for the OpenRouter alias scout.

The scenario documents and checks a reproducible Docker Compose flow that starts
SkeinRank's dev stack, indexes the bundled real-ES validation fixtures, and runs
the agent in safe report-only mode. The helpers here are intentionally
network-free: they build plans and command manifests that external operators or
CI jobs can execute explicitly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

JsonDict = dict[str, Any]


@dataclass(frozen=True)
class DockerFullDemoConfig:
    """Config for the Docker Compose full demo scenario."""

    compose_file: str = "deploy/docker/openrouter-agent-full-demo.compose.yml"
    env_file: str = "deploy/docker/openrouter-agent-full-demo.env.example"
    script_path: str = "deploy/docker/scripts/openrouter-agent-full-demo.sh"
    guide_path: str = "docs/deployment/openrouter-agent-full-demo.md"
    artifacts_dir: str = "examples/agents/openrouter_alias_scout/reports/docker-demo"
    elasticsearch_index: str = "skeinrank_agent_demo"
    elasticsearch_url: str = "http://elasticsearch:9200"
    governance_api_url: str = "http://governance-api:8010"
    openrouter_model: str = "openai/gpt-4o-mini"
    max_llm_calls: int = 3
    max_run_cost_usd: float = 0.05
    live_llm_enabled_by_default: bool = False
    proposal_submission_enabled_by_default: bool = False
    runtime_mutation_enabled: bool = False
    snapshot_publish_enabled: bool = False

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any] | None) -> "DockerFullDemoConfig":
        """Create config from optional JSON config values."""

        raw = raw or {}
        return cls(
            compose_file=str(raw.get("compose_file", cls.compose_file)),
            env_file=str(raw.get("env_file", cls.env_file)),
            script_path=str(raw.get("script_path", cls.script_path)),
            guide_path=str(raw.get("guide_path", cls.guide_path)),
            artifacts_dir=str(raw.get("artifacts_dir", cls.artifacts_dir)),
            elasticsearch_index=str(
                raw.get("elasticsearch_index", cls.elasticsearch_index)
            ),
            elasticsearch_url=str(raw.get("elasticsearch_url", cls.elasticsearch_url)),
            governance_api_url=str(
                raw.get("governance_api_url", cls.governance_api_url)
            ),
            openrouter_model=str(raw.get("openrouter_model", cls.openrouter_model)),
            max_llm_calls=int(raw.get("max_llm_calls", cls.max_llm_calls)),
            max_run_cost_usd=float(raw.get("max_run_cost_usd", cls.max_run_cost_usd)),
            live_llm_enabled_by_default=bool(
                raw.get(
                    "live_llm_enabled_by_default",
                    cls.live_llm_enabled_by_default,
                )
            ),
            proposal_submission_enabled_by_default=bool(
                raw.get(
                    "proposal_submission_enabled_by_default",
                    cls.proposal_submission_enabled_by_default,
                )
            ),
            runtime_mutation_enabled=bool(
                raw.get("runtime_mutation_enabled", cls.runtime_mutation_enabled)
            ),
            snapshot_publish_enabled=bool(
                raw.get("snapshot_publish_enabled", cls.snapshot_publish_enabled)
            ),
        )

    def build_compose_command(self, action: str = "run") -> list[str]:
        """Build the host command for the demo script action."""

        return [self.script_path, action]


def build_docker_full_demo_plan(config: DockerFullDemoConfig) -> JsonDict:
    """Return a network-free plan for the full Docker Compose demo."""

    return {
        "schema_version": "skeinrank.agent_docker_compose_full_demo.v1",
        "runner": "openrouter_alias_scout",
        "workflow": "docker_compose_full_demo",
        "status": "planned",
        "compose": {
            "dev_stack_file": "docker-compose.dev.yml",
            "overlay_file": config.compose_file,
            "env_file": config.env_file,
            "script_path": config.script_path,
            "guide_path": config.guide_path,
            "service_name": "openrouter-agent-full-demo",
        },
        "artifacts": {
            "root_dir": config.artifacts_dir,
            "expected_files": [
                "real-es-fixtures.json",
                "real-es-indexing.json",
                "real-es-validation-report.json",
                "agent-cycle-report.json",
                "manifest.json",
            ],
        },
        "elasticsearch": {
            "url": config.elasticsearch_url,
            "index": config.elasticsearch_index,
            "fixtures_source": "examples/agents/openrouter_alias_scout/real_es_validation",
        },
        "governance_api": {
            "url": config.governance_api_url,
            "required_for_validation_submit": True,
            "proposal_submission_default": config.proposal_submission_enabled_by_default,
        },
        "openrouter": {
            "model": config.openrouter_model,
            "live_llm_default": config.live_llm_enabled_by_default,
            "max_llm_calls": config.max_llm_calls,
            "max_run_cost_usd": config.max_run_cost_usd,
        },
        "safety": {
            "network_calls_in_plan": False,
            "runtime_mutation_enabled": config.runtime_mutation_enabled,
            "snapshot_publish_enabled": config.snapshot_publish_enabled,
            "proposal_submission_enabled_by_default": (
                config.proposal_submission_enabled_by_default
            ),
            "live_openrouter_enabled_by_default": config.live_llm_enabled_by_default,
            "sample_index_isolated": True,
        },
        "commands": {
            "config": config.build_compose_command("config"),
            "run": config.build_compose_command("run"),
            "down": config.build_compose_command("down"),
        },
        "phases": [
            {
                "name": "start_dev_stack",
                "description": "Start PostgreSQL, Elasticsearch, RabbitMQ, migrations, and Governance API via docker-compose.dev.yml.",
            },
            {
                "name": "index_validation_docs",
                "description": "Index the bundled isolated real-ES validation documents.",
            },
            {
                "name": "run_readonly_es_validation",
                "description": "Verify Elasticsearch evidence coverage without OpenRouter or SkeinRank writes.",
            },
            {
                "name": "run_safe_agent_cycle",
                "description": "Run scheduled agent cycle in report-only mode and write standardized artifacts.",
            },
        ],
        "next_steps": [
            "Run the script from the repository root on a machine with Docker Compose v2.",
            "Inspect the generated reports under the configured artifacts directory.",
            "Enable live OpenRouter only by setting OPENROUTER_API_KEY and SKEINRANK_DOCKER_DEMO_LIVE_LLM=true.",
        ],
    }


__all__ = ["DockerFullDemoConfig", "build_docker_full_demo_plan"]
