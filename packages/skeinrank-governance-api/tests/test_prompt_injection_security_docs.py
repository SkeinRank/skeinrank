from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
DOCS = REPO_ROOT / "docs"
SECURITY_DOCS = DOCS / "security"

PROMPT_INJECTION_DOC = SECURITY_DOCS / "prompt-injection.md"
RAG_BOUNDARIES_DOC = SECURITY_DOCS / "rag-context-boundaries.md"
AGENT_TOOL_SAFETY_DOC = SECURITY_DOCS / "agent-tool-safety.md"
PROMPT_LIKE_DETECTOR_DOC = SECURITY_DOCS / "prompt-like-detector.md"
PROMPT_REGRESSION_CORPUS_DOC = SECURITY_DOCS / "prompt-injection-regression-corpus.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_prompt_injection_security_docs_exist() -> None:
    assert PROMPT_INJECTION_DOC.exists()
    assert RAG_BOUNDARIES_DOC.exists()
    assert AGENT_TOOL_SAFETY_DOC.exists()
    assert PROMPT_LIKE_DETECTOR_DOC.exists()
    assert PROMPT_REGRESSION_CORPUS_DOC.exists()


def test_prompt_injection_taxonomy_is_product_facing() -> None:
    content = _read(PROMPT_INJECTION_DOC)

    for fragment in (
        "Prompt injection risk taxonomy",
        "Untrusted runtime data",
        "Direct prompt injection",
        "Indirect prompt injection",
        "Tool injection",
        "Poisoned terminology",
        "Evidence poisoning",
        "Context confusion",
        "ignore previous instructions",
        "proposal review",
        "approved snapshot",
        "binding-scoped runtime use",
    ):
        assert fragment in content

    assert "Patch" not in content


def test_rag_context_boundaries_define_data_not_instructions_contract() -> None:
    content = _read(RAG_BOUNDARIES_DOC)

    for fragment in (
        "RAG context boundaries",
        "retrieved documents",
        "untrusted data",
        "trusted policy",
        "System/tool policy",
        "User request",
        "SkeinRank runtime context",
        "Retrieved/evidence context",
        "binding id",
        "pinned snapshot",
        "Treat that sentence as evidence of risky content",
    ):
        assert fragment in content

    assert "Patch" not in content


def test_agent_tool_safety_documents_safe_mcp_surface() -> None:
    content = _read(AGENT_TOOL_SAFETY_DOC)

    allowed_tools = (
        "skeinrank_list_bindings",
        "skeinrank_explain_query",
        "skeinrank_validate_alias",
        "skeinrank_submit_alias_proposal",
        "skeinrank_get_proposal_status",
    )
    for tool_name in allowed_tools:
        assert tool_name in content

    for unsafe_action in (
        "publish snapshots",
        "mutate production bindings",
        "run enrichment jobs",
        "send email",
        "read secrets",
        "proposal-first safety model",
        "Proposal only",
    ):
        assert unsafe_action in content

    assert "Patch" not in content


def test_prompt_like_detector_doc_documents_review_semantics() -> None:
    content = _read(PROMPT_LIKE_DETECTOR_DOC)

    for fragment in (
        "Prompt-like instruction detector",
        "skeinrank.prompt_injection_risk.v1",
        "Dictionary lint",
        "Console dictionary validate/import",
        "Proposal validation",
        "Elasticsearch/OpenSearch evidence",
        "risk_findings",
        "prompt_like_instruction_findings",
        "does not silently delete or rewrite text",
    ):
        assert fragment in content

    assert "Patch" not in content


def test_security_docs_are_linked_from_readme_and_docs_index() -> None:
    root_readme = _read(REPO_ROOT / "README.md")
    docs_readme = _read(DOCS / "README.md")
    deployment_security = _read(DOCS / "deployment" / "security.md")
    mcp_kit = _read(DOCS / "deployment" / "mcp-integration-kit.md")

    expected_links = (
        "docs/security/prompt-injection.md",
        "docs/security/rag-context-boundaries.md",
        "docs/security/agent-tool-safety.md",
    )
    assert "docs/security/prompt-injection.md" in root_readme
    assert "docs/security/agent-tool-safety.md" in root_readme
    for link in expected_links:
        assert link in deployment_security

    for link in (
        "security/prompt-injection.md",
        "security/rag-context-boundaries.md",
        "security/agent-tool-safety.md",
    ):
        assert link in docs_readme

    for link in (
        "../security/prompt-injection.md",
        "../security/rag-context-boundaries.md",
        "../security/agent-tool-safety.md",
    ):
        assert link in mcp_kit

    assert "security/prompt-like-detector.md" in docs_readme
    assert "security/prompt-injection-regression-corpus.md" in docs_readme
    assert "docs/security/prompt-like-detector.md" in deployment_security
    assert "../security/prompt-like-detector.md" in mcp_kit
    assert "../security/prompt-injection-regression-corpus.md" in mcp_kit
    assert "prompt-like-detector.md" in _read(PROMPT_INJECTION_DOC)


def test_mcp_integration_kit_has_tool_injection_boundary_without_runtime_mutation() -> (
    None
):
    content = _read(DOCS / "deployment" / "mcp-integration-kit.md")

    assert "Prompt injection and tool-injection boundary" in content
    assert (
        "user text, retrieved documents, evidence snippets, and model output" in content
    )
    assert "does not publish snapshots" in content
    assert "mutate production bindings" in content
    assert "run enrichment jobs" in content
    assert "safe output is a proposal" in content
