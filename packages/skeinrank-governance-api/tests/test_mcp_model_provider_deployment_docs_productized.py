from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
DOCS = [
    REPO_ROOT / "docs/deployment/mcp-claude-desktop.md",
    REPO_ROOT / "docs/deployment/mcp-cursor-agents.md",
    REPO_ROOT / "docs/deployment/mcp-integration-kit.md",
    REPO_ROOT / "docs/deployment/mcp-langgraph-agents.md",
    REPO_ROOT / "docs/deployment/mcp-scoped-credentials-smoke-tests.md",
    REPO_ROOT / "docs/deployment/model-provider-abstraction.md",
    REPO_ROOT / "docs/deployment/model-provider-adapters.md",
    REPO_ROOT / "docs/deployment/company-model-integration.md",
]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_mcp_and_model_provider_deployment_docs_are_productized() -> None:
    forbidden = re.compile(r"\b[Pp]atch\b|\b(?:57|62)[A-Z](?:\.\d+)?\b")
    dev_log_phrases = (
        "adds client-specific",
        "introduces the first",
        "adds concrete",
        "does not add auto-apply",
        "future patches",
    )

    for path in DOCS:
        text = _read(path)
        assert not forbidden.search(text), path
        lower = text.lower()
        for phrase in dev_log_phrases:
            assert phrase not in lower, (path, phrase)


def test_mcp_deployment_docs_keep_real_adapter_surface() -> None:
    combined = "\n".join(_read(path) for path in DOCS[:5])
    expected = (
        "skeinrank-mcp --smoke-test",
        "skeinrank-mcp --print-tool-manifest",
        "skeinrank-mcp --print-env-template",
        "skeinrank.mcp_integration_manifest.v1",
        "skeinrank.mcp_tool_safety_policy.v1",
        "GET /v1/auth/scoped-agent-credentials",
        "POST /v1/auth/service-accounts",
        "POST /v1/auth/service-accounts/mcp-agent-proposal-writer/tokens",
        "POST /v1/auth/service-accounts/{account_name}/tokens/{token_id}/rotate",
        "skeinrank.mcp_smoke_report.v1",
        "SKEINRANK_MCP_GOVERNANCE_API_URL",
        "SKEINRANK_MCP_API_TOKEN",
        "skeinrank_list_bindings",
        "skeinrank_explain_query",
        "skeinrank_validate_alias",
        "skeinrank_submit_alias_proposal",
        "skeinrank_get_proposal_status",
    )
    for fragment in expected:
        assert fragment in combined


def test_model_provider_deployment_docs_keep_real_cli_surface() -> None:
    combined = "\n".join(_read(path) for path in DOCS[5:])
    expected = (
        "examples/agents/openrouter_alias_scout/model_provider.py",
        "--print-model-provider-plan",
        "--print-company-model-integration-plan",
        "--run-openrouter-live-pilot",
        "--write-openrouter-validated-pilot-report",
        "skeinrank.model_provider_plan.v1",
        "skeinrank.company_model_integration_plan.v1",
        "openrouter",
        "local_endpoint",
        "mock",
        "OpenRouterChatProvider",
        "MockChatProvider",
        "SKEINRANK_MODEL_PROVIDER_TYPE=local_endpoint",
        "SKEINRANK_MODEL_PROVIDER_BASE_URL=http://127.0.0.1:8000/v1",
        "SKEINRANK_MODEL_PROVIDER_MODEL=company-model",
        "proposal_submission_enabled == false",
    )
    for fragment in expected:
        assert fragment in combined


def test_mcp_and_model_provider_docs_markdown_links_exist() -> None:
    link_pattern = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
    for path in DOCS:
        for target in link_pattern.findall(_read(path)):
            if "://" in target or target.startswith("#"):
                continue
            target_path = (path.parent / target.split("#", 1)[0]).resolve()
            assert target_path.exists(), f"{path} links to missing {target}"
