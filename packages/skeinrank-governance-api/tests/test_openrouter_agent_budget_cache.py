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


def _load_inputs() -> tuple[Any, Any, list[dict[str, Any]], list[dict[str, Any]]]:
    runner = _load_module("agent_run_alias_scout_40m", AGENT_DIR / "run_alias_scout.py")
    sampler = _load_module(
        "agent_evidence_sampler_40m", AGENT_DIR / "evidence_sampler.py"
    )
    config = runner.AgentRunnerConfig.from_file(AGENT_DIR / "agent_config.example.json")
    failed_queries = runner.load_failed_queries(config.failed_queries_path)
    evidence_records = sampler.load_jsonl_records(config.evidence_records_path)
    return runner, config, failed_queries, evidence_records


def _mock_response(action: str = "reject") -> dict[str, Any]:
    return {
        "id": f"or-{action}-1",
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": json.dumps(
                        {
                            "action": action,
                            "confidence": 0.4,
                            "reason": "Budget/cache test response.",
                            "risk_flags": ["test"],
                        }
                    ),
                }
            }
        ],
        "usage": {
            "prompt_tokens": 100,
            "completion_tokens": 20,
            "total_tokens": 120,
            "cost": 0.0001,
        },
    }


def test_40m_files_exist_and_docs_are_linked() -> None:
    assert (AGENT_DIR / "budget_cache.py").exists()

    readme = (AGENT_DIR / "README.md").read_text(encoding="utf-8")
    for fragment in (
        "--print-budget-cache-plan",
        "--print-budget-cache-plan",
        "--clear-llm-cache",
        "--max-llm-calls",
        "skeinrank.agent_budget_cache_plan.v1",
    ):
        assert fragment in readme

    gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "examples/agents/openrouter_alias_scout/.cache/" in gitignore


def test_budget_cache_plan_cli_is_offline() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(AGENT_DIR / "run_alias_scout.py"),
            "--config",
            str(AGENT_DIR / "agent_config.example.json"),
            "--print-budget-cache-plan",
            "--max-llm-calls",
            "1",
            "--no-llm-cache",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    plan = json.loads(result.stdout)
    assert plan["schema_version"] == "skeinrank.agent_budget_cache_plan.v1"
    assert plan["openrouter_calls"] is False
    assert plan["budget_cache"]["max_llm_calls_per_run"] == 1
    assert plan["budget_cache"]["cache_enabled"] is False
    assert plan["safety"]["limits_checked_before_live_calls"] is True


def test_budget_limit_skips_extra_candidates_without_more_openrouter_calls() -> None:
    _, config, failed_queries, evidence_records = _load_inputs()
    workflow = _load_module(
        "agent_alias_scout_workflow_40m_budget", AGENT_DIR / "alias_scout_workflow.py"
    )
    client_module = _load_module(
        "agent_openrouter_client_40m_budget", AGENT_DIR / "openrouter_client.py"
    )
    budget_module = _load_module(
        "agent_budget_cache_40m_budget", AGENT_DIR / "budget_cache.py"
    )
    calls: list[tuple[str, str]] = []

    def transport(method: str, path: str, payload: dict[str, Any] | None) -> Any:
        assert payload is not None
        calls.append((method, path))
        return _mock_response("reject")

    client = client_module.OpenRouterClient(api_key="test-key", transport=transport)
    report = workflow.run_openrouter_llm_review_workflow(
        failed_queries,
        evidence_records,
        openrouter_client=client,
        candidate_config=config.candidate_discovery,
        evidence_config=config.evidence_sampler,
        demo_config=config.demo_report,
        llm_config=workflow.LlmReviewConfig(max_candidates=3),
        budget_cache_config=budget_module.AgentBudgetCacheConfig(
            max_llm_calls_per_run=1,
            cache_enabled=False,
        ),
        profile_name=config.default_profile_name,
        proposal_source_name=config.proposal_source_name,
        openrouter_model=config.openrouter_model,
    )

    assert calls == [("POST", "/chat/completions")]
    assert report["llm_review_summary"]["live_openrouter_calls"] == 1
    assert report["llm_review_summary"]["skipped_due_to_budget"] == 2
    assert report["llm_review_summary"]["actions"] == {
        "reject": 1,
        "skipped_budget": 2,
    }
    assert report["budget_cache_summary"]["usage"]["total_tokens"] == 120
    assert report["budget_cache_summary"]["usage"]["estimated_cost_usd"] == 0.0001


