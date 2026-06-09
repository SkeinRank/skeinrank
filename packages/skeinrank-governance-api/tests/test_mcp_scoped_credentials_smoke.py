from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
DOC = REPO_ROOT / "docs/deployment/mcp-scoped-credentials-smoke-tests.md"
EXAMPLES_DIR = REPO_ROOT / "examples/mcp-scoped-credentials"
ROOT_README = REPO_ROOT / "README.md"
DOCS_README = REPO_ROOT / "docs/README.md"
API_DOC = REPO_ROOT / "docs/api/governance-api.md"
MCP_KIT_DOC = REPO_ROOT / "docs/deployment/mcp-integration-kit.md"
PACKAGE_README = REPO_ROOT / "packages/skeinrank-governance-api/README.md"
MCP_MODULE = (
    REPO_ROOT / "packages/skeinrank-governance-api/skeinrank_governance_api/mcp.py"
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_mcp_scoped_credentials_docs_are_discoverable() -> None:
    assert DOC.exists()
    assert (EXAMPLES_DIR / "README.md").exists()

    docs_index = _read(DOCS_README)
    assert "deployment/mcp-scoped-credentials-smoke-tests.md" in docs_index
    assert "../examples/mcp-scoped-credentials" in docs_index
    assert "docs/deployment/mcp-scoped-credentials-smoke-tests.md" in _read(
        PACKAGE_README
    )
    assert "examples/mcp-scoped-credentials" in _read(PACKAGE_README)
    assert "mcp-scoped-credentials-smoke-tests.md" in _read(MCP_KIT_DOC)


def test_mcp_scoped_credentials_doc_uses_existing_auth_surfaces() -> None:
    doc = _read(DOC)
    api_doc = _read(API_DOC)
    mcp_module = _read(MCP_MODULE)

    expected = (
        "GET /v1/auth/scoped-agent-credentials",
        "POST /v1/auth/service-accounts",
        "POST /v1/auth/service-accounts/mcp-agent-proposal-writer/tokens",
        "POST /v1/auth/service-accounts/{account_name}/tokens/{token_id}/rotate",
        "skeinrank.scoped_agent_credentials.v1",
        "agent-proposal-writer",
        "agent:tools:read",
        "agent:tools:validate",
        "agent:tools:suggest",
        "agent:tools:explain",
        "SKEINRANK_MCP_API_TOKEN",
        "skeinrank-mcp --smoke-test",
        "skeinrank.mcp_smoke_report.v1",
    )
    for fragment in expected:
        assert fragment in doc

    assert "GET /v1/auth/scoped-agent-credentials" in api_doc
    assert (
        "POST /v1/auth/service-accounts/{account_name}/tokens/{token_id}/rotate"
        in api_doc
    )
    assert "--smoke-test" in mcp_module
    assert "smoke_test_report" in mcp_module

    forbidden = (
        "POST /v1/auth/mcp/tokens",
        "skeinrank-mcp create-token",
        "skeinrank_mcp_create_service_account",
        "skeinrank_approve_proposal",
        "skeinrank_publish_snapshot",
    )
    for fragment in forbidden:
        assert fragment not in doc


def test_mcp_scoped_credential_examples_are_valid_json_and_least_privilege() -> None:
    service_account = json.loads(
        _read(EXAMPLES_DIR / "create-proposal-writer-service-account.json")
    )
    proposal_token = json.loads(
        _read(EXAMPLES_DIR / "create-proposal-writer-token.json")
    )
    readonly_token = json.loads(
        _read(EXAMPLES_DIR / "create-readonly-validator-token.json")
    )
    rotation = json.loads(_read(EXAMPLES_DIR / "rotate-proposal-writer-token.json"))
    client_config = json.loads(
        _read(EXAMPLES_DIR / "mcp-client.scoped-token.example.json")
    )
    smoke = json.loads(_read(EXAMPLES_DIR / "smoke-test.expected.json"))

    assert service_account["role"] == "contributor"
    assert service_account["is_active"] is True

    proposal_scopes = set(proposal_token["scopes"])
    assert "agent:tools:suggest" in proposal_scopes
    assert "agent:tools:validate" in proposal_scopes
    assert "migration:apply" not in proposal_scopes
    assert "admin" not in proposal_scopes

    readonly_scopes = set(readonly_token["scopes"])
    assert "agent:tools:validate" in readonly_scopes
    assert "agent:tools:suggest" not in readonly_scopes

    assert rotation["scopes"] == proposal_token["scopes"]
    assert client_config["mcpServers"]["skeinrank"]["command"] == "skeinrank-mcp"
    env = client_config["mcpServers"]["skeinrank"]["env"]
    assert env["SKEINRANK_MCP_ROLE"] == "contributor"
    assert "SKEINRANK_MCP_API_TOKEN" in env
    assert smoke["schema"] == "skeinrank.mcp_smoke_report.v1"
    assert smoke["status"] == "passed"
    assert smoke["requires_governance_api"] is False
