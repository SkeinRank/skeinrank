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


def test_openrouter_40i_files_exist_and_are_documented() -> None:
    assert (AGENT_DIR / "evidence_sampler.py").exists()
    assert (AGENT_DIR / "evidence_records.example.jsonl").exists()

    readme = (AGENT_DIR / "README.md").read_text(encoding="utf-8")
    for fragment in (
        "compact window sampler",
        "--sample-evidence",
        "--print-sample-evidence-pack",
        "no Elasticsearch calls, no OpenRouter calls",
    ):
        assert fragment in readme


def test_evidence_sampler_extracts_compact_windows_and_respects_limits() -> None:
    sampler = _load_module("agent_evidence_sampler", AGENT_DIR / "evidence_sampler.py")

    long_tail = "x" * 500
    records = [
        {
            "id": "doc-1",
            "source_type": "runbook",
            "text": f"before text {long_tail} pg timeout after failover {long_tail}",
        },
        {
            "id": "doc-2",
            "source_type": "incident",
            "snippet": "No matching candidate here.",
        },
        {
            "id": "doc-3",
            "source_type": "search_log",
            "query": "pg restart approval",
        },
    ]
    config = sampler.EvidenceSamplerConfig.from_mapping(
        {
            "max_docs": 2,
            "max_windows": 2,
            "window_chars": 20,
            "max_window_chars": 80,
            "max_total_chars": 160,
        }
    )

    windows = sampler.sample_evidence_windows("pg", records, config=config)

    assert len(windows) == 2
    assert [window.source_id for window in windows] == ["doc-1", "doc-3"]
    assert all("pg" in window.text.lower() for window in windows)
    assert all(len(window.text) <= 80 for window in windows)
    assert all("x" * 100 not in window.text for window in windows)


def test_evidence_report_and_candidate_pack_are_deterministic() -> None:
    discovery = _load_module(
        "agent_candidate_discovery_for_evidence", AGENT_DIR / "candidate_discovery.py"
    )
    sampler = _load_module(
        "agent_evidence_sampler_report", AGENT_DIR / "evidence_sampler.py"
    )
    runner = _load_module("agent_run_alias_scout_40i", AGENT_DIR / "run_alias_scout.py")

    config = runner.AgentRunnerConfig.from_file(AGENT_DIR / "agent_config.example.json")
    failed_queries = runner.load_failed_queries(config.failed_queries_path)
    evidence_records = sampler.load_jsonl_records(config.evidence_records_path)
    candidates = discovery.discover_alias_candidates(
        failed_queries, config=config.candidate_discovery
    )

    report = sampler.build_evidence_sampling_report(
        candidates[:3],
        evidence_records,
        config=config.evidence_sampler,
        profile_name=config.default_profile_name,
    )

    assert report["schema_version"] == "skeinrank.agent_evidence_sampling.v1"
    assert report["llm_enabled"] is False
    assert report["profile_name"] == "infra_incidents"
    assert report["samples"][0]["candidate_alias"] == "pg"
    assert report["samples"][0]["windows_found"] >= 2
    assert (
        report["samples"][0]["total_chars"] <= config.evidence_sampler.max_total_chars
    )

    windows = sampler.sample_evidence_windows(
        candidates[0].surface, evidence_records, config=config.evidence_sampler
    )
    pack = sampler.build_candidate_evidence_pack(
        candidates[0], windows, profile_name=config.default_profile_name
    )

    assert pack["candidate_alias"] == "pg"
    assert pack["possible_canonical"] is None
    assert pack["slot"] is None
    assert pack["profile_name"] == "infra_incidents"
    assert pack["evidence_windows"][0]["source_id"] == "ev-001"
    assert pack["stats"]["evidence_windows"] == len(windows)
    assert (
        pack["stats"]["evidence_total_chars"] <= config.evidence_sampler.max_total_chars
    )


def test_alias_scout_cli_evidence_sampling_outputs_parseable_json() -> None:
    base_cmd = [
        sys.executable,
        str(AGENT_DIR / "run_alias_scout.py"),
        "--config",
        str(AGENT_DIR / "agent_config.example.json"),
    ]

    evidence_result = subprocess.run(
        [*base_cmd, "--sample-evidence"],
        check=True,
        capture_output=True,
        text=True,
    )
    report = json.loads(evidence_result.stdout)
    assert report["schema_version"] == "skeinrank.agent_evidence_sampling.v1"
    assert report["samples"][0]["candidate_alias"] == "pg"
    assert report["samples"][0]["windows_found"] >= 2

    pack_result = subprocess.run(
        [*base_cmd, "--print-sample-evidence-pack"],
        check=True,
        capture_output=True,
        text=True,
    )
    pack = json.loads(pack_result.stdout)
    assert pack["candidate_alias"] == "pg"
    assert pack["evidence_windows"][0]["text"]
    assert "postgres" in " ".join(pack["evidence"]).lower()


def test_openrouter_40i_docs_are_linked_from_project_docs() -> None:
    docs = [
        REPO_ROOT / "packages" / "skeinrank-governance-api" / "README.md",
        REPO_ROOT / "docs" / "guides" / "openrouter-agent.md",
        AGENT_DIR / "README.md",
    ]
    for path in docs:
        content = path.read_text(encoding="utf-8")
        assert "--sample-evidence" in content, path
        assert "--print-sample-evidence-pack" in content, path
