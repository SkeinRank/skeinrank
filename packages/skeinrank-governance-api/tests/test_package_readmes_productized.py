from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
PACKAGE_READMES = tuple(sorted((REPO_ROOT / "packages").glob("*/README.md")))
GOVERNANCE_README = REPO_ROOT / "packages/skeinrank-governance/README.md"
UI_README = REPO_ROOT / "packages/skeinrank-ui/README.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_package_readmes_are_product_facing() -> None:
    assert PACKAGE_READMES
    forbidden_patterns = (
        r"\b[Pp]atch(?:es)?\b",
        r"\bdev[- ]?journal\b",
        r"\bdevelopment diary\b",
        r"\bfirst package skeleton\b",
        r"\bfirst frontend layer\b",
        r"\blegacy/dev\b",
        r"\bfollow-up patches\b",
        r"\blater platform patches\b",
        r"\bMVP\b",
    )

    for path in PACKAGE_READMES:
        content = _read(path)
        for pattern in forbidden_patterns:
            assert re.search(pattern, content) is None, f"{path}: {pattern}"


def test_governance_readme_documents_stable_package_surfaces() -> None:
    content = _read(GOVERNANCE_README)

    required_sections = (
        "## Role in the architecture",
        "## Database setup",
        "## Core schema surfaces",
        "## Integrity rules",
        "## Admin CLI",
        "## Stop lists",
        "## Elasticsearch bindings and enrichment jobs",
        "## Evidence snapshots",
        "## Term tags and conflict review",
        "## Agent run tracking",
    )
    for section in required_sections:
        assert section in content

    required_fragments = (
        "poetry run alembic upgrade head",
        "poetry run skeinrank-admin db init",
        "poetry run skeinrank-admin profile create default_it",
        "poetry run skeinrank-validate-profile /tmp/default_it.json",
        "elasticsearch_enrichment_jobs",
        "governance_binding_policies",
        "agent_proposal_attempts",
        "reindex_alias_swap",
    )
    for fragment in required_fragments:
        assert fragment in content


def test_ui_readme_documents_current_console_surfaces() -> None:
    content = _read(UI_README)

    required_sections = (
        "## Product surfaces",
        "## Current capabilities",
        "## Review-first proposal workflow",
        "## API Access",
        "## Elasticsearch binding dry-run",
        "## Elasticsearch enrichment jobs",
        "## Rollout metadata and rollback action",
        "## Search Playground snapshot compare",
        "## Schema & Snapshots tree",
        "## Read-only legacy/admin cockpit lockdown",
        "## Checks",
    )
    for section in required_sections:
        assert section in content

    required_fragments = (
        "npm run dev",
        "VITE_SKEINRANK_GOVERNANCE_API_URL",
        "Playground",
        "AI Inbox",
        "Schema & Snapshots",
        "GET /v1/ops/alerts/report",
        "POST /v1/governance/elasticsearch/bindings/{binding_id}/jobs",
        "POST /v1/query/plan",
        "VITE_SKEINRANK_ENABLE_LEGACY_WRITE_TOOLS=true npm run dev",
    )
    for fragment in required_fragments:
        assert fragment in content
