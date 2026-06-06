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


def test_openrouter_40k_files_exist_and_are_documented() -> None:
    assert (AGENT_DIR / "demo_report.py").exists()
    assert (REPO_ROOT / "docs" / "guides" / "openrouter-agent.md").exists()

    readme = (AGENT_DIR / "README.md").read_text(encoding="utf-8")
    for fragment in (
        "local demo is network-free",
        "--run-demo-report",
        "--print-demo-review-prompt",
        "skeinrank.agent_demo_report.v1",
        "no OpenRouter calls",
    ):
        assert fragment in readme


def test_demo_report_stitches_candidates_evidence_and_review_queue() -> None:
    runner = _load_module("agent_run_alias_scout_40k", AGENT_DIR / "run_alias_scout.py")
    demo = _load_module("agent_demo_report", AGENT_DIR / "demo_report.py")
    sampler = _load_module(
        "agent_evidence_sampler_40k", AGENT_DIR / "evidence_sampler.py"
    )

    config = runner.AgentRunnerConfig.from_file(AGENT_DIR / "agent_config.example.json")
    failed_queries = runner.load_failed_queries(config.failed_queries_path)
    evidence_records = sampler.load_jsonl_records(config.evidence_records_path)

    report = demo.build_alias_scout_demo_report(
        failed_queries,
        evidence_records,
        candidate_config=config.candidate_discovery,
        evidence_config=config.evidence_sampler,
        demo_config=config.demo_report,
        profile_name=config.default_profile_name,
        proposal_source_name=config.proposal_source_name,
        openrouter_model=config.openrouter_model,
    )

    assert report["schema_version"] == "skeinrank.agent_demo_report.v1"
    assert report["llm_enabled"] is False
    assert report["openrouter_calls"] is False
    assert report["skeinrank_api_calls"] is False
    assert report["proposal_submission_enabled"] is False
    assert report["proposals_submitted"] == 0
    assert report["candidate_summary"]["top_surfaces"][:3] == ["pg", "k8s", "kube"]
    assert report["source_quality"]["ready_for_llm_review"] >= 1

    first = report["review_queue"][0]
    assert first["candidate_alias"] == "pg"
    assert first["review_status"] == "ready_for_llm_review"
    assert first["evidence_windows_found"] >= 1
    assert first["idempotency_key"].startswith(
        "openrouter-alias-scout:profile:infra_incidents:candidate:"
    )
    assert first["candidate_pack"]["candidate_alias"] == "pg"
    assert first["evidence_preview"][0]["text"]


def test_demo_review_prompt_uses_real_sample_pack_without_model_call() -> None:
    runner = _load_module(
        "agent_run_alias_scout_40k_prompt", AGENT_DIR / "run_alias_scout.py"
    )
    demo = _load_module("agent_demo_report_prompt", AGENT_DIR / "demo_report.py")
    sampler = _load_module(
        "agent_evidence_sampler_40k_prompt", AGENT_DIR / "evidence_sampler.py"
    )

    config = runner.AgentRunnerConfig.from_file(AGENT_DIR / "agent_config.example.json")
    failed_queries = runner.load_failed_queries(config.failed_queries_path)
    evidence_records = sampler.load_jsonl_records(config.evidence_records_path)

    prompt = demo.build_demo_review_prompt(
        failed_queries,
        evidence_records,
        candidate_config=config.candidate_discovery,
        evidence_config=config.evidence_sampler,
        profile_name=config.default_profile_name,
    )

    assert "Review this SkeinRank alias candidate" in prompt
    assert '"candidate_alias": "pg"' in prompt
    assert "pg timeout" in prompt
    assert "Return only JSON" in prompt


def test_alias_scout_cli_demo_report_outputs_and_writes_json(tmp_path: Path) -> None:
    base_cmd = [
        sys.executable,
        str(AGENT_DIR / "run_alias_scout.py"),
        "--config",
        str(AGENT_DIR / "agent_config.example.json"),
    ]

    report_result = subprocess.run(
        [*base_cmd, "--run-demo-report"],
        check=True,
        capture_output=True,
        text=True,
    )
    report = json.loads(report_result.stdout)
    assert report["schema_version"] == "skeinrank.agent_demo_report.v1"
    assert report["review_queue"][0]["candidate_alias"] == "pg"

    output_path = tmp_path / "demo-report.json"
    write_result = subprocess.run(
        [*base_cmd, "--write-demo-report", str(output_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    assert write_result.stdout == ""
    written = json.loads(output_path.read_text(encoding="utf-8"))
    assert written["schema_version"] == "skeinrank.agent_demo_report.v1"

    prompt_result = subprocess.run(
        [*base_cmd, "--print-demo-review-prompt"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "Candidate pack" in prompt_result.stdout
    assert "pg" in prompt_result.stdout


def test_openrouter_40k_docs_and_makefile_are_linked() -> None:
    paths = [
        REPO_ROOT / "packages" / "skeinrank-governance-api" / "README.md",
        REPO_ROOT / "docs" / "guides" / "openrouter-agent.md",
        AGENT_DIR / "README.md",
    ]
    for path in paths:
        content = path.read_text(encoding="utf-8")
        assert "--run-demo-report" in content, path
        assert "--print-demo-review-prompt" in content, path

    makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
    assert "agent-demo" in makefile
