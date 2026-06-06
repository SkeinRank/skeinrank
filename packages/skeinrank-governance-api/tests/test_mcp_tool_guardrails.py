from __future__ import annotations

import json
from pathlib import Path

from skeinrank_governance_api.mcp import (
    SkeinRankApiClient,
    SkeinRankMcpServer,
    SkeinRankMcpTools,
    integration_manifest,
    smoke_test_report,
    tool_definitions,
)
from skeinrank_governance_api.mcp_guardrails import (
    MCP_TOOL_SAFETY_POLICY_SCHEMA,
    build_mcp_tool_safety_policy,
    validate_mcp_tool_call,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
MCP_GUARDRAIL_DOC = REPO_ROOT / "docs/security/mcp-tool-guardrails.md"
AGENT_SAFETY_DOC = REPO_ROOT / "docs/security/agent-tool-safety.md"
MCP_KIT_DOC = REPO_ROOT / "docs/deployment/mcp-integration-kit.md"
ROOT_README = REPO_ROOT / "README.md"
DOCS_README = REPO_ROOT / "docs/README.md"
CONTRACT = REPO_ROOT / "examples/mcp-integration-kit/agent-tool-contract.json"
LANGGRAPH_FLOW = REPO_ROOT / "examples/mcp-agent-docs/langgraph-tool-flow.example.json"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class FakeTransport:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict | None]] = []

    def __call__(self, method: str, path: str, payload: dict | None):
        self.calls.append((method, path, payload))
        return {"ok": True}


def _server(fake: FakeTransport | None = None) -> SkeinRankMcpServer:
    fake = fake or FakeTransport()
    return SkeinRankMcpServer(SkeinRankMcpTools(SkeinRankApiClient(transport=fake)))


def test_mcp_tool_policy_contract_lists_allowed_and_forbidden_surfaces() -> None:
    policy = build_mcp_tool_safety_policy()

    assert policy["schema_version"] == MCP_TOOL_SAFETY_POLICY_SCHEMA
    assert set(policy["allowed_tools"]) == {
        "skeinrank_list_bindings",
        "skeinrank_explain_query",
        "skeinrank_validate_alias",
        "skeinrank_submit_alias_proposal",
        "skeinrank_get_proposal_status",
    }
    assert "skeinrank_publish_snapshot" in policy["forbidden_tools"]
    assert "publish_snapshot" in policy["forbidden_actions"]
    assert "POST /v1/tools/suggest-alias" in policy["allowed_rest_surfaces"]
    assert any(
        surface.startswith("POST /v1/governance/elasticsearch")
        for surface in policy["forbidden_rest_surfaces"]
    )
    assert policy["runtime_mutation_directly_allowed"] is False
    assert policy["proposal_review_required"] is True


def test_mcp_tool_definitions_use_closed_non_destructive_schemas() -> None:
    for definition in tool_definitions():
        assert definition["inputSchema"]["additionalProperties"] is False
        assert definition["annotations"]["destructiveHint"] is False
        assert definition["annotations"]["openWorldHint"] is False

    submit = next(
        tool
        for tool in tool_definitions()
        if tool["name"] == "skeinrank_submit_alias_proposal"
    )
    assert submit["annotations"]["readOnlyHint"] is False
    assert submit["annotations"]["idempotentHint"] is False


def test_mcp_manifest_and_smoke_report_publish_tool_policy() -> None:
    manifest = integration_manifest()
    report = smoke_test_report()

    assert manifest["tool_policy"]["schema_version"] == MCP_TOOL_SAFETY_POLICY_SCHEMA
    assert manifest["safety"]["mutates_runtime_directly"] is False
    assert "skeinrank_publish_snapshot" in manifest["tool_policy"]["forbidden_tools"]
    assert report["checks"]["tool_policy_present"] is True


def test_mcp_server_rejects_forbidden_runtime_tool_without_api_call() -> None:
    fake = FakeTransport()
    server = _server(fake)

    response = server.handle_request(
        {
            "jsonrpc": "2.0",
            "id": 11,
            "method": "tools/call",
            "params": {
                "name": "skeinrank_publish_snapshot",
                "arguments": {"binding_id": 1},
            },
        }
    )

    assert fake.calls == []
    assert response is not None
    assert response["error"]["code"] == -32001
    assert response["error"]["data"]["allowed"] is False
    assert response["error"]["data"]["errors"] == ["forbidden_tool"]


def test_mcp_server_rejects_proxy_style_arguments_without_api_call() -> None:
    fake = FakeTransport()
    server = _server(fake)

    response = server.handle_request(
        {
            "jsonrpc": "2.0",
            "id": 12,
            "method": "tools/call",
            "params": {
                "name": "skeinrank_validate_alias",
                "arguments": {
                    "binding_id": 1,
                    "canonical_value": "postgresql",
                    "alias_value": "pg",
                    "slot": "database",
                    "endpoint": "/v1/governance/snapshots",
                    "runtime_action": "publish_snapshot",
                },
            },
        }
    )

    assert fake.calls == []
    assert response is not None
    data = response["error"]["data"]
    assert data["schema_version"] == MCP_TOOL_SAFETY_POLICY_SCHEMA
    assert data["allowed"] is False
    assert any("reserved_top_level_argument_keys" in item for item in data["errors"])
    assert "source_payload" in data["allowed_arguments"]


def test_mcp_guardrail_function_allows_declared_tool_arguments() -> None:
    check = validate_mcp_tool_call(
        "skeinrank_submit_alias_proposal",
        {
            "binding_id": 1,
            "canonical_value": "postgresql",
            "alias_value": "pg",
            "slot": "database",
            "context": "Observed in failed-query logs: pg timeout",
            "source_payload": {"evidence": ["pg timeout"]},
        },
    )

    assert check.allowed is True
    assert check.errors == ()


def test_mcp_tool_guardrail_docs_and_examples_are_discoverable() -> None:
    assert MCP_GUARDRAIL_DOC.exists()

    for fragment in (
        "docs/security/mcp-tool-guardrails.md",
        "skeinrank.mcp_tool_safety_policy.v1",
    ):
        assert fragment in _read(ROOT_README) or fragment in _read(MCP_GUARDRAIL_DOC)

    assert "security/mcp-tool-guardrails.md" in _read(DOCS_README)
    assert "mcp-tool-guardrails.md" in _read(AGENT_SAFETY_DOC)
    assert "mcp-tool-guardrails.md" in _read(MCP_KIT_DOC)

    contract = json.loads(_read(CONTRACT))
    flow = json.loads(_read(LANGGRAPH_FLOW))
    assert contract["safety"]["tool_policy_schema"] == MCP_TOOL_SAFETY_POLICY_SCHEMA
    assert "skeinrank_publish_snapshot" in contract["safety"]["forbidden_tools"]
    assert "runtime_action" in contract["safety"]["reserved_top_level_argument_keys"]
    assert flow["tool_policy_schema"] == MCP_TOOL_SAFETY_POLICY_SCHEMA
    assert "run_enrichment_job" in flow["forbidden_actions"]


def test_new_mcp_tool_guardrail_docs_do_not_use_patch_language() -> None:
    for path in (
        MCP_GUARDRAIL_DOC,
        AGENT_SAFETY_DOC,
        MCP_KIT_DOC,
    ):
        assert "Patch" not in _read(path)
