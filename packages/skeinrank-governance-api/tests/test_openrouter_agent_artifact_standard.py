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


def test_artifact_standard_files_are_present_and_documented() -> None:
    assert (AGENT_DIR / "artifact_standard.py").exists()
    readme = (AGENT_DIR / "README.md").read_text(encoding="utf-8")
    guide = (REPO_ROOT / "docs" / "guides" / "openrouter-agent.md").read_text(
        encoding="utf-8"
    )
    for content in (readme, guide):
        assert "--print-artifacts-standard-plan" in content
        assert "--print-artifacts-standard-plan" in content
        assert "manifest.json" in content


def test_artifact_standard_writes_manifest_and_report_files(tmp_path: Path) -> None:
    module = _load_module("agent_artifact_standard", AGENT_DIR / "artifact_standard.py")
    config = module.ArtifactStandardConfig(root_dir=tmp_path / "reports")

    artifact = module.write_standard_artifact(
        config=config,
        run_id="run-1",
        name="llm_review_report",
        payload={"schema_version": "skeinrank.test.v1", "ok": True},
    )
    manifest = module.write_artifact_manifest(
        config=config,
        run_id="run-1",
        artifacts=[artifact],
        status="completed",
    )

    run_dir = tmp_path / "reports" / "run-1"
    assert (run_dir / "reports" / "llm_review_report.json").exists()
    assert (run_dir / "manifest.json").exists()
    assert (run_dir / "run_summary.json").exists()
    assert manifest["schema_version"] == "skeinrank.agent_artifact_manifest.v1"
    assert manifest["artifact_count"] == 1
    assert manifest["artifacts"][0]["relative_path"] == "reports/llm_review_report.json"
    assert "sha256" in manifest["artifacts"][0]


def test_cli_print_artifacts_standard_plan_outputs_json() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(AGENT_DIR / "run_alias_scout.py"),
            "--config",
            str(AGENT_DIR / "agent_config.example.json"),
            "--print-artifacts-standard-plan",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)

    assert payload["schema_version"] == "skeinrank.agent_artifacts_standard_plan.v1"
    assert payload["safe_defaults"]["runtime_mutation_enabled"] is False
    assert "demo_report" in payload["canonical_artifacts"]


def test_scheduled_cycle_uses_standard_manifest(tmp_path: Path) -> None:
    output_path = tmp_path / "cycle.json"
    artifacts_dir = tmp_path / "artifacts"
    subprocess.run(
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

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "skeinrank.agent_scheduled_cycle_report.v1"
    manifest_info = payload["artifact_manifest"]
    manifest_path = Path(manifest_info["path"])
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "skeinrank.agent_artifact_manifest.v1"
    assert manifest["artifact_count"] >= 1
    assert all("relative_path" in item for item in manifest["artifacts"])
