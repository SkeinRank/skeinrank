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
    spec.loader.exec_module(module)
    return module


def test_scheduled_runner_files_are_present_and_documented() -> None:
    assert (AGENT_DIR / "scheduled_runner.py").exists()
    readme = (AGENT_DIR / "README.md").read_text(encoding="utf-8")
    guide = (REPO_ROOT / "docs" / "guides" / "openrouter-agent.md").read_text(
        encoding="utf-8"
    )
    for content in (readme, guide):
        assert "--print-scheduled-runner-plan" in content
        assert "--print-scheduled-runner-plan" in content
        assert "--run-agent-cycle" in content


def test_scheduled_runner_plan_keeps_mutation_disabled(tmp_path: Path) -> None:
    module = _load_module("agent_scheduled_runner", AGENT_DIR / "scheduled_runner.py")
    config = module.ScheduledRunnerConfig(artifacts_dir=tmp_path / "reports")

    plan = config.to_plan()

    assert plan["schema_version"] == "skeinrank.agent_scheduled_runner_plan.v1"
    assert plan["safe_defaults"]["openrouter_calls_by_default"] is False
    assert plan["safe_defaults"]["proposal_submission_by_default"] is False
    assert plan["safe_defaults"]["runtime_mutation_enabled"] is False
    assert "Airflow BashOperator" in plan["orchestrators"]


def test_scheduled_run_id_is_deterministic_for_seed() -> None:
    module = _load_module(
        "agent_scheduled_runner_ids", AGENT_DIR / "scheduled_runner.py"
    )

    first = module.make_scheduled_run_id(cycle_name="alias scout", seed="seed-1")
    second = module.make_scheduled_run_id(cycle_name="alias scout", seed="seed-1")
    third = module.make_scheduled_run_id(cycle_name="alias scout", seed="seed-2")

    assert first == second
    assert first != third
    assert first.startswith("alias-scout-seed-1-")


def test_scheduled_cycle_report_can_signal_needs_review(tmp_path: Path) -> None:
    module = _load_module(
        "agent_scheduled_runner_report", AGENT_DIR / "scheduled_runner.py"
    )
    config = module.ScheduledRunnerConfig(
        artifacts_dir=tmp_path,
        fail_on_needs_review=True,
    )

    report = module.build_scheduled_cycle_report(
        config=config,
        run_id="run-1",
        artifacts=[],
        steps=[{"name": "proposal_inbox", "status": "needs_review"}],
        reports={"proposal_inbox_report": {"schema_version": "x"}},
    )

    assert report["schema_version"] == "skeinrank.agent_scheduled_cycle_report.v1"
    assert report["status"] == "needs_review"
    assert report["recommended_exit_code"] == config.needs_review_exit_code
    assert report["safety"]["runtime_mutation_enabled"] is False


def test_cli_print_scheduled_runner_plan_outputs_safe_json() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(AGENT_DIR / "run_alias_scout.py"),
            "--config",
            str(AGENT_DIR / "agent_config.example.json"),
            "--print-scheduled-runner-plan",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)

    assert payload["schema_version"] == "skeinrank.agent_scheduled_runner_plan.v1"
    assert payload["safe_defaults"]["openrouter_calls_by_default"] is False
    assert payload["safe_defaults"]["proposal_submission_by_default"] is False


def test_cli_run_agent_cycle_writes_artifacts(tmp_path: Path) -> None:
    output_path = tmp_path / "cycle-report.json"
    artifacts_dir = tmp_path / "artifacts"
    result = subprocess.run(
        [
            sys.executable,
            str(AGENT_DIR / "run_alias_scout.py"),
            "--config",
            str(AGENT_DIR / "agent_config.example.json"),
            "--write-agent-cycle-report",
            str(output_path),
            "--agent-cycle-artifacts-dir",
            str(artifacts_dir),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout == ""
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "skeinrank.agent_scheduled_cycle_report.v1"
    assert payload["status"] in {"completed", "needs_review"}
    assert payload["safety"]["live_llm_review_enabled"] is False
    assert payload["safety"]["submit_proposals_enabled"] is False
    assert any(item["name"] == "demo_report" for item in payload["artifacts"])
    assert artifacts_dir.exists()
