from __future__ import annotations

import ast
from pathlib import Path

from public_docs_guard import (
    INTERNAL_MILESTONE_PATTERN,
    PRODUCT_DOC_FORBIDDEN_PATTERNS,
    REPO_ROOT,
)

SOURCE_ROOTS = (
    REPO_ROOT / "packages" / "skeinrank-core" / "skeinrank",
    REPO_ROOT / "packages" / "skeinrank-governance" / "skeinrank_governance",
    REPO_ROOT / "packages" / "skeinrank-governance-api" / "skeinrank_governance_api",
    REPO_ROOT / "packages" / "skeinrank-server" / "skeinrank_server",
    REPO_ROOT / "examples" / "agents" / "openrouter_alias_scout",
)
FORBIDDEN_DOCSTRING_PATTERNS = (
    *PRODUCT_DOC_FORBIDDEN_PATTERNS,
    INTERNAL_MILESTONE_PATTERN,
)


def _python_sources() -> list[Path]:
    paths: list[Path] = []
    for root in SOURCE_ROOTS:
        paths.extend(path for path in root.rglob("*.py") if "tests" not in path.parts)
    return sorted(paths)


def _docstrings(path: Path) -> list[tuple[str, int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    docs: list[tuple[str, int, str]] = []
    module_doc = ast.get_docstring(tree, clean=False)
    if module_doc:
        docs.append(("module", 1, module_doc))
    for node in ast.walk(tree):
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc:
                docs.append((node.name, node.lineno, doc))
    return docs


def test_public_docstrings_do_not_expose_internal_milestones() -> None:
    assert _python_sources()

    violations: list[str] = []
    for path in _python_sources():
        relative = path.relative_to(REPO_ROOT)
        for owner, line, docstring in _docstrings(path):
            for pattern in FORBIDDEN_DOCSTRING_PATTERNS:
                if pattern.search(docstring):
                    violations.append(f"{relative}:{line} {owner}: {pattern.pattern}")

    assert not violations
