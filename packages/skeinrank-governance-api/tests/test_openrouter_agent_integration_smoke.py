from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
AGENT_DIR = REPO_ROOT / "examples" / "agents" / "openrouter_alias_scout"


def _load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    sys.path.insert(0, str(AGENT_DIR))
    try:
        spec.loader.exec_module(module)
    finally:
        try:
            sys.path.remove(str(AGENT_DIR))
        except ValueError:
            pass
    return module


def test_integration_smoke_files_are_present_and_documented() -> None:
    assert (AGENT_DIR / "integration_smoke.py").exists()
    readme = (AGENT_DIR / "README.md").read_text(encoding="utf-8")
    guide = (REPO_ROOT / "docs" / "guides" / "openrouter-agent.md").read_text(
        encoding="utf-8"
    )
    for content in (readme, guide):
        assert "Patch 42A" in content
        assert "--print-integration-smoke-plan" in content
        assert "--write-integration-smoke-report" in content


def test_integration_smoke_plan_is_network_free(tmp_path: Path) -> None:
    module = _load_module("agent_integration_smoke", AGENT_DIR / "integration_smoke.py")
    config = module.FullIntegrationSmokeConfig(artifacts_dir=tmp_path)

    plan = config.to_plan()

    assert plan["schema_version"] == "skeinrank.agent_full_integration_smoke_plan.v1"
    assert plan["safe_defaults"]["openrouter_calls"] is False
    assert plan["safe_defaults"]["elasticsearch_calls"] is False
    assert plan["safe_defaults"]["skeinrank_api_calls"] is False
    assert plan["safe_defaults"]["runtime_mutation_enabled"] is False
    assert "proposal_inbox_report" in plan["stages"]


def test_cli_print_integration_smoke_plan_outputs_json() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(AGENT_DIR / "run_alias_scout.py"),
            "--config",
            str(AGENT_DIR / "agent_config.example.json"),
            "--print-integration-smoke-plan",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)

    assert payload["schema_version"] == "skeinrank.agent_full_integration_smoke_plan.v1"
    assert payload["safe_defaults"]["openrouter_calls"] is False
    assert payload["safe_defaults"]["proposal_submission_enabled"] is False


def test_cli_write_integration_smoke_report_writes_full_contour(tmp_path: Path) -> None:
    output_path = tmp_path / "full-smoke.json"
    artifacts_dir = tmp_path / "artifacts"
    result = subprocess.run(
        [
            sys.executable,
            str(AGENT_DIR / "run_alias_scout.py"),
            "--config",
            str(AGENT_DIR / "agent_config.example.json"),
            "--write-integration-smoke-report",
            str(output_path),
            "--integration-smoke-artifacts-dir",
            str(artifacts_dir),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout == ""
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "skeinrank.agent_full_integration_smoke.v1"
    assert payload["quality_gate"]["status"] == "passed"
    assert payload["summary"]["llm_proposals_prepared"] >= 1
    assert payload["summary"]["validated"] >= 1
    assert payload["summary"]["approved_operations"] >= 1
    assert payload["summary"]["snapshot_eval_enabled"] is True
    assert payload["safety"]["openrouter_calls"] is False
    assert payload["safety"]["skeinrank_api_calls"] is False
    assert payload["safety"]["runtime_mutation_enabled"] is False
    assert artifacts_dir.exists()
    assert any(item["name"] == "cycle_report" for item in payload["artifacts"])


def test_synthetic_smoke_reports_keep_submission_disabled(tmp_path: Path) -> None:
    output_path = tmp_path / "full-smoke.json"
    subprocess.run(
        [
            sys.executable,
            str(AGENT_DIR / "run_alias_scout.py"),
            "--config",
            str(AGENT_DIR / "agent_config.example.json"),
            "--write-integration-smoke-report",
            str(output_path),
            "--integration-smoke-artifacts-dir",
            str(tmp_path / "artifacts"),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert payload["stage_schemas"]["proposal_submission_report"] == (
        "skeinrank.agent_proposal_submission_report.v1"
    )
    assert payload["stage_schemas"]["approved_apply_plan"] == (
        "skeinrank.agent_approved_apply_plan.v1"
    )
    assert payload["safety"]["proposal_submission_enabled"] is False
    assert payload["safety"]["snapshot_publish_enabled"] is False
