from __future__ import annotations

import re

from public_docs_guard import assert_productized_text, read_repo_file


def _target_pattern(name: str) -> re.Pattern[str]:
    return re.compile(rf"^{re.escape(name)}(?::|\s*:)", re.MULTILINE)


def test_root_makefile_exposes_developer_check_commands() -> None:
    content = read_repo_file("Makefile")

    for target in (
        "lint",
        "format",
        "format-check",
        "check",
        "test-core",
        "test-governance-models",
        "test-governance-api",
        "test-provider-elasticsearch",
        "test-server",
        "test-ui",
        "test-agent",
        "test-scout",
        "test-migrations",
        "test-docs",
        "test-fast",
        "test-python",
        "test-all",
    ):
        assert _target_pattern(target).search(content), target


def test_root_makefile_delegates_to_real_package_paths() -> None:
    content = read_repo_file("Makefile")

    for fragment in (
        "CORE_DIR := packages/skeinrank-core",
        "GOVERNANCE_DIR := packages/skeinrank-governance",
        "GOVERNANCE_API_DIR := packages/skeinrank-governance-api",
        "PROVIDER_ELASTICSEARCH_DIR := packages/skeinrank-provider-elasticsearch",
        "SERVER_DIR := packages/skeinrank-server",
        "UI_DIR := packages/skeinrank-ui",
        "cd $(CORE_DIR) && $(POETRY) run $(PYTEST) -q",
        "cd $(GOVERNANCE_API_DIR) && $(POETRY) run $(PYTEST) -q",
        "cd $(UI_DIR) && $(NPM) run typecheck && $(NPM) test -- --run && $(NPM) run build",
        "RUFF_RUNNER ?= $(DEV_PYTHON) tools/dev/resolve_ruff.py",
        "$(RUFF_RUNNER) check .",
        "$(RUFF_RUNNER) format --check .",
    ):
        assert fragment in content


def test_development_docs_describe_root_test_commands() -> None:
    content = read_repo_file("docs/guides/development.md")

    assert_productized_text(content, source="docs/guides/development.md")
    for fragment in (
        "make test-fast",
        "make test-scout",
        "make test-migrations",
        "make test-docs",
        "make check",
        "make test-ui",
        "make test-all",
    ):
        assert fragment in content


def test_contributing_guide_points_to_developer_commands() -> None:
    content = read_repo_file("CONTRIBUTING.md")

    assert_productized_text(content, source="CONTRIBUTING.md")
    for fragment in (
        "make test-fast",
        "make check",
        "make test-scout",
        "make test-migrations",
        "make test-docs",
        "make test-ui",
    ):
        assert fragment in content


def test_ruff_resolver_is_documented_and_productized() -> None:
    resolver = read_repo_file("tools/dev/resolve_ruff.py")
    development = read_repo_file("docs/guides/development.md")
    contributing = read_repo_file("CONTRIBUTING.md")

    assert "def resolve_ruff" in resolver
    assert "def _is_usable_ruff" in resolver
    assert "--version" in resolver
    assert "RUFF" in resolver
    assert "pyenv" in resolver
    assert "--print-command" in resolver
    assert "tools/dev/resolve_ruff.py" in development
    assert 'RUFF="$HOME/.pyenv/versions/3.11.9/bin/ruff" make check' in development
    assert "tools/dev/resolve_ruff.py" in contributing
