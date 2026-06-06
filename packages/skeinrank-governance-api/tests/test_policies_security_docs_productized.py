from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
DOCS = REPO_ROOT / "docs"

POLICY_DOCS = [
    DOCS / "policies" / "apply-policy-risk-levels.md",
    DOCS / "policies" / "role-boundaries.md",
    DOCS / "policies" / "token-rotation-scoped-agent-credentials.md",
    DOCS / "policies" / "profile-isolation-checks.md",
]

SECURITY_DOCS = [
    DOCS / "deployment" / "security.md",
    DOCS / "security" / "agent-tool-safety.md",
    DOCS / "security" / "mcp-tool-guardrails.md",
    DOCS / "security" / "prompt-injection.md",
    DOCS / "security" / "prompt-injection-regression-corpus.md",
    DOCS / "security" / "prompt-like-detector.md",
    DOCS / "security" / "rag-context-boundaries.md",
]

PRODUCTIZED_DOCS = POLICY_DOCS + SECURITY_DOCS
LEGACY_MARKERS = [
    re.compile(r"\bpatch\b", re.IGNORECASE),
    re.compile(r"\b(?:46A|46B|55A|55B|55C|55D|70A|70B|70C|70D)\b"),
    re.compile(r"\bdev[- ]?journal\b", re.IGNORECASE),
    re.compile(r"\bdevelopment diary\b", re.IGNORECASE),
]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _markdown_links(content: str) -> list[str]:
    return re.findall(r"\[[^\]]+\]\(([^)]+)\)", content)


def test_policy_and_security_docs_are_product_facing() -> None:
    for path in PRODUCTIZED_DOCS:
        assert path.exists(), path
        content = _read(path)
        for marker in LEGACY_MARKERS:
            assert marker.search(content) is None, f"{path} contains {marker.pattern}"


def test_policy_docs_keep_real_api_surfaces_and_schemas() -> None:
    expected_fragments = {
        "apply-policy-risk-levels.md": [
            "skeinrank.apply_policy.v1",
            "POST /v1/governance/profiles/{profile_name}/suggestions",
            "POST /v1/tools/validate-alias",
            "batch_approve_allowed",
            "review_required",
            "admin_or_reject",
            "auto_apply_allowed` is always `false",
        ],
        "role-boundaries.md": [
            "GET /v1/governance/role-boundaries",
            "skeinrank.role_boundaries.v1",
            "contributor",
            "moderator",
            "admin",
            "agent:tools:validate",
            "agent:tools:suggest",
        ],
        "token-rotation-scoped-agent-credentials.md": [
            "GET /v1/auth/scoped-agent-credentials",
            "skeinrank.scoped_agent_credentials.v1",
            "POST /v1/auth/service-accounts/{account_name}/tokens/{token_id}/rotate",
            "agent-proposal-writer",
            "agent:tools:validate",
            "agent:tools:suggest",
        ],
        "profile-isolation-checks.md": [
            "GET /v1/governance/isolation-checks",
            "skeinrank.profile_isolation.v1",
            "binding_id",
            "profile_name",
            "degraded",
            "Elasticsearch/OpenSearch bindings",
        ],
    }

    for path in POLICY_DOCS:
        content = _read(path)
        for fragment in expected_fragments[path.name]:
            assert fragment in content, f"{path} missing {fragment!r}"


def test_deployment_security_doc_uses_product_runbook_language() -> None:
    content = _read(DOCS / "deployment" / "security.md")

    for fragment in (
        "Production security profile",
        "make prod-env-check",
        "SKEINRANK_GOVERNANCE_API_AUTH_ENABLED=true",
        "SKEINRANK_GOVERNANCE_API_PRODUCTION_SECURITY_ENABLED=true",
        "prompt-injection.md",
        "agent-tool-safety.md",
        "production environment preflight validator",
        "Bump image versions intentionally after checking compatibility",
    ):
        assert fragment in content


def test_policy_security_markdown_links_resolve() -> None:
    for path in PRODUCTIZED_DOCS:
        content = _read(path)
        for href in _markdown_links(content):
            if href.startswith(("http://", "https://", "mailto:", "#")):
                continue
            target = href.split("#", 1)[0]
            if not target:
                continue
            resolved = (path.parent / target).resolve()
            assert resolved.exists(), f"{path} links to missing file {href}"
