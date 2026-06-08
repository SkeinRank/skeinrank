"""Deployment recipe helpers for the OpenRouter alias scout.

Deployment recipe generation is offline and dependency-light. It explains how to
run the reference agent as a Docker Compose service or scheduled job without
enabling proposal submission or runtime mutation by default.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

JsonDict = dict[str, Any]


@dataclass(frozen=True)
class AgentDeploymentConfig:
    """Static deployment recipe settings for the alias scout."""

    service_name: str = "openrouter-alias-scout"
    image_name: str = "skeinrank/openrouter-alias-scout:local"
    dockerfile_path: Path = Path("deploy/docker/openrouter-alias-scout.Dockerfile")
    compose_file_path: Path = Path("deploy/docker/openrouter-alias-scout.compose.yml")
    env_file_path: Path = Path("deploy/docker/openrouter-alias-scout.env.example")
    reports_dir: Path = Path("examples/agents/openrouter_alias_scout/reports")
    cache_dir: Path = Path("examples/agents/openrouter_alias_scout/.cache")
    default_mode: str = "evaluation_report"
    schedule_mode: str = "manual"
    schedule_cron: str = "0 2 * * *"

    @classmethod
    def from_mapping(
        cls, raw: Mapping[str, Any] | None, *, repo_root: Path | None = None
    ) -> "AgentDeploymentConfig":
        """Create config from optional JSON config values."""

        if not raw:
            raw = {}
        root = repo_root or Path.cwd()
        return cls(
            service_name=str(raw.get("service_name", cls.service_name)),
            image_name=str(raw.get("image_name", cls.image_name)),
            dockerfile_path=_resolve_repo_path(
                raw.get("dockerfile_path", str(cls.dockerfile_path)), root
            ),
            compose_file_path=_resolve_repo_path(
                raw.get("compose_file_path", str(cls.compose_file_path)), root
            ),
            env_file_path=_resolve_repo_path(
                raw.get("env_file_path", str(cls.env_file_path)), root
            ),
            reports_dir=_resolve_repo_path(
                raw.get("reports_dir", str(cls.reports_dir)), root
            ),
            cache_dir=_resolve_repo_path(
                raw.get("cache_dir", str(cls.cache_dir)), root
            ),
            default_mode=str(raw.get("default_mode", cls.default_mode)),
            schedule_mode=str(raw.get("schedule_mode", cls.schedule_mode)),
            schedule_cron=str(raw.get("schedule_cron", cls.schedule_cron)),
        )

    def to_report(self) -> JsonDict:
        """Return JSON-safe deployment metadata."""

        return {
            "service_name": self.service_name,
            "image_name": self.image_name,
            "dockerfile_path": str(self.dockerfile_path),
            "compose_file_path": str(self.compose_file_path),
            "env_file_path": str(self.env_file_path),
            "reports_dir": str(self.reports_dir),
            "cache_dir": str(self.cache_dir),
            "default_mode": self.default_mode,
            "schedule_mode": self.schedule_mode,
            "schedule_cron": self.schedule_cron,
        }


def build_agent_deployment_recipe(
    deployment_config: AgentDeploymentConfig | None = None,
    *,
    skeinrank_api_url: str = "http://127.0.0.1:8010",
    openrouter_model: str = "openai/gpt-4o-mini",
    proposal_submission_enabled: bool = False,
    runtime_mutation_enabled: bool = False,
    required_role: str = "contributor",
    cache_enabled: bool = True,
    max_llm_calls_per_run: int = 3,
    max_cost_usd_per_run: float = 0.01,
    workflow_nodes: Sequence[str] | None = None,
) -> JsonDict:
    """Build an offline deployment recipe report.

    The report is intentionally descriptive. It does not build images, start
    containers, contact OpenRouter, or call the SkeinRank API.
    """

    cfg = deployment_config or AgentDeploymentConfig()
    nodes = list(workflow_nodes or [])
    default_command = _default_command(cfg.default_mode)
    live_command = [
        "python",
        "examples/agents/openrouter_alias_scout/run_alias_scout.py",
        "--llm-review",
        "--model",
        openrouter_model,
        "--max-candidates",
        str(max_llm_calls_per_run),
    ]
    return {
        "schema_version": "skeinrank.agent_deployment_recipe.v1",
        "runner": "openrouter_alias_scout",
        "deployment_mode": "docker_compose_reference",
        "openrouter_calls": False,
        "skeinrank_api_calls": False,
        "proposal_submission_enabled": proposal_submission_enabled,
        "runtime_mutation_enabled": runtime_mutation_enabled,
        "langgraph_ready": True,
        "workflow_engine": "dependency_light_state_machine",
        "workflow_nodes": nodes,
        "deployment": cfg.to_report(),
        "commands": {
            "safe_default": default_command,
            "live_llm_review": live_command,
            "write_llm_report": [
                "python",
                "examples/agents/openrouter_alias_scout/run_alias_scout.py",
                "--write-llm-review-report",
                "examples/agents/openrouter_alias_scout/reports/llm-review-report.json",
                "--model",
                openrouter_model,
            ],
            "offline_evaluation": [
                "python",
                "examples/agents/openrouter_alias_scout/run_alias_scout.py",
                "--write-evaluation-report",
                "examples/agents/openrouter_alias_scout/reports/evaluation-report.json",
            ],
        },
        "environment": {
            "required_for_live_llm_review": ["OPENROUTER_API_KEY"],
            "required_for_future_submission": ["SKEINRANK_AGENT_API_TOKEN"],
            "recommended": {
                "SKEINRANK_AGENT_API_URL": skeinrank_api_url,
                "SKEINRANK_AGENT_ROLE": required_role,
                "OPENROUTER_MODEL": openrouter_model,
            },
            "secret_policy": "copy env example locally and never commit real keys",
        },
        "budget_cache": {
            "cache_enabled": cache_enabled,
            "max_llm_calls_per_run": max_llm_calls_per_run,
            "max_cost_usd_per_run": max_cost_usd_per_run,
        },
        "safety": {
            "default_command_is_offline": True,
            "agent_may_mutate_runtime": runtime_mutation_enabled,
            "direct_dictionary_write": False,
            "snapshot_publish": False,
            "direct_git_push": False,
            "proposal_submission_requires_later_policy": not proposal_submission_enabled,
        },
        "operator_steps": [
            "copy deploy/docker/openrouter-alias-scout.env.example to a local env file",
            "replace CHANGE_ME values outside Git",
            "run docker compose config to validate the service recipe",
            "run the safe offline evaluation command first",
            "enable live --llm-review only with a bounded OpenRouter key",
        ],
    }


def _default_command(mode: str) -> list[str]:
    if mode == "llm_review_report":
        return [
            "python",
            "examples/agents/openrouter_alias_scout/run_alias_scout.py",
            "--write-llm-review-report",
            "examples/agents/openrouter_alias_scout/reports/llm-review-report.json",
        ]
    if mode == "demo_report":
        return [
            "python",
            "examples/agents/openrouter_alias_scout/run_alias_scout.py",
            "--write-demo-report",
            "examples/agents/openrouter_alias_scout/reports/demo-report.json",
        ]
    return [
        "python",
        "examples/agents/openrouter_alias_scout/run_alias_scout.py",
        "--write-evaluation-report",
        "examples/agents/openrouter_alias_scout/reports/evaluation-report.json",
    ]


def _resolve_repo_path(value: Any, repo_root: Path) -> Path:
    path = Path(str(value))
    if path.is_absolute():
        return path
    return repo_root / path
