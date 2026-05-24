from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

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


def test_openrouter_40g_files_exist_and_are_documented() -> None:
    expected = (
        "openrouter_tools.py",
        "prompts.py",
        "structured_output.py",
    )
    for name in expected:
        assert (AGENT_DIR / name).exists(), name

    readme = (AGENT_DIR / "README.md").read_text(encoding="utf-8")
    for fragment in (
        "OpenRouter/OpenAI-compatible tool schemas",
        "skeinrank_submit_alias_proposal",
        "propose | reject | needs_evidence",
        "do not introduce new backend calls",
    ):
        assert fragment in readme


def test_openrouter_tool_schemas_match_existing_safe_tool_surface() -> None:
    module = _load_module("agent_openrouter_tools", AGENT_DIR / "openrouter_tools.py")
    schemas = module.get_openrouter_tool_schemas()

    names = [schema["function"]["name"] for schema in schemas]
    assert names == [
        "skeinrank_list_bindings",
        "skeinrank_explain_query",
        "skeinrank_validate_alias",
        "skeinrank_submit_alias_proposal",
    ]
    assert all(schema["type"] == "function" for schema in schemas)

    validate_schema = module.get_tool_schema("skeinrank_validate_alias")
    validate_parameters = validate_schema["function"]["parameters"]
    assert validate_parameters["required"] == [
        "canonical_value",
        "alias_value",
        "slot",
    ]
    assert "binding_id" in validate_parameters["properties"]
    assert validate_parameters["additionalProperties"] is False

    submit_schema = module.get_tool_schema("skeinrank_submit_alias_proposal")
    submit_parameters = submit_schema["function"]["parameters"]
    assert submit_parameters["required"] == [
        "canonical_value",
        "alias_value",
        "slot",
    ]
    assert "context" in submit_parameters["properties"]
    assert "publish_snapshot" not in submit_parameters["properties"]


def test_tool_call_argument_parser_accepts_only_json_objects() -> None:
    module = _load_module(
        "agent_openrouter_tools_parser", AGENT_DIR / "openrouter_tools.py"
    )

    assert module.parse_tool_call_arguments('{"binding_id": 7}') == {"binding_id": 7}
    assert module.parse_tool_call_arguments({"profile_name": "infra"}) == {
        "profile_name": "infra"
    }
    assert module.parse_tool_call_arguments(None) == {}

    with pytest.raises(ValueError):
        module.parse_tool_call_arguments('["not", "object"]')
    with pytest.raises(TypeError):
        module.parse_tool_call_arguments(["not", "object"])


def test_alias_review_prompt_uses_compact_candidate_pack() -> None:
    prompts = _load_module("agent_prompts", AGENT_DIR / "prompts.py")

    pack = prompts.build_candidate_pack(
        candidate_alias="pg",
        possible_canonical="postgresql",
        slot="database",
        binding_id=7,
        evidence=["pg timeout after failover", "postgres pool exhausted"],
        stats={"query_count": 42},
        known_conflicts=["page"],
    )
    prompt = prompts.build_alias_review_prompt(pack)

    assert pack["candidate_alias"] == "pg"
    assert pack["binding_id"] == 7
    assert "Return only JSON" in prompt
    assert "needs_evidence" in prompt
    assert "pg timeout after failover" in prompt
    assert "full document" not in prompt.lower()
    assert "Never mutate terminology directly" in prompts.SYSTEM_PROMPT


def test_structured_output_parser_validates_propose_reject_and_payload_mapping() -> (
    None
):
    structured = _load_module(
        "agent_structured_output", AGENT_DIR / "structured_output.py"
    )

    judgment = structured.parse_alias_review_output(
        """
        ```json
        {
          "action": "propose",
          "alias_value": "pg",
          "canonical_value": "postgresql",
          "slot": "database",
          "confidence": 0.91,
          "reason": "Evidence maps pg to postgres.",
          "context": "Observed in failed queries.",
          "risk_flags": []
        }
        ```
        """
    )
    assert judgment.action == "propose"
    assert judgment.confidence == 0.91

    payload = structured.judgment_to_proposal_payload(
        judgment,
        binding_id=7,
        proposal_source_name="openrouter-alias-scout",
        idempotency_key="key-1",
        source_payload={"query_count": 42},
    )
    assert payload == {
        "binding_id": 7,
        "canonical_value": "postgresql",
        "alias_value": "pg",
        "slot": "database",
        "confidence": 0.91,
        "context": "Observed in failed queries.",
        "proposal_source_name": "openrouter-alias-scout",
        "idempotency_key": "key-1",
        "source_payload": {"query_count": 42},
    }

    reject = structured.parse_alias_review_output(
        {
            "action": "reject",
            "confidence": 0.2,
            "reason": "Too generic.",
            "risk_flags": ["generic"],
        }
    )
    assert reject.to_dict()["risk_flags"] == ["generic"]

    with pytest.raises(structured.AliasReviewOutputError):
        structured.parse_alias_review_output(
            {
                "action": "propose",
                "confidence": 0.9,
                "reason": "Missing fields.",
                "risk_flags": [],
            }
        )
    with pytest.raises(structured.AliasReviewOutputError):
        structured.judgment_to_proposal_payload(
            reject,
            proposal_source_name="openrouter-alias-scout",
            idempotency_key="key-2",
        )


def test_alias_scout_cli_print_helpers_output_parseable_contracts() -> None:
    base_cmd = [
        sys.executable,
        str(AGENT_DIR / "run_alias_scout.py"),
        "--config",
        str(AGENT_DIR / "agent_config.example.json"),
    ]

    schemas_result = subprocess.run(
        [*base_cmd, "--print-tool-schemas"],
        check=True,
        capture_output=True,
        text=True,
    )
    schemas = json.loads(schemas_result.stdout)
    assert schemas[0]["function"]["name"] == "skeinrank_list_bindings"

    system_prompt = subprocess.run(
        [*base_cmd, "--print-system-prompt"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert "SkeinRank OpenRouter Alias Scout" in system_prompt
    assert "Never mutate terminology directly" in system_prompt

    review_prompt = subprocess.run(
        [*base_cmd, "--print-sample-review-prompt"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert "Candidate pack" in review_prompt
    assert "postgresql" in review_prompt
    assert "needs_evidence" in review_prompt


def test_openrouter_40g_docs_are_linked_from_project_docs() -> None:
    docs = [
        REPO_ROOT / "README.md",
        REPO_ROOT / "docs" / "README.md",
        REPO_ROOT / "docs" / "api" / "governance-api.md",
        REPO_ROOT / "packages" / "skeinrank-governance-api" / "README.md",
    ]
    for path in docs:
        content = path.read_text(encoding="utf-8")
        assert "Patch 40G" in content, path
        assert "--print-tool-schemas" in content, path
