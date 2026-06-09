from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
API_DOC = REPO_ROOT / "docs/api/governance-api.md"


def _read() -> str:
    return API_DOC.read_text(encoding="utf-8")


def test_governance_api_reference_is_product_documentation() -> None:
    content = _read()

    forbidden_patterns = (
        r"\bPatch\s+\d",
        r"\bpatch-era\b",
        r"\bdev diary\b",
        r"\bdevelopment diary\b",
        r"\badds a\b",
        r"\badds an\b",
        r"\badds `",
        r"later coverage-framework patches",
    )
    for pattern in forbidden_patterns:
        assert re.search(pattern, content, flags=re.IGNORECASE) is None, pattern

    required_sections = (
        "## Operating model",
        "## Health, readiness, and metrics",
        "## Operator reports",
        "## Headless dictionary workflows",
        "## Headless snapshot artifacts",
        "## Terminology-as-Code import/export map",
        "## Profiles, stop lists, terms, aliases, and snapshots",
        "## Suggestions, evidence, and apply gates",
        "## Conflict detection and coverage framework",
        "## Ambiguous aliases and binding policy",
        "## Elasticsearch/OpenSearch discovery and delivery",
        "## Runtime search and canonicalization",
        "## Agent-friendly proposal tools",
        "## Agent run registry and progress",
        "## Auth, users, service accounts, and scoped tokens",
        "## Safety boundaries",
    )
    for section in required_sections:
        assert section in content


def test_governance_api_reference_documents_current_endpoint_groups() -> None:
    content = _read()

    required_fragments = (
        "GET | `/livez`",
        "GET | `/healthz`",
        "GET | `/readyz`",
        "GET | `/schema/health`",
        "GET | `/metrics`",
        "GET | `/v1/ops/troubleshooting/report`",
        "GET | `/v1/ops/alerts/report`",
        "POST | `/v1/headless/dictionaries/validate`",
        "POST | `/v1/headless/dictionaries/apply`",
        "GET | `/v1/headless/dictionaries/export?profile_name=...`",
        "GET | `/v1/headless/snapshots/export?binding_id=7`",
        "POST | `/v1/console/dictionary/validate`",
        "POST | `/v1/console/dictionary/import`",
        "GET | `/v1/governance/profiles`",
        "POST | `/v1/governance/profiles/{profile_name}/suggestions/apply-batch/preview`",
        "POST | `/v1/governance/profiles/{profile_name}/suggestions/apply-batch`",
        "GET | `/v1/governance/conflicts`",
        "PATCH | `/v1/governance/conflicts/{fingerprint}/review`",
        "GET | `/v1/governance/profiles/{profile_name}/ambiguous-aliases`",
        "GET | `/v1/governance/elasticsearch/bindings/{binding_id}/policy`",
        "PUT | `/v1/governance/elasticsearch/bindings/{binding_id}/policy`",
        "GET | `/v1/governance/elasticsearch/connection/status`",
        "POST | `/v1/governance/elasticsearch/bindings/{binding_id}/jobs/preflight`",
        "POST | `/v1/governance/elasticsearch/jobs/{job_id}/pause`",
        "POST | `/v1/governance/elasticsearch/jobs/{job_id}/resume`",
        "POST | `/v1/text/canonicalize`",
        "POST | `/v1/query/plan`",
        "POST | `/v1/query/route-plan`",
        "POST | `/v1/search`",
        "POST | `/v1/search/multi`",
        "GET | `/v1/tools/bindings`",
        "POST | `/v1/tools/explain-query`",
        "POST | `/v1/tools/validate-alias`",
        "POST | `/v1/tools/suggest-alias`",
        "POST | `/v1/agents/runs`",
        "GET | `/v1/agents/runs/{run_id}/progress`",
        "POST | `/v1/agents/runs/{run_id}/resume-plan`",
        "GET | `/v1/agents/runs/{run_id}/report`",
        "GET | `/v1/auth/scoped-agent-credentials`",
        "POST | `/v1/auth/service-accounts/{account_name}/tokens/{token_id}/rotate`",
        "GET | `/v1/dashboard/summary`",
        "GET | `/v1/governance/isolation-checks`",
        "GET | `/v1/governance/role-boundaries`",
    )
    for fragment in required_fragments:
        assert fragment in content


def test_governance_api_reference_links_to_existing_docs_and_examples() -> None:
    content = _read()

    expected_paths = (
        "docs/deployment/headless-quickstart.md",
        "docs/deployment/alerting-hooks-degraded-state-reports.md",
        "docs/guides/terminology-as-code.md",
        "docs/guides/dictionary-cli-planning.md",
        "docs/deployment/gitops-delivery-runbook.md",
        "docs/concepts/coverage-framework.md",
        "docs/guides/coverage-framework.md",
        "examples/coverage-framework",
        "../deployment/blue-green-alias-swap-runbook.md",
        "docs/guides/elasticsearch-enrichment.md",
        "docs/guides/enrichment-beta-hardening.md",
        "docs/guides/enrichment-pause-resume-checkpointing.md",
        "docs/deployment/mcp-integration-kit.md",
        "examples/mcp-integration-kit",
        "docs/deployment/mcp-claude-desktop.md",
        "docs/deployment/mcp-cursor-agents.md",
        "docs/deployment/mcp-langgraph-agents.md",
        "examples/mcp-agent-docs",
        "docs/deployment/mcp-scoped-credentials-smoke-tests.md",
        "examples/mcp-scoped-credentials",
        "docs/security/prompt-injection.md",
        "docs/security/prompt-like-detector.md",
        "docs/security/prompt-injection-regression-corpus.md",
        "docs/security/mcp-tool-guardrails.md",
        "docs/security/agent-tool-safety.md",
        "docs/security/rag-context-boundaries.md",
        "packages/skeinrank-governance-api/README.md",
        "docs/concepts/headless-runtime-contracts.md",
    )
    for path in expected_paths:
        assert path in content
        resolved = (
            (API_DOC.parent / path).resolve()
            if path.startswith("../")
            else REPO_ROOT / path
        )
        assert resolved.exists(), path
