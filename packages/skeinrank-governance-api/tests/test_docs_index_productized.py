from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
DOCS_README = REPO_ROOT / "docs/README.md"


def _read_docs_index() -> str:
    return DOCS_README.read_text(encoding="utf-8")


def test_docs_index_is_product_facing_entrypoint() -> None:
    content = _read_docs_index()

    for fragment in (
        "SkeinRank docs",
        "Terminology Control Plane",
        "enterprise search, RAG, and AI-agent workflows",
        "Quick evaluation",
        "Core concepts",
        "Terminology-as-Code",
        "Runtime API and SDKs",
        "Governance console UI",
        "MCP and agents",
        "Deployment and operations",
        "Security and safety",
        "Benchmarks and quality gates",
        "Pilots and support",
        "Community",
    ):
        assert fragment in content


def test_docs_index_keeps_existing_product_links_discoverable() -> None:
    content = _read_docs_index()

    expected_links = (
        "overview.md",
        "product-positioning.md",
        "concepts/terminology-control-plane.md",
        "concepts/profiles-bindings-snapshots.md",
        "concepts/headless-runtime-contracts.md",
        "adr/0001-headless-runtime-contracts.md",
        "guides/terminology-as-code.md",
        "guides/dictionary-cli-planning.md",
        "guides/runtime-routing-api.md",
        "guides/context-trigger-disambiguation.md",
        "api/governance-api.md",
        "deployment/mcp-integration-kit.md",
        "../examples/mcp-integration-kit",
        "deployment/mcp-claude-desktop.md",
        "deployment/mcp-cursor-agents.md",
        "deployment/mcp-langgraph-agents.md",
        "../examples/mcp-agent-docs",
        "guides/elasticsearch-enrichment.md",
        "deployment/blue-green-alias-swap-runbook.md",
        "../examples/blue-green-alias-swap",
        "deployment/release-compose.md",
        "deployment/docker-images.md",
        "deployment/helm-chart.md",
        "deployment/helm-production.md",
        "deployment/helm-smoke-test.md",
        "deployment/ci-routing.md",
        "security/prompt-injection.md",
        "security/rag-context-boundaries.md",
        "security/agent-tool-safety.md",
        "security/prompt-like-detector.md",
        "security/mcp-tool-guardrails.md",
        "security/prompt-injection-regression-corpus.md",
        "benchmarks/headless-agent-workflow.md",
        "benchmarks/openrouter-live-pilot.md",
        "benchmarks/retrieval-eval-baseline.md",
        "benchmarks/synthetic-smoke-generator.md",
        "benchmarks/cost-latency-throughput-report.md",
        "pilots/elasticsearch-pilot-integration.md",
        "pilots/first-company-pilot-runbook.md",
        "pilots/troubleshooting-bundle-export.md",
        "pilots/support-bundle-production.md",
        "community/discussions.md",
        "community/github-labels.md",
    )
    for link in expected_links:
        assert link in content


def test_docs_index_does_not_read_like_an_implementation_log() -> None:
    content = _read_docs_index()
    lower_content = content.lower()

    assert "Patch" not in content
    assert "patch" not in lower_content
    assert "changelog" not in lower_content
    assert "dev-журнал" not in lower_content
    assert "дневник" not in lower_content
