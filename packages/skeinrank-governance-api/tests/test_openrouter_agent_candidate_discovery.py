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


def test_openrouter_40h_files_exist_and_are_documented() -> None:
    assert (AGENT_DIR / "candidate_discovery.py").exists()

    readme = (AGENT_DIR / "README.md").read_text(encoding="utf-8")
    for fragment in (
        "failed-query candidate mining",
        "--discover-candidates",
        "--print-sample-candidate-pack",
        "does not call OpenRouter",
    ):
        assert fragment in readme


def test_candidate_discovery_finds_alias_like_terms_and_prunes_noise() -> None:
    discovery = _load_module(
        "agent_candidate_discovery", AGENT_DIR / "candidate_discovery.py"
    )

    rows = [
        {"query": "k8s rollout stuck after pg failover", "count": 12},
        {"query": "postgres pool exhausted in kube worker", "count": 7},
        {"query": "pg timeout during pod restart", "count": 5},
        {"query": "kube dns incident runbook", "count": 3},
    ]
    config = discovery.CandidateDiscoveryConfig.from_mapping(
        {
            "noise_tokens": [
                "timeout",
                "incident",
                "runbook",
                "restart",
                "worker",
                "stuck",
                "rollout",
                "failover",
                "pool",
                "pod",
                "dns",
                "exhausted",
            ],
            "known_terms": ["postgres", "postgresql", "kubernetes"],
        }
    )
    candidates = discovery.discover_alias_candidates(rows, config=config)
    surfaces = [candidate.surface for candidate in candidates]

    assert surfaces[:3] == ["pg", "k8s", "kube"]
    assert "timeout" not in surfaces
    assert "postgres" not in surfaces
    assert candidates[0].weighted_count == 17
    assert candidates[0].document_frequency == 2
    assert "short_alias_like" in candidates[0].reasons


def test_candidate_report_and_fact_pack_are_compact_and_deterministic() -> None:
    discovery = _load_module(
        "agent_candidate_discovery_report", AGENT_DIR / "candidate_discovery.py"
    )
    runner = _load_module("agent_run_alias_scout_40h", AGENT_DIR / "run_alias_scout.py")

    config = runner.AgentRunnerConfig.from_file(AGENT_DIR / "agent_config.example.json")
    rows = runner.load_failed_queries(config.failed_queries_path)
    report = discovery.build_candidate_discovery_report(
        rows,
        config=config.candidate_discovery,
        profile_name=config.default_profile_name,
    )

    assert report["schema_version"] == "skeinrank.agent_candidate_discovery.v1"
    assert report["llm_enabled"] is False
    assert report["profile_name"] == "infra_incidents"
    assert report["candidates_found"] >= 3
    assert report["candidates"][0]["surface"] == "pg"

    candidates = discovery.discover_alias_candidates(
        rows, config=config.candidate_discovery
    )
    pack = discovery.build_candidate_fact_pack(
        candidates[0], profile_name=config.default_profile_name
    )
    assert pack["candidate_alias"] == "pg"
    assert pack["possible_canonical"] is None
    assert pack["slot"] is None
    assert pack["profile_name"] == "infra_incidents"
    assert pack["evidence"][0].startswith("failed query:")
    assert pack["stats"]["discovery_reasons"] == ["short_alias_like"]


def test_alias_scout_cli_candidate_discovery_outputs_parseable_json() -> None:
    base_cmd = [
        sys.executable,
        str(AGENT_DIR / "run_alias_scout.py"),
        "--config",
        str(AGENT_DIR / "agent_config.example.json"),
    ]

    discovery_result = subprocess.run(
        [*base_cmd, "--discover-candidates"],
        check=True,
        capture_output=True,
        text=True,
    )
    report = json.loads(discovery_result.stdout)
    assert report["schema_version"] == "skeinrank.agent_candidate_discovery.v1"
    assert report["candidates"][0]["surface"] == "pg"

    pack_result = subprocess.run(
        [*base_cmd, "--print-sample-candidate-pack"],
        check=True,
        capture_output=True,
        text=True,
    )
    pack = json.loads(pack_result.stdout)
    assert pack["candidate_alias"] == "pg"
    assert pack["stats"]["document_frequency"] == 2


def test_openrouter_40h_docs_are_linked_from_project_docs() -> None:
    docs = [
        REPO_ROOT / "packages" / "skeinrank-governance-api" / "README.md",
        REPO_ROOT / "docs" / "guides" / "openrouter-agent.md",
        AGENT_DIR / "README.md",
    ]
    for path in docs:
        content = path.read_text(encoding="utf-8")
        assert "--discover-candidates" in content, path
        assert "--print-sample-candidate-pack" in content, path
