from __future__ import annotations

import io
import json

from skeinrank_governance_api.mcp import (
    SkeinRankApiClient,
    SkeinRankMcpServer,
    SkeinRankMcpTools,
    read_framed_message,
    tool_definitions,
    write_framed_message,
)


class FakeTransport:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict | None]] = []

    def __call__(self, method: str, path: str, payload: dict | None):
        self.calls.append((method, path, payload))
        if path.startswith("/v1/tools/bindings"):
            return [
                {
                    "id": 7,
                    "name": "Infra docs",
                    "profile_name": "infra_incidents",
                    "normalized_profile_name": "infra_incidents",
                    "provider": "elasticsearch",
                    "index_name": "infra-docs",
                    "text_fields": ["title", "body"],
                    "target_field": "skeinrank",
                    "is_enabled": True,
                    "snapshot_status": "ready",
                }
            ]
        if path == "/v1/tools/validate-alias":
            return {"validation_summary": {"status": "passed"}, **(payload or {})}
        if path == "/v1/tools/suggest-alias":
            return {
                "created": True,
                "suggestion": {"id": 3, "status": "pending", **(payload or {})},
                "validation_summary": {"status": "passed"},
            }
        if path == "/v1/tools/explain-query":
            return {"canonical_query": "kubernetes timeout", "changed": True}
        if path == "/v1/governance/profiles/infra_incidents/suggestions":
            return [
                {"id": 3, "status": "pending", "canonical_value": "kubernetes"},
                {"id": 4, "status": "approved", "canonical_value": "postgresql"},
            ]
        raise AssertionError(f"Unexpected request: {method} {path}")


def _server(fake: FakeTransport | None = None) -> SkeinRankMcpServer:
    fake = fake or FakeTransport()
    client = SkeinRankApiClient(transport=fake)
    return SkeinRankMcpServer(SkeinRankMcpTools(client))


def test_mcp_tool_definitions_include_agent_tools():
    names = {tool["name"] for tool in tool_definitions()}

    assert {
        "skeinrank_list_bindings",
        "skeinrank_explain_query",
        "skeinrank_validate_alias",
        "skeinrank_submit_alias_proposal",
        "skeinrank_get_proposal_status",
    }.issubset(names)


def test_mcp_initialize_and_tools_list():
    server = _server()

    initialized = server.handle_request(
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
    )
    tools = server.handle_request(
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
    )

    assert initialized is not None
    assert initialized["result"]["capabilities"] == {"tools": {}}
    assert tools is not None
    assert any(
        tool["name"] == "skeinrank_submit_alias_proposal"
        for tool in tools["result"]["tools"]
    )


def test_mcp_list_bindings_calls_tools_api():
    fake = FakeTransport()
    server = _server(fake)

    response = server.handle_request(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "skeinrank_list_bindings",
                "arguments": {"profile_name": "infra_incidents"},
            },
        }
    )

    assert fake.calls[0][0] == "GET"
    assert fake.calls[0][1].startswith("/v1/tools/bindings?")
    assert response is not None
    text = response["result"]["content"][0]["text"]
    payload = json.loads(text)
    assert payload[0]["profile_name"] == "infra_incidents"


def test_mcp_submit_alias_proposal_calls_agent_tool_api():
    fake = FakeTransport()
    server = _server(fake)

    response = server.handle_request(
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "skeinrank_submit_alias_proposal",
                "arguments": {
                    "binding_id": 7,
                    "canonical_value": "kubernetes",
                    "alias_value": "kube",
                    "slot": "tool",
                    "idempotency_key": "scout:infra:kube",
                },
            },
        }
    )

    assert fake.calls[0] == (
        "POST",
        "/v1/tools/suggest-alias",
        {
            "binding_id": 7,
            "canonical_value": "kubernetes",
            "alias_value": "kube",
            "slot": "tool",
            "idempotency_key": "scout:infra:kube",
        },
    )
    assert response is not None
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["created"] is True
    assert payload["suggestion"]["status"] == "pending"


def test_mcp_get_proposal_status_filters_profile_suggestions():
    fake = FakeTransport()
    server = _server(fake)

    response = server.handle_request(
        {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {
                "name": "skeinrank_get_proposal_status",
                "arguments": {"profile_name": "infra_incidents", "suggestion_id": 4},
            },
        }
    )

    assert fake.calls[0] == (
        "GET",
        "/v1/governance/profiles/infra_incidents/suggestions",
        None,
    )
    assert response is not None
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["id"] == 4
    assert payload["status"] == "approved"


def test_mcp_framed_message_round_trip():
    message = {"jsonrpc": "2.0", "id": 1, "method": "ping", "params": {}}
    stream = io.BytesIO()

    write_framed_message(stream, message)
    stream.seek(0)

    assert read_framed_message(stream) == message
