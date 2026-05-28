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


def _mock_propose_response() -> dict[str, Any]:
    return {
        "id": "mock-provider-1",
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": json.dumps(
                        {
                            "action": "propose",
                            "confidence": 0.91,
                            "reason": "Mock provider evidence links pg to PostgreSQL.",
                            "risk_flags": [],
                            "alias_value": "pg",
                            "canonical_value": "postgresql",
                            "slot": "database",
                            "context": "pg appears near postgres failover evidence.",
                        }
                    ),
                }
            }
        ],
        "usage": {
            "prompt_tokens": 100,
            "completion_tokens": 40,
            "total_tokens": 140,
            "cost": 0.0001,
        },
    }


def _load_inputs() -> tuple[Any, Any, list[dict[str, Any]], list[dict[str, Any]]]:
    runner = _load_module("agent_run_alias_scout_57a", AGENT_DIR / "run_alias_scout.py")
    sampler = _load_module(
        "agent_evidence_sampler_57a", AGENT_DIR / "evidence_sampler.py"
    )
    config = runner.AgentRunnerConfig.from_file(AGENT_DIR / "agent_config.example.json")
    failed_queries = runner.load_failed_queries(config.failed_queries_path)
    evidence_records = sampler.load_jsonl_records(config.evidence_records_path)
    return runner, config, failed_queries, evidence_records


def test_57a_model_provider_files_docs_and_config_exist() -> None:
    assert (AGENT_DIR / "model_provider.py").exists()
    config = json.loads((AGENT_DIR / "agent_config.example.json").read_text())
    assert config["model_provider"]["provider_type"] == "openrouter"

    for path in (
        REPO_ROOT / "README.md",
        REPO_ROOT / "docs" / "README.md",
        REPO_ROOT / "packages" / "skeinrank-governance-api" / "README.md",
        AGENT_DIR / "README.md",
        REPO_ROOT / "docs" / "deployment" / "model-provider-abstraction.md",
    ):
        content = path.read_text(encoding="utf-8")
        assert "Patch 57A" in content, path
        assert "model provider" in content.lower(), path


def test_model_provider_plan_cli_is_offline() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(AGENT_DIR / "run_alias_scout.py"),
            "--config",
            str(AGENT_DIR / "agent_config.example.json"),
            "--print-model-provider-plan",
        ],
        check=True,
        capture_output=True,
        text=True,
        env={"PATH": ""},
    )
    plan = json.loads(result.stdout)
    assert plan["schema_version"] == "skeinrank.model_provider_plan.v1"
    assert plan["status"] == "planned"
    assert plan["provider"]["provider_type"] == "openrouter"
    assert plan["provider"]["api_key_value"] is None
    assert plan["safety"]["network_calls"] is False
    assert plan["safety"]["secrets_included"] is False


def test_mock_model_provider_matches_chat_completion_interface() -> None:
    provider_module = _load_module(
        "agent_model_provider_57a_mock", AGENT_DIR / "model_provider.py"
    )
    provider = provider_module.MockChatProvider(responses=[_mock_propose_response()])

    response = provider.create_chat_completion(
        model="mock/test-model",
        messages=[{"role": "user", "content": "review pg"}],
        response_format={"type": "json_object"},
    )

    assert response["id"] == "mock-provider-1"
    assert len(provider.calls) == 1
    assert provider.calls[0]["model"] == "mock/test-model"
    metadata = provider_module.provider_metadata(provider)
    assert metadata["provider_type"] == "mock"
    assert metadata["chat_completion_interface"] is True


def test_llm_review_workflow_uses_model_provider_without_openrouter_client() -> None:
    _, config, failed_queries, evidence_records = _load_inputs()
    workflow = _load_module(
        "agent_alias_scout_workflow_57a_provider", AGENT_DIR / "alias_scout_workflow.py"
    )
    provider_module = _load_module(
        "agent_model_provider_57a_provider", AGENT_DIR / "model_provider.py"
    )
    provider = provider_module.MockChatProvider(responses=[_mock_propose_response()])

    report = workflow.run_openrouter_llm_review_workflow(
        failed_queries,
        evidence_records,
        model_provider=provider,
        candidate_config=config.candidate_discovery,
        evidence_config=config.evidence_sampler,
        demo_config=config.demo_report,
        canonical_hints_config=config.canonical_hints,
        llm_config=workflow.LlmReviewConfig(max_candidates=1),
        profile_name=config.default_profile_name,
        proposal_source_name=config.proposal_source_name,
        openrouter_model="mock/test-model",
    )

    assert report["schema_version"] == "skeinrank.agent_llm_review_report.v1"
    assert report["openrouter_calls"] is True  # backward-compatible field
    assert report["provider_calls"] is True
    assert report["model_provider"]["provider_type"] == "mock"
    assert report["llm_review_summary"]["candidates_sent_to_model"] == 1
    assert report["llm_review_summary"]["proposals_prepared"] == 1
    assert report["reviewed_items"][0]["model_provider"]["provider_type"] == "mock"
    assert report["reviewed_items"][0]["model_response_id"] == "mock-provider-1"


def test_create_model_provider_keeps_openrouter_adapter_env_guard(
    monkeypatch: Any,
) -> None:
    provider_module = _load_module(
        "agent_model_provider_57a_factory", AGENT_DIR / "model_provider.py"
    )
    cfg = provider_module.ModelProviderConfig(api_key_env="SKEINRANK_TEST_PROVIDER_KEY")
    monkeypatch.delenv("SKEINRANK_TEST_PROVIDER_KEY", raising=False)
    try:
        provider_module.create_model_provider(cfg)
    except provider_module.ModelProviderError as exc:
        assert "SKEINRANK_TEST_PROVIDER_KEY" in str(exc)
    else:  # pragma: no cover - defensive
        raise AssertionError("Expected missing API key to be rejected")

    monkeypatch.setenv("SKEINRANK_TEST_PROVIDER_KEY", "test-key")
    provider = provider_module.create_model_provider(cfg)
    assert provider.provider_type == "openrouter"
    assert provider.model == "openai/gpt-4o-mini"
