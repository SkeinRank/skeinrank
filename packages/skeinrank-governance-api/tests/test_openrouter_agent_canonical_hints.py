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


def test_41a_canonical_hints_enrich_candidate_packs() -> None:
    runner = _load_module("agent_run_alias_scout_41a", AGENT_DIR / "run_alias_scout.py")
    sampler = _load_module(
        "agent_evidence_sampler_41a", AGENT_DIR / "evidence_sampler.py"
    )
    demo = _load_module("agent_demo_report_41a", AGENT_DIR / "demo_report.py")

    config = runner.AgentRunnerConfig.from_file(AGENT_DIR / "agent_config.example.json")
    failed_queries = runner.load_failed_queries(config.failed_queries_path)
    evidence_records = sampler.load_jsonl_records(config.evidence_records_path)
    report = demo.build_alias_scout_demo_report(
        failed_queries,
        evidence_records,
        candidate_config=config.candidate_discovery,
        evidence_config=config.evidence_sampler,
        demo_config=config.demo_report,
        canonical_hints_config=config.canonical_hints,
        profile_name=config.default_profile_name,
    )

    assert report["canonical_hints"]["terms_loaded"] >= 4
    by_alias = {item["candidate_alias"]: item for item in report["review_queue"]}

    pg_pack = by_alias["pg"]["candidate_pack"]
    assert pg_pack["possible_canonical"] == "postgresql"
    assert pg_pack["slot"] == "database"
    assert pg_pack["canonical_hint"]["reason"] == "single_configured_alias_match"
    assert "page" in pg_pack["known_conflicts"]

    k8s_pack = by_alias["k8s"]["candidate_pack"]
    assert k8s_pack["possible_canonical"] == "kubernetes"
    assert k8s_pack["slot"] == "technology"
    assert k8s_pack["canonical_candidates"][0]["canonical_value"] == "kubernetes"


def test_41a_noise_tokens_keep_validation_sprint_noise_out_of_review_queue() -> None:
    runner = _load_module(
        "agent_run_alias_scout_41a_noise", AGENT_DIR / "run_alias_scout.py"
    )
    config = runner.AgentRunnerConfig.from_file(AGENT_DIR / "agent_config.example.json")
    failed_queries = [
        {"query": "pg timeout after failover", "count": 12},
        {"query": "k8s pod crashloop", "count": 9},
        {"query": "kube dns incident", "count": 7},
        {"query": "rabbit queue stuck", "count": 5},
        {"query": "elastic shard red", "count": 4},
    ]
    candidates = runner.discover_alias_candidates(
        failed_queries, config=config.candidate_discovery
    )
    surfaces = [candidate.surface for candidate in candidates]

    assert surfaces[:3] == ["pg", "k8s", "kube"]
    assert "queue" not in surfaces
    assert "red" not in surfaces
    assert "shard" not in surfaces


def test_41a_review_prompt_contains_canonical_hint_rules() -> None:
    runner = _load_module(
        "agent_run_alias_scout_41a_prompt", AGENT_DIR / "run_alias_scout.py"
    )
    sampler = _load_module(
        "agent_evidence_sampler_41a_prompt", AGENT_DIR / "evidence_sampler.py"
    )
    demo = _load_module("agent_demo_report_41a_prompt", AGENT_DIR / "demo_report.py")

    config = runner.AgentRunnerConfig.from_file(AGENT_DIR / "agent_config.example.json")
    failed_queries = runner.load_failed_queries(config.failed_queries_path)
    evidence_records = sampler.load_jsonl_records(config.evidence_records_path)
    prompt = demo.build_demo_review_prompt(
        failed_queries,
        evidence_records,
        candidate_config=config.candidate_discovery,
        evidence_config=config.evidence_sampler,
        canonical_hints_config=config.canonical_hints,
        profile_name=config.default_profile_name,
    )

    assert "canonical_hint" in prompt
    assert "known_canonicals" in prompt
    assert "postgresql" in prompt
    assert "Use action=propose" in prompt


def test_41a_cli_reports_canonical_hints_and_llm_plan_uses_them() -> None:
    hints_result = subprocess.run(
        [
            sys.executable,
            str(AGENT_DIR / "run_alias_scout.py"),
            "--config",
            str(AGENT_DIR / "agent_config.example.json"),
            "--print-canonical-hints",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    hints = json.loads(hints_result.stdout)
    assert hints["schema_version"] == "skeinrank.agent_canonical_hints.v1"
    assert hints["canonical_hints"]["aliases_loaded"] >= 4

    pack_result = subprocess.run(
        [
            sys.executable,
            str(AGENT_DIR / "run_alias_scout.py"),
            "--config",
            str(AGENT_DIR / "agent_config.example.json"),
            "--print-sample-evidence-pack",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    pack = json.loads(pack_result.stdout)
    assert pack["schema_version"] if "schema_version" in pack else True
    assert pack["possible_canonical"] == "postgresql"
    assert pack["canonical_hint"]["confidence"] >= 0.9


def test_41a_docs_are_linked() -> None:
    paths = [
        REPO_ROOT / "docs" / "README.md",
        REPO_ROOT / "docs" / "api" / "governance-api.md",
        REPO_ROOT / "packages" / "skeinrank-governance-api" / "README.md",
        REPO_ROOT / "docs" / "guides" / "openrouter-agent.md",
        AGENT_DIR / "README.md",
    ]
    for path in paths:
        content = path.read_text(encoding="utf-8")
        assert "Patch 41A" in content, path
        assert "--print-canonical-hints" in content, path
