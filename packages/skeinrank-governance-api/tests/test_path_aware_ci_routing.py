from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
CI_ROUTING_DOC = REPO_ROOT / "docs" / "deployment" / "ci-routing.md"
ROOT_README = REPO_ROOT / "README.md"
DOCS_README = REPO_ROOT / "docs" / "README.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_ci_workflow_keeps_required_checks_and_adds_routing_gate() -> None:
    workflow = _read(CI_WORKFLOW)

    for fragment in (
        "name: ci",
        "pull_request:",
        "push:",
        "branches: [main]",
        "changes:",
        "name: route changed files",
        "fetch-depth: 0",
        "Classify changed files",
        "ci-required:",
        "name: ci-required",
        "Check routed CI jobs",
    ):
        assert fragment in workflow

    # Existing required-check names stay available for branch rules.
    assert "lint:" in workflow
    assert "test:" in workflow
    assert "ui:" in workflow
    assert "matrix:" in workflow
    assert "packages/skeinrank-core" in workflow
    assert "packages/skeinrank-server" in workflow
    assert "packages/skeinrank-provider-elasticsearch" in workflow
    assert "packages/skeinrank-governance" in workflow
    assert "packages/skeinrank-governance-api" in workflow


def test_ci_routing_classifies_expected_repository_areas() -> None:
    workflow = _read(CI_WORKFLOW)

    for output_name in (
        "force_all",
        "python_any",
        "docs_contracts",
        "core",
        "server",
        "provider_elasticsearch",
        "governance",
        "governance_api",
        "ui",
    ):
        assert (
            f"{output_name}: ${{{{ steps.filter.outputs.{output_name} }}}}" in workflow
        )

    for path_fragment in (
        "packages/skeinrank-core/",
        "packages/skeinrank-server/",
        "packages/skeinrank-provider-elasticsearch/",
        "packages/skeinrank-governance/",
        "packages/skeinrank-governance-api/",
        "packages/skeinrank-ui/",
        "deploy/docker/ui.Dockerfile",
        "docs/",
        "deploy/",
        "charts/",
        "examples/",
        "scripts/",
        "docker-compose.yml",
        ".github/workflows/docker-publish.yml",
        ".github/workflows/helm-chart.yml",
        ".github/workflows/helm-smoke.yml",
        ".github/workflows/ci.yml",
        "ruff.toml",
    ):
        assert path_fragment in workflow


def test_package_matrix_skips_unrelated_package_installs() -> None:
    workflow = _read(CI_WORKFLOW)

    for fragment in (
        "Decide whether this package test should run",
        "run_tests=false",
        "steps.package_route.outputs.run_tests == 'true'",
        "Skip package tests",
        "No relevant changes for ${{ matrix.package }}; skipping package install and tests.",
        "DOCS_CONTRACTS_CHANGED",
        "packages/skeinrank-governance-api)",
    ):
        assert fragment in workflow

    assert "poetry install --no-interaction" in workflow
    assert "poetry run pytest -q" in workflow
    assert "npm run typecheck" in workflow
    assert "npm test -- --run" in workflow
    assert "npm run build" in workflow


def test_ci_gate_accepts_success_or_skipped_and_rejects_failures() -> None:
    workflow = _read(CI_WORKFLOW)

    for fragment in (
        "CHANGES_RESULT: ${{ needs.changes.result }}",
        "LINT_RESULT: ${{ needs.lint.result }}",
        "TEST_RESULT: ${{ needs.test.result }}",
        "UI_RESULT: ${{ needs.ui.result }}",
        "success|skipped)",
        "exit 1",
    ):
        assert fragment in workflow

    assert "paths-ignore" not in workflow
    assert "paths:" not in workflow.split("jobs:", 1)[0]


def test_ci_routing_docs_are_discoverable() -> None:
    doc = _read(CI_ROUTING_DOC)
    docs_readme = _read(DOCS_README)

    for fragment in (
        "Path-aware CI routing",
        ".github/workflows/ci.yml",
        "ci-required",
        "docs_contracts",
        "Docker image publishing is not part of normal PR CI",
        "helm-smoke.yml",
        "Branch protection recommendation",
    ):
        assert fragment in doc

    assert "deployment/ci-routing.md" in docs_readme
