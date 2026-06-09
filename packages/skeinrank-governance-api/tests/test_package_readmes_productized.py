from __future__ import annotations

from public_docs_guard import REPO_ROOT, assert_productized_repo_files, read_repo_file

PACKAGE_READMES = tuple(sorted((REPO_ROOT / "packages").glob("*/README.md")))
GOVERNANCE_README = "packages/skeinrank-governance/README.md"
UI_README = "packages/skeinrank-ui/README.md"


def test_package_readmes_are_product_facing() -> None:
    assert PACKAGE_READMES
    assert_productized_repo_files(
        list(PACKAGE_READMES),
        extra_forbidden=(
            "first package skeleton",
            "first frontend layer",
            "legacy/dev",
            "later platform patches",
            "MVP",
        ),
    )


def test_governance_readme_documents_stable_package_surfaces() -> None:
    content = read_repo_file(GOVERNANCE_README)

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
    content = read_repo_file(UI_README)

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
