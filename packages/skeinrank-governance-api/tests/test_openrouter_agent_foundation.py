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


def test_openrouter_agent_foundation_files_exist_and_are_documented() -> None:
    expected = (
        "README.md",
        "agent_config.example.json",
        "env.example",
        "failed_queries.example.jsonl",
        "skeinrank_client.py",
        "run_alias_scout.py",
    )
    for name in expected:
        assert (AGENT_DIR / name).exists(), name

    readme = (AGENT_DIR / "README.md").read_text(encoding="utf-8")
    for fragment in (
        "LLM / agent -> proposal -> validation -> review/policy -> snapshot -> runtime",
        "/v1/tools/bindings",
        "/v1/tools/validate-alias",
        "/v1/tools/suggest-alias",
        "does not call OpenRouter yet",
    ):
        assert fragment in readme


def test_agent_config_and_failed_queries_are_valid() -> None:
    config = json.loads((AGENT_DIR / "agent_config.example.json").read_text())
    assert config["skeinrank_api_url"] == "http://127.0.0.1:8010"
    assert config["skeinrank_role"] == "contributor"
    assert config["openrouter_api_key_env"] == "OPENROUTER_API_KEY"
    assert config["dry_run"] is True

    rows = [
        json.loads(line)
        for line in (AGENT_DIR / "failed_queries.example.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line
    ]
    assert len(rows) >= 3
    assert all(row["query"] for row in rows)
    assert any("pg" in row["query"] for row in rows)


def test_skeinrank_agent_client_maps_rest_tool_paths() -> None:
    module = _load_module("agent_skeinrank_client", AGENT_DIR / "skeinrank_client.py")
    calls: list[tuple[str, str, dict[str, Any] | None]] = []

    def transport(method: str, path: str, payload: dict[str, Any] | None) -> Any:
        calls.append((method, path, payload))
        if path.startswith("/v1/tools/bindings"):
            return [{"id": 7, "name": "Infra"}]
        return {"ok": True, "path": path, "payload": payload}

    client = module.SkeinRankAgentClient(transport=transport)

    assert client.list_bindings(profile_name="infra")[0]["id"] == 7
    client.explain_query(binding_id=7, query="k8s pg timeout")
    client.validate_alias(
        binding_id=7,
        canonical_value="postgresql",
        alias_value="pg",
        slot="database",
        proposal_source_name="openrouter-alias-scout",
        idempotency_key="key-1",
        source_payload={"query_count": 3},
    )
    client.suggest_alias(
        binding_id=7,
        canonical_value="postgresql",
        alias_value="pg",
        slot="database",
        context="Observed in failed queries.",
    )

    assert calls[0][0] == "GET"
    assert calls[0][1].startswith("/v1/tools/bindings?")
    assert calls[1][1] == "/v1/tools/explain-query"
    assert calls[2][1] == "/v1/tools/validate-alias"
    assert calls[2][2]["proposal_source_type"] == "agent"
    assert calls[3][1] == "/v1/tools/suggest-alias"


def test_alias_scout_dry_run_plan_is_deterministic() -> None:
    runner = _load_module("agent_run_alias_scout", AGENT_DIR / "run_alias_scout.py")
    config = runner.AgentRunnerConfig.from_file(AGENT_DIR / "agent_config.example.json")
    queries = runner.load_failed_queries(config.failed_queries_path, limit=2)
    plan = runner.build_run_plan(config, queries)

    assert plan["schema_version"] == "skeinrank.agent_run_plan.v1"
    assert plan["llm_enabled"] is False
    assert plan["dry_run"] is True
    assert plan["queries_loaded"] == 2
    assert len(plan["sample_queries"]) == 2
    assert plan["sample_queries"][0]["idempotency_key"].startswith(
        "openrouter-alias-scout:profile:infra_incidents:query:"
    )


def test_alias_scout_script_dry_run_outputs_json() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(AGENT_DIR / "run_alias_scout.py"),
            "--config",
            str(AGENT_DIR / "agent_config.example.json"),
            "--dry-run-plan",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    assert payload["runner"] == "openrouter_alias_scout"
    assert payload["llm_enabled"] is False
    assert payload["queries_loaded"] >= 3


def test_agent_foundation_is_linked_from_docs() -> None:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    docs_readme = (REPO_ROOT / "docs" / "README.md").read_text(encoding="utf-8")
    api_docs = (REPO_ROOT / "docs" / "api" / "governance-api.md").read_text(
        encoding="utf-8"
    )

    for content in (readme, docs_readme, api_docs):
        assert "examples/agents/openrouter_alias_scout" in content