def test_response_cache_reuses_identical_review_without_second_call(
    tmp_path: Path,
) -> None:
    _, config, failed_queries, evidence_records = _load_inputs()
    workflow = _load_module(
        "agent_alias_scout_workflow_40m_cache", AGENT_DIR / "alias_scout_workflow.py"
    )
    client_module = _load_module(
        "agent_openrouter_client_40m_cache", AGENT_DIR / "openrouter_client.py"
    )
    budget_module = _load_module(
        "agent_budget_cache_40m_cache", AGENT_DIR / "budget_cache.py"
    )
    cache_config = budget_module.AgentBudgetCacheConfig(
        max_llm_calls_per_run=3,
        cache_enabled=True,
        cache_path=tmp_path / "llm-cache.json",
        write_cache=True,
    )
    calls = 0

    def transport(method: str, path: str, payload: dict[str, Any] | None) -> Any:
        nonlocal calls
        calls += 1
        assert method == "POST"
        assert path == "/chat/completions"
        return _mock_response("needs_evidence")

    client = client_module.OpenRouterClient(api_key="test-key", transport=transport)
    first = workflow.run_openrouter_llm_review_workflow(
        failed_queries,
        evidence_records,
        openrouter_client=client,
        candidate_config=config.candidate_discovery,
        evidence_config=config.evidence_sampler,
        demo_config=config.demo_report,
        llm_config=workflow.LlmReviewConfig(max_candidates=1),
        budget_cache_config=cache_config,
        profile_name=config.default_profile_name,
        proposal_source_name=config.proposal_source_name,
        openrouter_model=config.openrouter_model,
    )
    assert calls == 1
    assert first["budget_cache_summary"]["cache_misses"] == 1
    assert first["budget_cache_summary"]["cache_writes"] == 1
    assert first["reviewed_items"][0]["cache"]["written"] is True

    def failing_transport(
        method: str, path: str, payload: dict[str, Any] | None
    ) -> Any:
        raise AssertionError("cache hit should avoid a second OpenRouter call")

    cached_client = client_module.OpenRouterClient(
        api_key="test-key", transport=failing_transport
    )
    second = workflow.run_openrouter_llm_review_workflow(
        failed_queries,
        evidence_records,
        openrouter_client=cached_client,
        candidate_config=config.candidate_discovery,
        evidence_config=config.evidence_sampler,
        demo_config=config.demo_report,
        llm_config=workflow.LlmReviewConfig(max_candidates=1),
        budget_cache_config=cache_config,
        profile_name=config.default_profile_name,
        proposal_source_name=config.proposal_source_name,
        openrouter_model=config.openrouter_model,
    )

    assert second["budget_cache_summary"]["live_calls_started"] == 0
    assert second["budget_cache_summary"]["cache_hits"] == 1
    assert second["reviewed_items"][0]["cache"]["hit"] is True
    assert (
        second["reviewed_items"][0]["openrouter_response_id"] == "or-needs_evidence-1"
    )


def test_clear_llm_cache_cli_removes_configured_cache(tmp_path: Path) -> None:
    config_path = tmp_path / "agent_config.json"
    raw = json.loads(
        (AGENT_DIR / "agent_config.example.json").read_text(encoding="utf-8")
    )
    raw["budget_cache"]["cache_path"] = str(tmp_path / "cache.json")
    raw["budget_cache"]["cache_enabled"] = True
    config_path.write_text(json.dumps(raw), encoding="utf-8")
    Path(raw["budget_cache"]["cache_path"]).write_text(
        json.dumps(
            {
                "schema_version": "skeinrank.openrouter_alias_scout_cache.v1",
                "namespace": "openrouter-alias-scout-v1",
                "entries": {"a": {"response": {}}},
            }
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(AGENT_DIR / "run_alias_scout.py"),
            "--config",
            str(config_path),
            "--clear-llm-cache",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    report = json.loads(result.stdout)
    assert report["schema_version"] == "skeinrank.agent_cache_clear_report.v1"
    assert report["entries_removed"] == 1
    assert not Path(raw["budget_cache"]["cache_path"]).exists()
