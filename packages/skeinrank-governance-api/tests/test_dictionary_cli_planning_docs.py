from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
DOC = REPO_ROOT / "docs/guides/dictionary-cli-planning.md"
DOCS_README = REPO_ROOT / "docs/README.md"
ROOT_README = REPO_ROOT / "README.md"
GOVERNANCE_API_README = REPO_ROOT / "packages/skeinrank-governance-api/README.md"
MIGRATION_TOOL = (
    REPO_ROOT
    / "packages/skeinrank-governance-api/skeinrank_governance_api/migration_tool.py"
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_dictionary_cli_planning_docs_are_discoverable() -> None:
    assert DOC.exists()
    assert "docs/guides/dictionary-cli-planning.md" in _read(ROOT_README)
    assert "guides/dictionary-cli-planning.md" in _read(DOCS_README)
    assert "docs/guides/dictionary-cli-planning.md" in _read(GOVERNANCE_API_README)


def test_dictionary_cli_planning_guide_documents_existing_commands() -> None:
    doc = _read(DOC)
    tool = _read(MIGRATION_TOOL)

    expected = (
        "skeinrank-migrate lint FILE",
        "skeinrank-migrate validate FILE",
        "skeinrank-migrate plan FILE",
        "skeinrank-migrate apply FILE --plan-output PLAN.json",
        "skeinrank.dictionary_lint.v1",
        "skeinrank.dictionary_apply_plan.v1",
        "safe_to_apply",
        "server_state_checked",
        "no state was written",
    )
    for fragment in expected:
        assert fragment in doc

    for command in ('"lint"', '"plan"', '"apply"'):
        assert command in tool
    assert "--plan-output" in tool
    assert "skeinrank-cli lint" not in doc
    assert "skeinrank-cli apply" not in doc
