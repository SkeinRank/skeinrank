from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
DOC = REPO_ROOT / "docs/deployment/mcp-integration-kit.md"
EXAMPLES_DIR = REPO_ROOT / "examples/mcp-integration-kit"
ROOT_README = REPO_ROOT / "README.md"
DOCS_README = REPO_ROOT / "docs/README.md"
API_DOC = REPO_ROOT / "docs/api/governance-api.md"
CONTRACTS_DOC = REPO_ROOT / "docs/concepts/headless-runtime-contracts.md"
PACKAGE_README = REPO_ROOT / "packages/skeinrank-governance-api/README.md"
MCP_MODULE = (
    REPO_ROOT / "packages/skeinrank-governance-api/skeinrank_governance_api/mcp.py"
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_mcp_integration_kit_docs_are_discoverable() -> None:
    assert DOC.exists()
    assert (EXAMPLES_DIR / "README.md").exists()

    assert "docs/deployment/mcp-integration-kit.md" in _read(ROOT_README)
    assert "examples/mcp-integration-kit" in _read(ROOT_README)
    assert "deployment/mcp-integration-kit.md" in _read(DOCS_README)
    assert "../examples/mcp-integration-kit" in _read(DOCS_README)
    assert "docs/deployment/mcp-integration-kit.md" in _read(PACKAGE_README)
    assert "examples/mcp-integration-kit" in _read(PACKAGE_README)
    assert "docs/deployment/mcp-integration-kit.md" in _read(API_DOC)
    assert "--print-tool-manifest" in _read(CONTRACTS_DOC)


def test_mcp_integration_kit_documents_existing_tool_surface() -> None:
    doc = _read(DOC)
    mcp_module = _read(MCP_MODULE)

    expected = (
        "skeinrank-mcp --api-url http://127.0.0.1:8010",
        "skeinrank-mcp --print-tool-manifest",
        "skeinrank-mcp --print-env-template",
        "skeinrank.mcp_integration_manifest.v1",
        "skeinrank_list_bindings",
        "skeinrank_explain_query",
        "skeinrank_validate_alias",
        "skeinrank_submit_alias_proposal",
        "skeinrank_get_proposal_status",
        "GET /v1/tools/bindings",
        "POST /v1/tools/explain-query",
        "POST /v1/tools/validate-alias",
        "POST /v1/tools/suggest-alias",
        "GET /v1/governance/profiles/{profile_name}/suggestions",
        "binding_id",
    )
    for fragment in expected:
        assert fragment in doc

    for cli_flag in ("--print-tool-manifest", "--print-env-template"):
        assert cli_flag in mcp_module

    forbidden = (
        "skeinrank_apply_alias",
        "skeinrank_publish_snapshot",
        "skeinrank_approve_proposal",
        "/v1/runtime/reload",
        "mcp_sdk",
    )
    for fragment in forbidden:
        assert fragment not in doc


def test_mcp_integration_examples_are_valid_and_safe() -> None:
    env = _read(EXAMPLES_DIR / "skeinrank-mcp.env.example")
    client_config = json.loads(_read(EXAMPLES_DIR / "mcp-client.stdio.example.json"))
    contract = json.loads(_read(EXAMPLES_DIR / "agent-tool-contract.json"))
    prompt = _read(EXAMPLES_DIR / "agent-system-prompt.md")
    workflow = _read(EXAMPLES_DIR / "agent-workflow.md")

    assert "SKEINRANK_MCP_GOVERNANCE_API_URL=http://127.0.0.1:8010" in env
    assert client_config["mcpServers"]["skeinrank"]["command"] == "skeinrank-mcp"
    assert "--api-url" in client_config["mcpServers"]["skeinrank"]["args"]
    assert contract["schema"] == "skeinrank.mcp_agent_tool_contract.v1"
    assert contract["safety"]["direct_runtime_mutation"] is False
    assert contract["safety"]["review_required"] is True

    names = {tool["name"] for tool in contract["tools"]}
    assert names == {
        "skeinrank_list_bindings",
        "skeinrank_explain_query",
        "skeinrank_validate_alias",
        "skeinrank_submit_alias_proposal",
        "skeinrank_get_proposal_status",
    }
    assert "Never claim that a proposal is live in runtime" in prompt
    assert "skeinrank_validate_alias" in workflow
    assert "snapshot publication" in workflow
