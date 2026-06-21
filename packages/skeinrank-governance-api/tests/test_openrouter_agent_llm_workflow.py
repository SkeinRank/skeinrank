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


def test_openrouter_40j_files_exist_and_are_documented() -> None:
    assert (AGENT_DIR / "openrouter_client.py").exists()
    assert (AGENT_DIR / "alias_scout_workflow.py").exists()

    readme = (AGENT_DIR / "README.md").read_text(encoding="utf-8")
    for fragment in (
        "Live model review",
        "--print-llm-review-plan",
        "--llm-review",
        "skeinrank.agent_llm_review_report.v1",
        "LangGraph-ready",
    ):
        assert fragment in readme


def test_openrouter_client_builds_chat_completion_payload() -> None:
    client_module = _load_module(
        "agent_openrouter_client_payload", AGENT_DIR / "openrouter_client.py"
    )
    calls: list[tuple[str, str, dict[str, Any] | None]] = []

    def transport(method: str, path: str, payload: dict[str, Any] | None) -> Any:
        calls.append((method, path, payload))
        return {
            "id": "or-test-1",
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": json.dumps(
                            {
                                "action": "reject",
                                "confidence": 0.4,
                                "reason": "not enough evidence",
                                "risk_flags": ["weak_evidence"],
                            }
                        ),
                    }
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 8},
        }

    client = client_module.OpenRouterClient(api_key="test", transport=transport)
    response = client.create_chat_completion(
        model="openai/gpt-4o-mini",
        messages=[{"role": "user", "content": "review pg"}],
        response_format={"type": "json_object"},
    )

    assert response["id"] == "or-test-1"
    assert calls == [
        (
            "POST",
            "/chat/completions",
            {
                "model": "openai/gpt-4o-mini",
                "messages": [{"role": "user", "content": "review pg"}],
                "temperature": 0.0,
                "max_tokens": 700,
                "response_format": {"type": "json_object"},
            },
        )
    ]
    assert "not enough evidence" in client_module.extract_first_message_content(
        response
    )


def test_llm_review_workflow_uses_mock_openrouter_and_prepares_payload() -> None:
    runner = _load_module("agent_run_alias_scout_40j", AGENT_DIR / "run_alias_scout.py")
    sampler = _load_module(
        "agent_evidence_sampler_40j", AGENT_DIR / "evidence_sampler.py"
    )
    workflow = _load_module(
        "agent_alias_scout_workflow_40j", AGENT_DIR / "alias_scout_workflow.py"
    )
    client_module = _load_module(
        "agent_openrouter_client_40j", AGENT_DIR / "openrouter_client.py"
    )

    config = runner.AgentRunnerConfig.from_file(AGENT_DIR / "agent_config.example.json")
    failed_queries = runner.load_failed_queries(config.failed_queries_path)
    evidence_records = sampler.load_jsonl_records(config.evidence_records_path)

    def transport(method: str, path: str, payload: dict[str, Any] | None) -> Any:
        assert method == "POST"
        assert path == "/chat/completions"
        assert payload is not None
        assert payload["response_format"] == {"type": "json_object"}
        assert (
            "Review this SkeinRank alias candidate" in payload["messages"][1]["content"]
        )
        return {
            "id": "or-review-1",
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": json.dumps(
                            {
                                "action": "propose",
                                "confidence": 0.91,
                                "reason": "Evidence links pg to Postgres incidents.",
                                "risk_flags": [],
                                "alias_value": "pg",
                                "canonical_value": "postgresql",
                                "slot": "database",
                                "context": "pg appears near postgres pool/failover evidence",
                            }
                        ),
                    }
                }
            ],
            "usage": {"prompt_tokens": 100, "completion_tokens": 50},
        }

    client = client_module.OpenRouterClient(api_key="test-key", transport=transport)
    report = workflow.run_openrouter_llm_review_workflow(
        failed_queries,
        evidence_records,
        openrouter_client=client,
        candidate_config=config.candidate_discovery,
        evidence_config=config.evidence_sampler,
        demo_config=config.demo_report,
        llm_config=workflow.LlmReviewConfig(max_candidates=1),
        profile_name=config.default_profile_name,
        proposal_source_name=config.proposal_source_name,
        openrouter_model=config.openrouter_model,
    )

    assert report["schema_version"] == "skeinrank.agent_llm_review_report.v1"
    assert report["llm_enabled"] is True
    assert report["openrouter_calls"] is True
    assert report["skeinrank_api_calls"] is False
    assert report["proposals_submitted"] == 0
    assert report["langgraph_ready"] is True
    assert report["llm_review_summary"]["candidates_sent_to_model"] == 1
    assert report["llm_review_summary"]["proposals_prepared"] == 1
    assert report["llm_review_summary"]["actions"] == {"propose": 1}

    reviewed = report["reviewed_items"][0]
    assert reviewed["candidate_alias"] == "pg"
    assert reviewed["proposal_ready_for_validation"] is True
    assert reviewed["proposal_payload"]["canonical_value"] == "postgresql"
    assert reviewed["proposal_payload"]["alias_value"] == "pg"
    assert reviewed["proposal_payload"]["profile_name"] == "infra_incidents"
    assert reviewed["proposal_payload"]["proposal_source_name"] == (
        "openrouter-alias-scout"
    )
    assert reviewed["openrouter_usage"] == {
        "prompt_tokens": 100,
        "completion_tokens": 50,
    }


