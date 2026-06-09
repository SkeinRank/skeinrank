from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
CLAUDE_DOC = REPO_ROOT / "docs/deployment/mcp-claude-desktop.md"
CURSOR_DOC = REPO_ROOT / "docs/deployment/mcp-cursor-agents.md"
LANGGRAPH_DOC = REPO_ROOT / "docs/deployment/mcp-langgraph-agents.md"
EXAMPLES_DIR = REPO_ROOT / "examples/mcp-agent-docs"
ROOT_README = REPO_ROOT / "README.md"
DOCS_README = REPO_ROOT / "docs/README.md"
API_DOC = REPO_ROOT / "docs/api/governance-api.md"
MCP_KIT_DOC = REPO_ROOT / "docs/deployment/mcp-integration-kit.md"
SCOPED_DOC = REPO_ROOT / "docs/deployment/mcp-scoped-credentials-smoke-tests.md"
CONTRACTS_DOC = REPO_ROOT / "docs/concepts/headless-runtime-contracts.md"
PACKAGE_README = REPO_ROOT / "packages/skeinrank-governance-api/README.md"

EXPECTED_TOOLS = {
    "skeinrank_list_bindings",
    "skeinrank_explain_query",
    "skeinrank_validate_alias",
    "skeinrank_submit_alias_proposal",
    "skeinrank_get_proposal_status",
}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_mcp_client_docs_are_discoverable() -> None:
    for path in (CLAUDE_DOC, CURSOR_DOC, LANGGRAPH_DOC):
        assert path.exists()
    assert (EXAMPLES_DIR / "README.md").exists()

    expected_links = (
        "docs/deployment/mcp-claude-desktop.md",
        "docs/deployment/mcp-cursor-agents.md",
        "docs/deployment/mcp-langgraph-agents.md",
        "examples/mcp-agent-docs",
    )
    root_readme = _read(ROOT_README)
    assert "MCP & agent integration" in root_readme
    assert "docs/deployment/mcp-integration-kit.md" in root_readme
    assert "docs/deployment/mcp-claude-desktop.md" in root_readme
    assert "docs/deployment/mcp-langgraph-agents.md" in root_readme

    for fragment in expected_links:
        assert fragment in _read(PACKAGE_README)
        assert fragment in _read(API_DOC)
        assert fragment in _read(MCP_KIT_DOC)
        assert fragment in _read(SCOPED_DOC)
        assert fragment in _read(CONTRACTS_DOC)

    docs_readme = _read(DOCS_README)
    for fragment in (
        "deployment/mcp-claude-desktop.md",
        "deployment/mcp-cursor-agents.md",
        "deployment/mcp-langgraph-agents.md",
        "../examples/mcp-agent-docs",
    ):
        assert fragment in docs_readme


def test_mcp_client_docs_use_existing_adapter_surface() -> None:
    combined = "\n".join(
        _read(path) for path in (CLAUDE_DOC, CURSOR_DOC, LANGGRAPH_DOC)
    )

    expected = (
        "skeinrank-mcp --smoke-test",
        "skeinrank-mcp --print-tool-manifest",
        "skeinrank-mcp --print-env-template",
        "SKEINRANK_MCP_GOVERNANCE_API_URL",
        "SKEINRANK_MCP_API_TOKEN",
        "SKEINRANK_MCP_ROLE",
        "SKEINRANK_MCP_TIMEOUT_SECONDS",
        "binding_id",
        "mcpServers",
        "command",
        "args",
        "env",
    )
    for fragment in expected:
        assert fragment in combined

    for tool in EXPECTED_TOOLS:
        assert tool in combined

    forbidden = (
        "skeinrank_apply_alias",
        "skeinrank_publish_snapshot",
        "skeinrank_approve_proposal",
        "skeinrank_reload_runtime",
        "POST /v1/runtime/reload",
        "skeinrank-mcp create-token",
        "apply_dictionary through MCP",
    )
    for fragment in forbidden:
        assert fragment not in combined


def test_mcp_agent_docs_examples_are_valid_and_safe() -> None:
    claude_config = json.loads(
        _read(EXAMPLES_DIR / "claude-desktop-config.example.json")
    )
    cursor_config = json.loads(_read(EXAMPLES_DIR / "cursor-mcp-config.example.json"))
    flow = json.loads(_read(EXAMPLES_DIR / "langgraph-tool-flow.example.json"))

    for config in (claude_config, cursor_config):
        server = config["mcpServers"]["skeinrank"]
        assert server["command"] == "skeinrank-mcp"
        assert server["args"] == []
        env = server["env"]
        assert env["SKEINRANK_MCP_GOVERNANCE_API_URL"] == "http://127.0.0.1:8010"
        assert env["SKEINRANK_MCP_ROLE"] == "contributor"
        assert env["SKEINRANK_MCP_TIMEOUT_SECONDS"] == "10.0"
        assert env["SKEINRANK_MCP_API_TOKEN"] == (
            "REPLACE_WITH_SCOPED_SERVICE_ACCOUNT_TOKEN"
        )

    assert flow["schema"] == "skeinrank.langgraph_mcp_tool_flow.v1"
    assert set(flow["allowed_tools"]) == EXPECTED_TOOLS
    assert flow["runtime_mutation_directly_allowed"] is False
    assert flow["human_review_required"] is True
    assert "apply_dictionary" in flow["forbidden_actions"]
    assert "publish_snapshot" in flow["forbidden_actions"]

    for prompt_file in (
        "claude-desktop-system-prompt.md",
        "cursor-agent-rules.md",
        "langgraph-agent-policy.md",
        "smoke-checklist.md",
    ):
        text = _read(EXAMPLES_DIR / prompt_file)
        assert "skeinrank-mcp" in text or "skeinrank_" in text
        assert "publish snapshots" in text or "snapshot" in text


def test_mcp_agent_docs_do_not_ship_real_secrets() -> None:
    for path in EXAMPLES_DIR.iterdir():
        if path.is_file():
            text = _read(path)
            assert "sk_sat_" not in text
            assert "paste-scoped-service-account-token-here" not in text
            assert (
                "REPLACE_WITH_SCOPED_SERVICE_ACCOUNT_TOKEN" in text
                or path.name
                not in {
                    "claude-desktop-config.example.json",
                    "cursor-mcp-config.example.json",
                }
            )
