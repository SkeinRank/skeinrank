from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
README = REPO_ROOT / "packages/skeinrank-governance-api/README.md"


def _read() -> str:
    return README.read_text(encoding="utf-8")


def test_governance_api_readme_is_product_documentation() -> None:
    content = _read()

    forbidden_fragments = (
        "Patch",
        "patch-era",
        "dev diary",
        "development diary",
        "adds `",
        "adds a ",
        "introduced",
    )
    for fragment in forbidden_fragments:
        assert fragment not in content

    required_sections = (
        "## Role in the architecture",
        "## Start locally",
        "## Auth, users, and roles",
        "## API surface",
        "## Dictionary import, validation, and export",
        "## Migration CLI and Terminology-as-Code",
        "## Runtime routing",
        "## MCP and agent integration",
        "## Benchmarks and dry-run evaluation",
        "## Operations and deployment",
        "## Security and policy docs",
    )
    for section in required_sections:
        assert section in content


def test_governance_api_readme_links_only_to_existing_repository_files() -> None:
    content = _read()
    links = re.findall(r"\[[^\]]+\]\((\.\./\.\./[^)#]+)\)", content)

    assert links
    for link in links:
        target = (README.parent / link).resolve()
        assert target.exists(), link
        assert REPO_ROOT.resolve() in target.parents or target == REPO_ROOT.resolve()


def test_governance_api_readme_documents_current_public_surfaces() -> None:
    content = _read()

    required_fragments = (
        "poetry run skeinrank-governance-api --reload",
        "POST /v1/console/dictionary/validate",
        "POST /v1/headless/dictionaries/apply",
        "POST /v1/text/canonicalize",
        "POST /v1/query/route-plan",
        "skeinrank-migrate lint",
        "skeinrank-migrate snapshot-export",
        "skeinrank.runtime_snapshot_artifact.v1",
        "skeinrank-mcp",
        "--print-tool-schemas",
        "--discover-candidates",
        "--print-model-provider-plan",
        "skeinrank-governance-benchmark-stack",
        "skeinrank-governance-retrieval-eval",
        "skeinrank-governance-retrieval-compare",
        "skeinrank-governance-synthetic-smoke",
        "skeinrank-governance-benchmark-performance",
        "skeinrank-governance-pilot",
        "skeinrank-governance-support-bundle",
        "skeinrank-governance-backup-drill",
        "skeinrank-governance-alerting",
        "deploy/docker/scripts/prod-smoke-test.sh",
        "docs/deployment/production-compose.md",
        "docs/deployment/backup-restore.md",
        "docs/deployment/release-checklist.md",
        "docs/security/prompt-injection.md",
    )
    for fragment in required_fragments:
        assert fragment in content
