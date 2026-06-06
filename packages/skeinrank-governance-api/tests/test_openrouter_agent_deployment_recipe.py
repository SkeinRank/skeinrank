from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
AGENT_DIR = REPO_ROOT / "examples" / "agents" / "openrouter_alias_scout"
DEPLOY_DOCKER = REPO_ROOT / "deploy" / "docker"


def _load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_40o_files_exist_and_docs_are_linked() -> None:
    expected_paths = [
        AGENT_DIR / "deployment_recipe.py",
        DEPLOY_DOCKER / "openrouter-alias-scout.Dockerfile",
        DEPLOY_DOCKER / "openrouter-alias-scout.compose.yml",
        DEPLOY_DOCKER / "openrouter-alias-scout.env.example",
        REPO_ROOT / "docs" / "deployment" / "openrouter-alias-scout.md",
    ]
    for path in expected_paths:
        assert path.exists(), path

    for path in (
        REPO_ROOT / "packages" / "skeinrank-governance-api" / "README.md",
        REPO_ROOT / "docs" / "guides" / "openrouter-agent.md",
        REPO_ROOT / "docs" / "deployment" / "openrouter-alias-scout.md",
        AGENT_DIR / "README.md",
    ):
        content = path.read_text(encoding="utf-8")
        assert "--print-deployment-recipe" in content, path
        assert "skeinrank.agent_deployment_recipe.v1" in content, path

    root_docs = (REPO_ROOT / "docs" / "README.md").read_text(encoding="utf-8")
    assert "deployment/openrouter-alias-scout.md" in root_docs
    assert "guides/openrouter-agent.md" in root_docs


def test_deployment_recipe_cli_is_offline_and_safe_by_default() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(AGENT_DIR / "run_alias_scout.py"),
            "--config",
            str(AGENT_DIR / "agent_config.example.json"),
            "--print-deployment-recipe",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    report = json.loads(result.stdout)
    assert report["schema_version"] == "skeinrank.agent_deployment_recipe.v1"
    assert report["openrouter_calls"] is False
    assert report["skeinrank_api_calls"] is False
    assert report["proposal_submission_enabled"] is False
    assert report["runtime_mutation_enabled"] is False
    assert report["safety"]["default_command_is_offline"] is True
    assert report["safety"]["snapshot_publish"] is False
    assert report["deployment"]["service_name"] == "openrouter-alias-scout"
    assert "OPENROUTER_API_KEY" in report["environment"]["required_for_live_llm_review"]


def test_deployment_recipe_module_builds_custom_recipe() -> None:
    module = _load_module(
        "agent_deployment_recipe_40o", AGENT_DIR / "deployment_recipe.py"
    )
    cfg = module.AgentDeploymentConfig.from_mapping(
        {
            "service_name": "alias-scout-nightly",
            "default_mode": "demo_report",
            "schedule_mode": "cron",
            "schedule_cron": "0 3 * * *",
        },
        repo_root=REPO_ROOT,
    )
    report = module.build_agent_deployment_recipe(
        cfg,
        skeinrank_api_url="http://governance-api:8010",
        openrouter_model="openai/gpt-4o-mini",
        proposal_submission_enabled=False,
        runtime_mutation_enabled=False,
        max_llm_calls_per_run=2,
        max_cost_usd_per_run=0.005,
    )
    assert report["deployment"]["service_name"] == "alias-scout-nightly"
    assert report["deployment"]["schedule_mode"] == "cron"
    assert report["deployment"]["schedule_cron"] == "0 3 * * *"
    assert report["commands"]["safe_default"][-2:] == [
        "--write-demo-report",
        "examples/agents/openrouter_alias_scout/reports/demo-report.json",
    ]
    assert report["budget_cache"]["max_llm_calls_per_run"] == 2
    assert report["budget_cache"]["max_cost_usd_per_run"] == 0.005


def test_deployment_files_do_not_embed_real_secrets() -> None:
    env_example = (DEPLOY_DOCKER / "openrouter-alias-scout.env.example").read_text(
        encoding="utf-8"
    )
    assert "CHANGE_ME_OPENROUTER_KEY" in env_example
    assert "CHANGE_ME_AGENT_CONTRIBUTOR_TOKEN" in env_example
    assert "sk-or-v1" not in env_example

    compose = (DEPLOY_DOCKER / "openrouter-alias-scout.compose.yml").read_text(
        encoding="utf-8"
    )
    assert "--write-evaluation-report" in compose
    assert "--llm-review" not in compose
    assert "openrouter-alias-scout.env.example" in compose

    dockerfile = (DEPLOY_DOCKER / "openrouter-alias-scout.Dockerfile").read_text(
        encoding="utf-8"
    )
    assert "python:3.11-slim" in dockerfile
    assert "--run-evaluation-report" in dockerfile


def test_makefile_and_gitignore_include_deployment_recipe_targets() -> None:
    makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
    for target in (
        "agent-deploy-plan:",
        "agent-deploy-recipe:",
        "agent-compose-config:",
    ):
        assert target in makefile

    gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "examples/agents/openrouter_alias_scout/reports/" in gitignore
