from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def test_backup_restore_runbook_documents_safe_cli_workflow() -> None:
    guide = _read("docs/deployment/backup-restore.md")

    expected_fragments = (
        "python -m skeinrank_governance_api.backup_restore export",
        "python -m skeinrank_governance_api.backup_restore inspect",
        "python -m skeinrank_governance_api.backup_restore restore",
        "--dry-run",
        "--replace",
        "--yes",
        "python -m skeinrank_governance_api.migrations check",
        "python -m skeinrank_governance_api.troubleshooting report --strict",
        "pg_dump",
        "restore drill",
    )
    for fragment in expected_fragments:
        assert fragment in guide


def test_backup_restore_docs_are_linked_from_primary_docs() -> None:
    root_readme = _read("README.md")
    docs_readme = _read("docs/README.md")
    observability = _read("docs/deployment/observability.md")
    package_readme = _read("packages/skeinrank-governance-api/README.md")

    for content in (root_readme, docs_readme, observability, package_readme):
        assert (
            "docs/deployment/backup-restore.md" in content
            or "deployment/backup-restore.md" in content
        )

    assert "skeinrank_governance_api.backup_restore" in package_readme
