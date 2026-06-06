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


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def test_42d_files_exist_and_docs_are_linked() -> None:
    expected_paths = [
        AGENT_DIR / "docker_demo_scenario.py",
        DEPLOY_DOCKER / "openrouter-agent-full-demo.compose.yml",
        DEPLOY_DOCKER / "openrouter-agent-full-demo.env.example",
        DEPLOY_DOCKER / "scripts" / "openrouter-agent-full-demo.sh",
        REPO_ROOT / "docs" / "deployment" / "openrouter-agent-full-demo.md",
    ]
    for path in expected_paths:
        assert path.exists(), path

    for path in (
        REPO_ROOT / "docs" / "README.md",
        REPO_ROOT / "docs" / "guides" / "openrouter-agent.md",
        REPO_ROOT / "deploy" / "docker" / "README.md",
        REPO_ROOT / "packages" / "skeinrank-governance-api" / "README.md",
        AGENT_DIR / "README.md",
    ):
        content = path.read_text(encoding="utf-8")
        assert "openrouter-agent-full-demo" in content, path
        assert "openrouter-agent-full-demo" in content, path


def test_docker_demo_plan_cli_is_network_free_and_safe() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(AGENT_DIR / "run_alias_scout.py"),
            "--config",
            str(AGENT_DIR / "agent_config.example.json"),
            "--print-docker-demo-plan",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    report = json.loads(result.stdout)
    assert report["schema_version"] == "skeinrank.agent_docker_compose_full_demo.v1"
    assert report["patch"] == "42D"
    assert report["safety"]["network_calls_in_plan"] is False
    assert report["safety"]["runtime_mutation_enabled"] is False
    assert report["safety"]["snapshot_publish_enabled"] is False
    assert report["safety"]["proposal_submission_enabled_by_default"] is False
    assert report["safety"]["live_openrouter_enabled_by_default"] is False
    assert report["compose"]["service_name"] == "openrouter-agent-full-demo"
    assert (
        "deploy/docker/openrouter-agent-full-demo.compose.yml"
        == report["compose"]["overlay_file"]
    )
    assert report["elasticsearch"]["index"] == "skeinrank_agent_demo"


def test_docker_demo_module_builds_custom_plan() -> None:
    module = _load_module(
        "agent_docker_demo_42d", AGENT_DIR / "docker_demo_scenario.py"
    )
    cfg = module.DockerFullDemoConfig.from_mapping(
        {
            "artifacts_dir": "reports/custom-demo",
            "elasticsearch_index": "custom_index",
            "live_llm_enabled_by_default": False,
            "proposal_submission_enabled_by_default": False,
        }
    )
    report = module.build_docker_full_demo_plan(cfg)
    assert report["artifacts"]["root_dir"] == "reports/custom-demo"
    assert report["elasticsearch"]["index"] == "custom_index"
    assert report["commands"]["run"] == [
        "deploy/docker/scripts/openrouter-agent-full-demo.sh",
        "run",
    ]


def test_compose_overlay_runs_safe_one_shot_service() -> None:
    compose = _read("deploy/docker/openrouter-agent-full-demo.compose.yml")

    assert "openrouter-agent-full-demo:" in compose
    assert "docker-compose.dev.yml" in compose
    assert "openrouter-alias-scout.Dockerfile" in compose
    assert "condition: service_healthy" in compose
    assert "--write-real-elasticsearch-validation-fixtures" in compose
    assert "--index-real-elasticsearch-validation-docs" in compose
    assert "--write-real-elasticsearch-validation-report" in compose
    assert "--write-agent-cycle-report" in compose
    assert "--submit-ready-proposals" not in compose
    assert "--submit-proposals" not in compose
    assert "--run-snapshot-publish" not in compose


def test_env_example_and_script_do_not_embed_real_secrets() -> None:
    env_example = _read("deploy/docker/openrouter-agent-full-demo.env.example")
    assert "CHANGE_ME_OPENROUTER_KEY" in env_example
    assert "CHANGE_ME_AGENT_CONTRIBUTOR_TOKEN" in env_example
    assert "SKEINRANK_DOCKER_DEMO_LIVE_LLM=false" in env_example
    assert "SKEINRANK_AGENT_SUBMIT_PROPOSALS=false" in env_example
    assert "sk-or-v1" not in env_example

    script = _read("deploy/docker/scripts/openrouter-agent-full-demo.sh")
    assert "set -euo pipefail" in script
    assert "openrouter-agent-full-demo.env.example" in script
    assert "--abort-on-container-exit" in script
    assert "--exit-code-from openrouter-agent-full-demo" in script


def test_makefile_exposes_docker_demo_targets() -> None:
    makefile = _read("Makefile")
    for target in (
        "agent-docker-demo-plan:",
        "agent-docker-demo-config:",
        "agent-docker-demo-run:",
    ):
        assert target in makefile
