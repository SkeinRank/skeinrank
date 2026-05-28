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


def _local_propose_response() -> dict[str, Any]:
    return {
        "id": "local-chatcmpl-1",
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": json.dumps(
                        {
                            "action": "propose",
                            "confidence": 0.9,
                            "reason": "Local endpoint mapped kube to Kubernetes.",
                            "risk_flags": [],
                            "alias_value": "kube",
                            "canonical_value": "kubernetes",
                            "slot": "technology",
                            "context": "kube appears in rollout evidence.",
                        }
                    ),
                }
            }
        ],
        "usage": {"prompt_tokens": 80, "completion_tokens": 30, "total_tokens": 110},
    }


def test_57b_local_endpoint_docs_and_config_exist() -> None:
    config = json.loads((AGENT_DIR / "agent_config.example.json").read_text())
    assert config["model_provider"]["provider_type"] == "openrouter"
    local_config = config["local_model_provider_example"]
    assert local_config["provider_type"] == "local_endpoint"
    assert local_config["base_url"].endswith("/v1")
    assert local_config["require_api_key"] is False

    for path in (
        REPO_ROOT / "README.md",
        REPO_ROOT / "docs" / "README.md",
        REPO_ROOT / "packages" / "skeinrank-governance-api" / "README.md",
        AGENT_DIR / "README.md",
        REPO_ROOT / "docs" / "deployment" / "model-provider-adapters.md",
    ):
        content = path.read_text(encoding="utf-8")
        assert "Patch 57B" in content, path
        assert "local endpoint" in content.lower(), path


def test_model_provider_plan_supports_local_endpoint_without_network_calls(
    monkeypatch: Any,
) -> None:
    monkeypatch.delenv("SKEINRANK_LOCAL_MODEL_API_KEY", raising=False)
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
        env={
            "PATH": "",
            "SKEINRANK_MODEL_PROVIDER_TYPE": "local_endpoint",
            "SKEINRANK_MODEL_PROVIDER_BASE_URL": "http://127.0.0.1:11434/v1",
            "SKEINRANK_MODEL_PROVIDER_MODEL": "llama3.1:8b",
        },
    )
    plan = json.loads(result.stdout)
    assert plan["schema_version"] == "skeinrank.model_provider_plan.v1"
    assert plan["provider"]["provider_type"] == "local_endpoint"
    assert plan["provider"]["base_url"] == "http://127.0.0.1:11434/v1"
    assert plan["provider"]["model"] == "llama3.1:8b"
    assert plan["provider"]["api_key_configured"] is False
    assert plan["provider"]["api_key_value"] is None
    assert plan["provider"]["requires_api_key"] is False
    assert plan["safety"]["network_calls"] is False
    assert "local_endpoint" in plan["supported_provider_types"]


def test_create_local_endpoint_provider_does_not_require_api_key_by_default(
    monkeypatch: Any,
) -> None:
    provider_module = _load_module(
        "agent_model_provider_57b_local", AGENT_DIR / "model_provider.py"
    )
    monkeypatch.delenv("SKEINRANK_LOCAL_MODEL_API_KEY", raising=False)
    cfg = provider_module.ModelProviderConfig.from_mapping(
        {
            "provider_type": "local_endpoint",
            "provider_name": "local-vllm",
            "base_url": "http://127.0.0.1:8000/v1",
            "model": "local/test-model",
        }
    )
    provider = provider_module.create_model_provider(cfg)
    assert provider.provider_type == "local_endpoint"
    assert provider.provider_name == "local-vllm"
    assert provider.model == "local/test-model"
    assert provider.api_key is None


def test_local_endpoint_provider_builds_chat_completion_payload() -> None:
    provider_module = _load_module(
        "agent_model_provider_57b_transport", AGENT_DIR / "model_provider.py"
    )
    calls: list[tuple[str, str, dict[str, Any] | None]] = []

    def transport(method: str, path: str, payload: dict[str, Any] | None) -> Any:
        calls.append((method, path, payload))
        return _local_propose_response()

    provider = provider_module.LocalEndpointChatProvider(
        base_url="http://localhost:8000/v1",
        model="local/test-model",
        provider_name="local-test",
        transport=transport,
    )
    response = provider.create_chat_completion(
        model="local/test-model",
        messages=[{"role": "user", "content": "review kube"}],
        response_format={"type": "json_object"},
        tools=[{"type": "function", "function": {"name": "validate_alias"}}],
    )

    assert response["id"] == "local-chatcmpl-1"
    assert calls == [
        (
            "POST",
            "/chat/completions",
            {
                "model": "local/test-model",
                "messages": [{"role": "user", "content": "review kube"}],
                "temperature": 0.0,
                "max_tokens": 700,
                "tools": [{"type": "function", "function": {"name": "validate_alias"}}],
                "tool_choice": "auto",
                "response_format": {"type": "json_object"},
            },
        )
    ]
    metadata = provider_module.provider_metadata(provider)
    assert metadata["provider_type"] == "local_endpoint"
    assert metadata["chat_completion_interface"] is True


def test_local_endpoint_can_drive_llm_review_workflow() -> None:
    runner = _load_module("agent_run_alias_scout_57b", AGENT_DIR / "run_alias_scout.py")
    sampler = _load_module(
        "agent_evidence_sampler_57b", AGENT_DIR / "evidence_sampler.py"
    )
    workflow = _load_module(
        "agent_alias_scout_workflow_57b", AGENT_DIR / "alias_scout_workflow.py"
    )
    provider_module = _load_module(
        "agent_model_provider_57b_workflow", AGENT_DIR / "model_provider.py"
    )
    config = runner.AgentRunnerConfig.from_file(AGENT_DIR / "agent_config.example.json")
    failed_queries = runner.load_failed_queries(config.failed_queries_path)
    evidence_records = sampler.load_jsonl_records(config.evidence_records_path)

    provider = provider_module.LocalEndpointChatProvider(
        model="local/test-model",
        transport=lambda _method, _path, _payload: _local_propose_response(),
    )
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
        openrouter_model="local/test-model",
    )

    assert report["schema_version"] == "skeinrank.agent_llm_review_report.v1"
    assert report["provider_calls"] is True
    assert report["model_provider"]["provider_type"] == "local_endpoint"
    assert report["llm_review_summary"]["candidates_sent_to_model"] == 1
    assert (
        report["reviewed_items"][0]["model_provider"]["provider_type"]
        == "local_endpoint"
    )
    assert report["reviewed_items"][0]["model_response_id"] == "local-chatcmpl-1"
