from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
RUNBOOK = REPO_ROOT / "docs/deployment/gitops-delivery-runbook.md"
DOCS_README = REPO_ROOT / "docs/README.md"
ROOT_README = REPO_ROOT / "README.md"
GOVERNANCE_API_README = REPO_ROOT / "packages/skeinrank-governance-api/README.md"
TERMINOLOGY_AS_CODE_DOC = REPO_ROOT / "docs/guides/terminology-as-code.md"
CLI_PLANNING_DOC = REPO_ROOT / "docs/guides/dictionary-cli-planning.md"
EXAMPLES_DIR = REPO_ROOT / "examples/gitops-delivery"
GITLAB_EXAMPLE = EXAMPLES_DIR / "gitlab-ci.dictionary-delivery.yml"
ARGOCD_EXAMPLE = EXAMPLES_DIR / "argocd-runtime-artifact.application.yaml"
FLUX_SOURCE_EXAMPLE = EXAMPLES_DIR / "flux-gitrepository.yaml"
FLUX_KUSTOMIZATION_EXAMPLE = EXAMPLES_DIR / "flux-runtime-artifact.kustomization.yaml"
RUNTIME_KUSTOMIZATION = EXAMPLES_DIR / "runtime-artifact/kustomization.yaml"
RUNTIME_DEPLOYMENT = EXAMPLES_DIR / "runtime-artifact/deployment.yaml"
RUNTIME_SNAPSHOT = EXAMPLES_DIR / "runtime-artifact/runtime-snapshot.example.json"
MIGRATION_TOOL = (
    REPO_ROOT
    / "packages/skeinrank-governance-api/skeinrank_governance_api/migration_tool.py"
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_gitops_delivery_runbook_is_discoverable() -> None:
    assert RUNBOOK.exists()
    assert (EXAMPLES_DIR / "README.md").exists()

    docs_index = _read(DOCS_README)
    assert "deployment/gitops-delivery-runbook.md" in docs_index
    assert "../examples/gitops-delivery" in docs_index
    assert "docs/deployment/gitops-delivery-runbook.md" in _read(GOVERNANCE_API_README)
    assert "../deployment/gitops-delivery-runbook.md" in _read(TERMINOLOGY_AS_CODE_DOC)
    assert "../deployment/gitops-delivery-runbook.md" in _read(CLI_PLANNING_DOC)


def test_gitops_delivery_runbook_documents_existing_cli_surface() -> None:
    runbook = _read(RUNBOOK)
    migration_tool = _read(MIGRATION_TOOL)

    expected_fragments = (
        "GitLab CI",
        "ArgoCD",
        "Flux",
        "SKEINRANK_CONSOLE_API_URL",
        "SKEINRANK_API_TOKEN",
        "SKEINRANK_DICTIONARY_FILE",
        "SKEINRANK_PROFILE_NAME",
        "SKEINRANK_BINDING_ID",
        "skeinrank-migrate lint",
        "skeinrank-migrate plan",
        "skeinrank-migrate apply",
        "--plan-output",
        "skeinrank-migrate export",
        "skeinrank-migrate snapshot-export",
        "skeinrank-migrate snapshot-inspect",
        "`snapshot-export` writes a binding-scoped artifact",
        "rollback is a Git revert",
    )
    for fragment in expected_fragments:
        assert fragment in runbook

    for command in ('"lint"', '"plan"', '"apply"', '"export"', '"snapshot-export"'):
        assert command in migration_tool

    forbidden_fragments = (
        "skeinrank-cli apply",
        "skeinrank-cli lint",
        "skeinrank gitops",
        "/api/v1/reload-config",
        "/v1/runtime/reload",
        "terraform apply",
    )
    for fragment in forbidden_fragments:
        assert fragment not in runbook


def test_gitops_delivery_examples_cover_gitlab_argocd_flux_and_kustomize() -> None:
    for path in (
        GITLAB_EXAMPLE,
        ARGOCD_EXAMPLE,
        FLUX_SOURCE_EXAMPLE,
        FLUX_KUSTOMIZATION_EXAMPLE,
        RUNTIME_KUSTOMIZATION,
        RUNTIME_DEPLOYMENT,
        RUNTIME_SNAPSHOT,
    ):
        assert path.exists(), path

    gitlab = _read(GITLAB_EXAMPLE)
    assert "lint_dictionary" in gitlab
    assert "plan_dictionary" in gitlab
    assert "apply_dictionary" in gitlab
    assert "export_runtime_snapshot" in gitlab
    assert "skeinrank-migrate lint" in gitlab
    assert "skeinrank-migrate plan" in gitlab
    assert "skeinrank-migrate apply" in gitlab
    assert "skeinrank-migrate export" in gitlab
    assert "skeinrank-migrate snapshot-export" in gitlab
    assert "skeinrank-migrate snapshot-inspect" in gitlab
    assert "--plan-output" in gitlab

    argocd = _read(ARGOCD_EXAMPLE)
    assert "kind: Application" in argocd
    assert "examples/gitops-delivery/runtime-artifact" in argocd

    flux_source = _read(FLUX_SOURCE_EXAMPLE)
    flux_kustomization = _read(FLUX_KUSTOMIZATION_EXAMPLE)
    assert "kind: GitRepository" in flux_source
    assert "kind: Kustomization" in flux_kustomization
    assert "./examples/gitops-delivery/runtime-artifact" in flux_kustomization

    kustomization = _read(RUNTIME_KUSTOMIZATION)
    deployment = _read(RUNTIME_DEPLOYMENT)
    snapshot = _read(RUNTIME_SNAPSHOT)
    assert "configMapGenerator" in kustomization
    assert "runtime-snapshot.json=runtime-snapshot.example.json" in kustomization
    assert "SKEINRANK_RUNTIME_SNAPSHOT_FILE" in deployment
    assert "skeinrank.runtime_snapshot_artifact.v1" in snapshot
