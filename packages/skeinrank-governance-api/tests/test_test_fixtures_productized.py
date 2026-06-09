from __future__ import annotations

import ast
import re
from pathlib import Path

from public_docs_guard import REPO_ROOT

AGENT_VERSION_MILESTONE = re.compile(
    r"[\"']?agent_version[\"']?\s*(?:=|:)\s*[\"']\d{2}[A-Z][\"']"
)
INTERNAL_TEST_NAME = re.compile(r"^test_\d{2}[A-Z](?:_|$)")
TEST_ROOTS = (
    REPO_ROOT / "packages" / "skeinrank-core" / "tests",
    REPO_ROOT / "packages" / "skeinrank-governance" / "tests",
    REPO_ROOT / "packages" / "skeinrank-governance-api" / "tests",
    REPO_ROOT / "packages" / "skeinrank-server" / "tests",
)
SOURCE_FILES_WITH_AGENT_VERSION_FIXTURES = (
    REPO_ROOT
    / "packages"
    / "skeinrank-governance-api"
    / "skeinrank_governance_api"
    / "benchmark.py",
)


def _python_files(paths: tuple[Path, ...]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        if path.is_file():
            files.append(path)
        elif path.exists():
            files.extend(path.rglob("*.py"))
    return sorted(files)


def test_agent_version_fixtures_use_product_names() -> None:
    violations: list[str] = []
    for path in _python_files(TEST_ROOTS + SOURCE_FILES_WITH_AGENT_VERSION_FIXTURES):
        content = path.read_text(encoding="utf-8")
        if AGENT_VERSION_MILESTONE.search(content):
            violations.append(str(path.relative_to(REPO_ROOT)))

    assert not violations


def test_test_functions_do_not_use_internal_milestone_names() -> None:
    violations: list[str] = []
    for path in _python_files(TEST_ROOTS):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(
                node, (ast.FunctionDef, ast.AsyncFunctionDef)
            ) and INTERNAL_TEST_NAME.search(node.name):
                violations.append(f"{path.relative_to(REPO_ROOT)}::{node.name}")

    assert not violations