def test_llm_review_plan_cli_is_offline_and_langgraph_ready() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(AGENT_DIR / "run_alias_scout.py"),
            "--config",
            str(AGENT_DIR / "agent_config.example.json"),
            "--print-llm-review-plan",
            "--max-candidates",
            "2",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    plan = json.loads(result.stdout)
    assert plan["schema_version"] == "skeinrank.agent_llm_review_plan.v1"
    assert plan["openrouter_calls"] is False
    assert plan["llm_enabled"] is True
    assert plan["langgraph_ready"] is True
    assert plan["max_candidates"] == 2
    assert plan["candidate_aliases"] == ["pg", "k8s"]
    assert "openrouter_review" in plan["workflow_nodes"]


def test_llm_review_cli_requires_openrouter_key_for_live_execution() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(AGENT_DIR / "run_alias_scout.py"),
            "--config",
            str(AGENT_DIR / "agent_config.example.json"),
            "--llm-review",
            "--max-candidates",
            "1",
        ],
        check=False,
        capture_output=True,
        text=True,
        env={"PATH": ""},
    )
    assert result.returncode != 0
    assert "OpenRouter API key is required" in result.stderr


def test_openrouter_40j_docs_are_linked() -> None:
    paths = [
        REPO_ROOT / "packages" / "skeinrank-governance-api" / "README.md",
        REPO_ROOT / "docs" / "guides" / "openrouter-agent.md",
        AGENT_DIR / "README.md",
    ]
    for path in paths:
        content = path.read_text(encoding="utf-8")
        assert "--print-llm-review-plan" in content, path
        assert "--llm-review" in content, path


def test_proposal_confidence_abstains_when_model_judgments_disagree() -> None:
    runner = _load_module("agent_run_alias_scout_84e", AGENT_DIR / "run_alias_scout.py")
    sampler = _load_module(
        "agent_evidence_sampler_84e", AGENT_DIR / "evidence_sampler.py"
    )
    workflow = _load_module(
        "agent_alias_scout_workflow_84e", AGENT_DIR / "alias_scout_workflow.py"
    )
    confidence = _load_module(
        "agent_proposal_confidence_84e", AGENT_DIR / "proposal_confidence.py"
    )
    client_module = _load_module(
        "agent_openrouter_client_84e", AGENT_DIR / "openrouter_client.py"
    )

    config = runner.AgentRunnerConfig.from_file(AGENT_DIR / "agent_config.example.json")
    failed_queries = runner.load_failed_queries(config.failed_queries_path)
    evidence_records = sampler.load_jsonl_records(config.evidence_records_path)
    responses = [
        {
            "action": "propose",
            "confidence": 0.92,
            "reason": "Evidence links pg to PostgreSQL incidents.",
            "risk_flags": [],
            "alias_value": "pg",
            "canonical_value": "postgresql",
            "slot": "database",
            "context": "pg appears near postgres pool/failover evidence",
        },
        {
            "action": "needs_evidence",
            "confidence": 0.58,
            "reason": "The pg surface has conflicting meanings in evidence.",
            "risk_flags": ["ambiguous_surface"],
        },
    ]
    call_index = 0

    def transport(method: str, path: str, payload: dict[str, Any] | None) -> Any:
        nonlocal call_index
        assert method == "POST"
        assert path == "/chat/completions"
        assert payload is not None
        content = responses[call_index]
        call_index += 1
        return {
            "id": f"or-review-{call_index}",
            "choices": [
                {"message": {"role": "assistant", "content": json.dumps(content)}}
            ],
            "usage": {"prompt_tokens": 100, "completion_tokens": 40},
        }

    report = workflow.run_openrouter_llm_review_workflow(
        failed_queries,
        evidence_records,
        openrouter_client=client_module.OpenRouterClient(
            api_key="test-key", transport=transport
        ),
        candidate_config=config.candidate_discovery,
        evidence_config=config.evidence_sampler,
        demo_config=config.demo_report,
        llm_config=workflow.LlmReviewConfig(
            max_candidates=1,
            confidence=confidence.ProposalConfidenceConfig(
                judgment_samples_per_candidate=2,
                min_consensus_to_prepare_proposal=1.0,
            ),
        ),
        profile_name=config.default_profile_name,
        proposal_source_name=config.proposal_source_name,
        openrouter_model=config.openrouter_model,
    )

    reviewed = report["reviewed_items"][0]
    assert call_index == 2
    assert reviewed["proposal_ready_for_validation"] is False
    assert reviewed["proposal_payload"] is None
    assert reviewed["judgment"]["action"] == "needs_evidence"
    assert reviewed["confidence_decision"]["abstained"] is True
    assert (
        reviewed["confidence_decision"]["abstention_reason"] == "low_action_consensus"
    )
    assert reviewed["confidence_decision"]["consensus_score"] == 0.5
    assert reviewed["sample_judgments"][0]["judgment"]["action"] == "propose"
    assert reviewed["sample_judgments"][1]["judgment"]["action"] == "needs_evidence"
    assert report["llm_review_summary"]["abstentions"] == 1


def test_structured_output_accepts_decision_trace_for_review_reasoning() -> None:
    structured_output = _load_module(
        "agent_structured_output_84e", AGENT_DIR / "structured_output.py"
    )

    judgment = structured_output.parse_alias_review_output(
        {
            "action": "propose",
            "confidence": 0.9,
            "reason": "Evidence maps pcore to payments-core.",
            "risk_flags": [],
            "alias_value": "pcore",
            "canonical_value": "payments-core",
            "slot": "service",
            "decision_trace": {
                "evidence_strength": "strong",
                "ambiguity": "low",
                "canonical_choice": "dominant surface in evidence",
            },
        }
    )

    payload = structured_output.judgment_to_proposal_payload(
        judgment,
        proposal_source_name="openrouter-alias-scout",
        idempotency_key="idem-1",
        profile_name="infra_incidents",
    )

    assert judgment.to_dict()["decision_trace"]["evidence_strength"] == "strong"
    assert payload["source_payload"]["model_decision_trace"]["ambiguity"] == "low"
