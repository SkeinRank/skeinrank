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


def test_agent_run_tracking_files_are_present_and_documented() -> None:
    assert (AGENT_DIR / "agent_run_tracking.py").exists()
    readme = (AGENT_DIR / "README.md").read_text(encoding="utf-8")
    guide = (REPO_ROOT / "docs" / "guides" / "openrouter-agent.md").read_text(
        encoding="utf-8"
    )
    for content in (readme, guide):
        assert "--print-agent-tracking-plan" in content
        assert "--print-agent-tracking-plan" in content
        assert "--append-agent-tracking-ledger" in content


def test_content_hashes_are_stable_and_content_sensitive() -> None:
    module = _load_module(
        "agent_run_tracking_hash", AGENT_DIR / "agent_run_tracking.py"
    )

    first = {"id": "doc-1", "title": "Runbook", "text": "pg timeout"}
    same = {"id": "doc-1", "title": "Runbook", "text": "pg timeout"}
    changed = {"id": "doc-1", "title": "Runbook", "text": "pg failover"}

    assert module.compute_record_content_hash(
        first
    ) == module.compute_record_content_hash(same)
    assert module.compute_record_content_hash(
        first
    ) != module.compute_record_content_hash(changed)


def test_tracking_report_classifies_new_and_unchanged_documents(tmp_path: Path) -> None:
    module = _load_module(
        "agent_run_tracking_report", AGENT_DIR / "agent_run_tracking.py"
    )
    config = module.AgentRunTrackingConfig(ledger_path=tmp_path / "ledger.jsonl")
    records = [
        {"id": "doc-1", "source_type": "runbook", "text": "pg timeout"},
        {"id": "doc-2", "source_type": "incident", "text": "k8s rollout"},
    ]

    first = module.build_agent_run_tracking_report(
        records,
        config=config,
        profile_name="infra_incidents",
        openrouter_model="openai/gpt-4o-mini",
        append_ledger=True,
    )
    second = module.build_agent_run_tracking_report(
        records,
        config=config,
        profile_name="infra_incidents",
        openrouter_model="openai/gpt-4o-mini",
    )

    assert first["summary"]["visit_statuses"]["new_document"] == 2
    assert first["ledger_appended"] is True
    assert first["ledger_entries_written"] == 3
    assert second["summary"]["visit_statuses"]["unchanged_seen"] == 2
    assert second["summary"]["skipped_unchanged"] == 2
    assert all(not item["should_scan"] for item in second["document_visits"])


def test_tracking_report_detects_content_and_context_changes(tmp_path: Path) -> None:
    module = _load_module(
        "agent_run_tracking_changes", AGENT_DIR / "agent_run_tracking.py"
    )
    config = module.AgentRunTrackingConfig(ledger_path=tmp_path / "ledger.jsonl")

    module.build_agent_run_tracking_report(
        [{"id": "doc-1", "text": "pg timeout"}],
        config=config,
        profile_name="infra_incidents",
        openrouter_model="openai/gpt-4o-mini",
        append_ledger=True,
    )
    changed_content = module.build_agent_run_tracking_report(
        [{"id": "doc-1", "text": "pg failover"}],
        config=config,
        profile_name="infra_incidents",
        openrouter_model="openai/gpt-4o-mini",
    )
    changed_context = module.build_agent_run_tracking_report(
        [{"id": "doc-1", "text": "pg timeout"}],
        config=config,
        profile_name="infra_incidents",
        openrouter_model="anthropic/claude-3.5-haiku",
    )

    assert changed_content["document_visits"][0]["visit_status"] == "content_changed"
    assert changed_context["document_visits"][0]["visit_status"] == "context_changed"


def test_cli_print_agent_tracking_plan_outputs_safe_json() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(AGENT_DIR / "run_alias_scout.py"),
            "--config",
            str(AGENT_DIR / "agent_config.example.json"),
            "--print-agent-tracking-plan",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)

    assert payload["schema_version"] == "skeinrank.agent_run_tracking_plan.v1"
    assert payload["openrouter_calls"] is False
    assert payload["skeinrank_api_calls"] is False
    assert payload["safety"]["runtime_mutation_enabled"] is False


def test_cli_write_agent_tracking_report(tmp_path: Path) -> None:
    output_path = tmp_path / "tracking-report.json"
    result = subprocess.run(
        [
            sys.executable,
            str(AGENT_DIR / "run_alias_scout.py"),
            "--config",
            str(AGENT_DIR / "agent_config.example.json"),
            "--write-agent-tracking-report",
            str(output_path),
            "--agent-tracking-ledger",
            str(tmp_path / "ledger.jsonl"),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout == ""
    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert payload["schema_version"] == "skeinrank.agent_run_tracking_report.v1"
    assert payload["summary"]["records_loaded"] >= 1
    assert payload["ledger_appended"] is False
