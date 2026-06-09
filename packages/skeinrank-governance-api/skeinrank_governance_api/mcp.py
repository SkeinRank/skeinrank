"""Minimal MCP server for SkeinRank agent proposal tools.

The server intentionally has no third-party MCP dependency. It implements the
small JSON-RPC surface that agent clients need for governed proposal workflows
and delegates all business logic to the existing ``/v1/tools/*`` and governance
REST endpoints.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from .mcp_guardrails import (
    McpToolGuardrailError,
    build_mcp_tool_safety_policy,
    mcp_tool_annotations,
    validate_mcp_tool_call,
)
from .scoped_agent_credentials import build_scoped_agent_credentials_policy

MCP_PROTOCOL_VERSION = "2024-11-05"
DEFAULT_API_URL = "http://127.0.0.1:8010"
DEFAULT_ROLE = "admin"
DEFAULT_TIMEOUT_SECONDS = 10.0
SMOKE_REPORT_SCHEMA = "skeinrank.mcp_smoke_report.v1"

API_URL_ENV = "SKEINRANK_MCP_GOVERNANCE_API_URL"
API_TOKEN_ENV = "SKEINRANK_MCP_API_TOKEN"
ROLE_ENV = "SKEINRANK_MCP_ROLE"
TIMEOUT_ENV = "SKEINRANK_MCP_TIMEOUT_SECONDS"

JsonDict = dict[str, Any]
Transport = Callable[[str, str, Mapping[str, Any] | None], Any]


class SkeinRankMcpError(RuntimeError):
    """Base MCP adapter error."""


class SkeinRankApiError(SkeinRankMcpError):
    """Raised when the governance API returns an error response."""

    def __init__(self, status_code: int, detail: Any) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"SkeinRank API returned {status_code}: {detail}")


@dataclass(frozen=True)
class SkeinRankApiClient:
    """Small stdlib HTTP client for the SkeinRank governance API."""

    base_url: str = DEFAULT_API_URL
    role: str = DEFAULT_ROLE
    api_token: str | None = None
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    transport: Transport | None = None

    def request(
        self, method: str, path: str, payload: Mapping[str, Any] | None = None
    ) -> Any:
        """Send an HTTP request to the governance API."""

        if self.transport is not None:
            return self.transport(method, path, payload)

        url = f"{self.base_url.rstrip('/')}{path}"
        headers = {
            "Accept": "application/json",
            "X-SkeinRank-Role": self.role,
        }
        data: bytes | None = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(payload).encode("utf-8")
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"

        request = Request(url, data=data, headers=headers, method=method.upper())
        try:
            # The URL is operator-configured for this local MCP adapter.
            with urlopen(  # noqa: S310
                request, timeout=self.timeout_seconds
            ) as response:
                body = response.read().decode("utf-8")
                return json.loads(body) if body else None
        except HTTPError as exc:
            body = exc.read().decode("utf-8")
            try:
                detail: Any = json.loads(body)
            except json.JSONDecodeError:
                detail = body or exc.reason
            raise SkeinRankApiError(exc.code, detail) from exc
        except URLError as exc:
            raise SkeinRankMcpError(f"Could not reach SkeinRank API: {exc}") from exc

    def get(self, path: str) -> Any:
        """Send a GET request."""

        return self.request("GET", path, None)

    def post(self, path: str, payload: Mapping[str, Any]) -> Any:
        """Send a POST request."""

        return self.request("POST", path, payload)


@dataclass(frozen=True)
class SkeinRankMcpTools:
    """Tool adapter that maps MCP tool calls to SkeinRank REST endpoints."""

    client: SkeinRankApiClient

    def list_bindings(
        self, *, profile_name: str | None = None, enabled_only: bool = True
    ) -> Any:
        query: dict[str, Any] = {"enabled_only": str(enabled_only).lower()}
        if profile_name:
            query["profile_name"] = profile_name
        return self.client.get(f"/v1/tools/bindings?{urlencode(query)}")

    def explain_query(self, **arguments: Any) -> Any:
        return self.client.post("/v1/tools/explain-query", arguments)

    def validate_alias(self, **arguments: Any) -> Any:
        return self.client.post("/v1/tools/validate-alias", arguments)

    def submit_alias_proposal(self, **arguments: Any) -> Any:
        return self.client.post("/v1/tools/suggest-alias", arguments)

    def get_proposal_status(self, *, profile_name: str, suggestion_id: int) -> Any:
        profile = quote(profile_name, safe="")
        suggestions = self.client.get(f"/v1/governance/profiles/{profile}/suggestions")
        if not isinstance(suggestions, list):
            raise SkeinRankMcpError("Unexpected suggestions response from API.")
        for suggestion in suggestions:
            if isinstance(suggestion, dict) and suggestion.get("id") == suggestion_id:
                return suggestion
        raise SkeinRankApiError(
            404,
            f"Suggestion {suggestion_id} was not found in profile {profile_name!r}.",
        )


def tool_definitions() -> list[JsonDict]:
    """Return MCP tool definitions exposed by the local server."""

    return [
        {
            "name": "skeinrank_list_bindings",
            "description": (
                "List SkeinRank runtime binding contexts available to agents."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "profile_name": {"type": "string"},
                    "enabled_only": {"type": "boolean", "default": True},
                },
                "additionalProperties": False,
            },
            "annotations": mcp_tool_annotations("skeinrank_list_bindings"),
        },
        {
            "name": "skeinrank_explain_query",
            "description": (
                "Explain how a query is canonicalized for a profile or binding."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "profile_name": {"type": "string"},
                    "binding_id": {"type": "integer", "minimum": 1},
                    "query": {"type": "string", "minLength": 1},
                    "size": {"type": "integer", "minimum": 1, "maximum": 100},
                    "include_evidence": {"type": "boolean", "default": True},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
            "annotations": mcp_tool_annotations("skeinrank_explain_query"),
        },
        {
            "name": "skeinrank_validate_alias",
            "description": "Validate an alias proposal without saving it.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "profile_name": {"type": "string"},
                    "binding_id": {"type": "integer", "minimum": 1},
                    "canonical_value": {"type": "string", "minLength": 1},
                    "alias_value": {"type": "string", "minLength": 1},
                    "slot": {"type": "string", "minLength": 1},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "proposal_source_name": {"type": "string"},
                    "idempotency_key": {"type": "string"},
                    "source_payload": {"type": "object"},
                },
                "required": ["canonical_value", "alias_value", "slot"],
                "additionalProperties": False,
            },
            "annotations": mcp_tool_annotations("skeinrank_validate_alias"),
        },
        {
            "name": "skeinrank_submit_alias_proposal",
            "description": (
                "Submit an alias proposal for review; it does not mutate runtime "
                "directly."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "profile_name": {"type": "string"},
                    "binding_id": {"type": "integer", "minimum": 1},
                    "canonical_value": {"type": "string", "minLength": 1},
                    "alias_value": {"type": "string", "minLength": 1},
                    "slot": {"type": "string", "minLength": 1},
                    "description": {"type": "string"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "context": {"type": "string"},
                    "proposal_source_name": {"type": "string"},
                    "idempotency_key": {"type": "string"},
                    "source_payload": {"type": "object"},
                },
                "required": ["canonical_value", "alias_value", "slot"],
                "additionalProperties": False,
            },
            "annotations": mcp_tool_annotations("skeinrank_submit_alias_proposal"),
        },
        {
            "name": "skeinrank_get_proposal_status",
            "description": (
                "Return one proposal/suggestion by profile and suggestion id."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "profile_name": {"type": "string", "minLength": 1},
                    "suggestion_id": {"type": "integer", "minimum": 1},
                },
                "required": ["profile_name", "suggestion_id"],
                "additionalProperties": False,
            },
            "annotations": mcp_tool_annotations("skeinrank_get_proposal_status"),
        },
    ]


def integration_manifest() -> JsonDict:
    """Return a dependency-light manifest for agent/MCP client packaging."""

    return {
        "schema": "skeinrank.mcp_integration_manifest.v1",
        "server": {
            "name": "skeinrank-mcp",
            "transport": "stdio",
            "command": "skeinrank-mcp",
            "description": (
                "Thin MCP stdio adapter over the SkeinRank Governance API "
                "agent-safe REST tools."
            ),
        },
        "environment": {
            API_URL_ENV: {
                "required": False,
                "default": DEFAULT_API_URL,
                "description": "Base URL for the SkeinRank Governance API.",
            },
            ROLE_ENV: {
                "required": False,
                "default": DEFAULT_ROLE,
                "description": "Role header for local no-auth deployments.",
            },
            API_TOKEN_ENV: {
                "required": False,
                "secret": True,
                "description": "Bearer token when Governance API auth is enabled.",
            },
            TIMEOUT_ENV: {
                "required": False,
                "default": DEFAULT_TIMEOUT_SECONDS,
                "description": "HTTP timeout for calls from the adapter to the API.",
            },
        },
        "credentials": build_scoped_agent_credentials_policy(current_user=None),
        "smoke_tests": {
            "offline_command": "skeinrank-mcp --smoke-test",
            "requires_governance_api": False,
            "schema": SMOKE_REPORT_SCHEMA,
        },
        "safety": {
            "mutates_runtime_directly": False,
            "proposal_flow": "validate -> submit proposal -> human review -> snapshot",
            "notes": [
                "The MCP adapter does not own business logic.",
                "Alias changes go through existing /v1/tools/* validation and review APIs.",
                "Use binding_id for production runtime context when available.",
                "The published tool policy rejects unknown tools and top-level proxy arguments.",
            ],
        },
        "tool_policy": build_mcp_tool_safety_policy(),
        "tools": tool_definitions(),
    }


def env_template() -> str:
    """Return a shell-friendly env template for local MCP integration."""

    return "\n".join(
        [
            f"{API_URL_ENV}={DEFAULT_API_URL}",
            "# Local no-auth development may keep admin role.",
            "# Auth-enabled MCP deployments should prefer a contributor service account",
            "# with the agent-proposal-writer scopes from /v1/auth/scoped-agent-credentials.",
            f"{ROLE_ENV}={DEFAULT_ROLE}",
            f"{TIMEOUT_ENV}={DEFAULT_TIMEOUT_SECONDS}",
            f"# {API_TOKEN_ENV}=paste-scoped-service-account-token-here",
            "",
        ]
    )


def smoke_test_report() -> JsonDict:
    """Return an offline MCP packaging smoke-test report.

    The smoke test intentionally avoids network access. It verifies that the
    stdio adapter can initialize, expose tools, and emit packaging metadata.
    """

    fake_client = SkeinRankApiClient(transport=lambda method, path, payload: {})
    server = SkeinRankMcpServer(SkeinRankMcpTools(fake_client))
    initialize = server.handle_request(
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
    )
    tools = server.handle_request(
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
    )
    manifest = integration_manifest()
    tool_names = [tool["name"] for tool in tool_definitions()]
    expected_tools = {
        "skeinrank_list_bindings",
        "skeinrank_explain_query",
        "skeinrank_validate_alias",
        "skeinrank_submit_alias_proposal",
        "skeinrank_get_proposal_status",
    }
    checks = {
        "initialize_ok": bool(initialize and initialize.get("result")),
        "tools_list_ok": bool(tools and tools.get("result", {}).get("tools")),
        "expected_tools_present": expected_tools.issubset(set(tool_names)),
        "manifest_ok": manifest.get("schema")
        == "skeinrank.mcp_integration_manifest.v1",
        "credential_policy_present": (
            manifest.get("credentials", {}).get("schema_version")
            == "skeinrank.scoped_agent_credentials.v1"
        ),
        "tool_policy_present": (
            manifest.get("tool_policy", {}).get("schema_version")
            == "skeinrank.mcp_tool_safety_policy.v1"
        ),
    }
    return {
        "schema": SMOKE_REPORT_SCHEMA,
        "status": "passed" if all(checks.values()) else "failed",
        "checks": checks,
        "tool_names": tool_names,
        "requires_governance_api": False,
    }


class SkeinRankMcpServer:
    """Minimal JSON-RPC MCP server for stdio transports."""

    def __init__(self, tools: SkeinRankMcpTools) -> None:
        self.tools = tools
        self._tool_handlers: dict[str, Callable[..., Any]] = {
            "skeinrank_list_bindings": self.tools.list_bindings,
            "skeinrank_explain_query": self.tools.explain_query,
            "skeinrank_validate_alias": self.tools.validate_alias,
            "skeinrank_submit_alias_proposal": self.tools.submit_alias_proposal,
            "skeinrank_get_proposal_status": self.tools.get_proposal_status,
        }

    def handle_request(self, message: Mapping[str, Any]) -> JsonDict | None:
        """Handle one JSON-RPC request or notification."""

        method = str(message.get("method", ""))
        request_id = message.get("id")
        if request_id is None and method in {
            "notifications/initialized",
            "initialized",
        }:
            return None

        try:
            result = self._dispatch(method, message.get("params") or {})
        except Exception as exc:  # noqa: BLE001 - converted to JSON-RPC error
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": _json_rpc_error(exc),
            }
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    def _dispatch(self, method: str, params: Any) -> Any:
        if method == "initialize":
            return {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "skeinrank-mcp", "version": "0.1.0"},
            }
        if method == "ping":
            return {}
        if method == "tools/list":
            return {"tools": tool_definitions()}
        if method == "tools/call":
            if not isinstance(params, Mapping):
                raise ValueError("tools/call params must be an object.")
            name = str(params.get("name", ""))
            arguments = params.get("arguments") or {}
            if not isinstance(arguments, Mapping):
                raise ValueError("tools/call arguments must be an object.")
            safety_check = validate_mcp_tool_call(name, arguments)
            if not safety_check.allowed:
                raise McpToolGuardrailError(safety_check)
            if name not in self._tool_handlers:
                raise KeyError(f"Unknown SkeinRank MCP tool: {name}")
            result = self._tool_handlers[name](**dict(arguments))
            return {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(result, ensure_ascii=False, indent=2),
                    }
                ],
                "isError": False,
            }
        raise KeyError(f"Unsupported MCP method: {method}")


def _json_rpc_error(exc: Exception) -> JsonDict:
    if isinstance(exc, McpToolGuardrailError):
        return {"code": -32001, "message": str(exc), "data": exc.check.to_dict()}
    if isinstance(exc, SkeinRankApiError):
        return {"code": -32000, "message": str(exc), "data": exc.detail}
    if isinstance(exc, KeyError):
        return {"code": -32601, "message": str(exc)}
    if isinstance(exc, (TypeError, ValueError)):
        return {"code": -32602, "message": str(exc)}
    return {"code": -32603, "message": str(exc)}


def read_framed_message(stdin: Any) -> JsonDict | None:
    """Read one LSP/MCP Content-Length framed JSON message."""

    headers: dict[str, str] = {}
    while True:
        line = stdin.readline()
        if line == b"":
            return None
        line = line.decode("ascii").strip()
        if not line:
            break
        name, _, value = line.partition(":")
        headers[name.lower()] = value.strip()
    content_length = int(headers.get("content-length", "0"))
    if content_length <= 0:
        return None
    payload = stdin.read(content_length)
    if not payload:
        return None
    return json.loads(payload.decode("utf-8"))


def write_framed_message(stdout: Any, message: Mapping[str, Any]) -> None:
    """Write one LSP/MCP Content-Length framed JSON message."""

    payload = json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )
    stdout.write(f"Content-Length: {len(payload)}\r\n\r\n".encode("ascii"))
    stdout.write(payload)
    stdout.flush()


def serve_stdio(server: SkeinRankMcpServer, stdin: Any, stdout: Any) -> int:
    """Serve MCP JSON-RPC messages over stdio until EOF."""

    while True:
        message = read_framed_message(stdin)
        if message is None:
            return 0
        response = server.handle_request(message)
        if response is not None:
            write_framed_message(stdout, response)


def build_server_from_env() -> SkeinRankMcpServer:
    """Create an MCP server using environment configuration."""

    timeout = _float_from_env(os.getenv(TIMEOUT_ENV), DEFAULT_TIMEOUT_SECONDS)
    client = SkeinRankApiClient(
        base_url=os.getenv(API_URL_ENV, DEFAULT_API_URL),
        role=os.getenv(ROLE_ENV, DEFAULT_ROLE),
        api_token=os.getenv(API_TOKEN_ENV),
        timeout_seconds=timeout,
    )
    return SkeinRankMcpServer(SkeinRankMcpTools(client))


def _float_from_env(value: str | None, default: float) -> float:
    if value is None:
        return default
    try:
        parsed = float(value)
    except ValueError:
        return default
    return parsed if parsed > 0 else default


def main(argv: Sequence[str] | None = None) -> int:
    """Run the SkeinRank MCP stdio server."""

    parser = argparse.ArgumentParser(
        prog="skeinrank-mcp",
        description="Run the SkeinRank MCP stdio server for agent proposal tools.",
    )
    parser.add_argument(
        "--api-url",
        default=None,
        help=f"Governance API URL. Defaults to ${API_URL_ENV} or {DEFAULT_API_URL}.",
    )
    parser.add_argument(
        "--role",
        default=None,
        help=(
            f"Role header for local no-auth deployments. "
            f"Defaults to ${ROLE_ENV} or admin."
        ),
    )
    parser.add_argument(
        "--print-tool-manifest",
        action="store_true",
        help="Print a JSON integration manifest and exit without serving stdio.",
    )
    parser.add_argument(
        "--print-env-template",
        action="store_true",
        help="Print an env template for local MCP integration and exit.",
    )
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="Run offline MCP packaging checks and exit without serving stdio.",
    )
    args = parser.parse_args(argv)

    if args.api_url:
        os.environ[API_URL_ENV] = args.api_url
    if args.role:
        os.environ[ROLE_ENV] = args.role

    if args.print_env_template:
        sys.stdout.write(env_template())
        return 0
    if args.print_tool_manifest:
        json.dump(integration_manifest(), sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
        return 0
    if args.smoke_test:
        report = smoke_test_report()
        json.dump(report, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
        return 0 if report["status"] == "passed" else 1

    return serve_stdio(build_server_from_env(), sys.stdin.buffer, sys.stdout.buffer)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
