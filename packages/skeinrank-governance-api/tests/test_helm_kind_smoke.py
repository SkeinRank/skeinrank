from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
CHART = REPO_ROOT / "charts" / "skeinrank"
SMOKE_VALUES = CHART / "values-kind-smoke.yaml"
SMOKE_SCRIPT = REPO_ROOT / "scripts" / "helm" / "smoke_kind.sh"
SMOKE_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "helm-smoke.yml"
SMOKE_DOC = REPO_ROOT / "docs" / "deployment" / "helm-smoke-test.md"
HELM_DOC = REPO_ROOT / "docs" / "deployment" / "helm-chart.md"
HELM_PRODUCTION_DOC = REPO_ROOT / "docs" / "deployment" / "helm-production.md"
ROOT_README = REPO_ROOT / "README.md"
DOCS_README = REPO_ROOT / "docs" / "README.md"
DOCKER_IMAGES_DOC = REPO_ROOT / "docs" / "deployment" / "docker-images.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_kind_smoke_files_exist_and_are_executable() -> None:
    assert SMOKE_VALUES.exists()
    assert SMOKE_SCRIPT.exists()
    assert SMOKE_WORKFLOW.exists()
    assert SMOKE_DOC.exists()
    assert SMOKE_SCRIPT.stat().st_mode & 0o111, "smoke_kind.sh must be executable"


def test_kind_smoke_values_do_not_start_runtime_pods_or_jobs() -> None:
    values = _read(SMOKE_VALUES)

    for fragment in (
        "replicaCount: 0",
        "migrations:",
        "enabled: false",
        "ingress:",
        "podDisruptionBudgets:",
        "tag: v0.10.0-beta.1",
        "authEnabled: false",
        "bootstrapAdmin: false",
    ):
        assert fragment in values

    assert "existingSecret:" not in values
    assert "replicaCount: 1" not in values


def test_kind_smoke_script_uses_real_helm_kubectl_kind_commands_safely() -> None:
    script = _read(SMOKE_SCRIPT)

    for command in ("docker", "kind", "kubectl", "helm"):
        assert f"require_command {command}" in script

    for fragment in (
        "set -euo pipefail",
        "KIND_CLUSTER_NAME",
        "SKEINRANK_IMAGE_TAG",
        "SKEINRANK_KEEP_KIND_CLUSTER",
        "kind create cluster --name",
        "kubectl create namespace",
        'helm lint "$CHART_DIR"',
        'helm template "$RELEASE_NAME" "$CHART_DIR"',
        'helm upgrade --install "$RELEASE_NAME" "$CHART_DIR"',
        "--wait",
        'kubectl -n "$NAMESPACE" get deploy,svc,configmap,secret',
        'kubectl -n "$NAMESPACE" get deployment "${RELEASE_NAME}-governance-api"',
        'kubectl -n "$NAMESPACE" get service "${RELEASE_NAME}-ui"',
        'kind delete cluster --name "$CLUSTER_NAME"',
    ):
        assert fragment in script

    assert "helm install" not in script
    assert "docker compose" not in script
    assert "port-forward" not in script


def test_helm_smoke_workflow_is_manual_and_not_required_by_default() -> None:
    workflow = _read(SMOKE_WORKFLOW)

    assert "name: helm-smoke" in workflow
    assert "workflow_dispatch:" in workflow
    assert "image_tag:" in workflow
    assert 'default: "v0.10.0-beta.1"' in workflow
    assert "pull_request:" not in workflow
    assert "push:" not in workflow
    assert "azure/setup-helm@v4" in workflow
    assert "azure/setup-kubectl@v4" in workflow
    assert "kind.sigs.k8s.io/dl/v0.24.0/kind-linux-amd64" in workflow
    assert "bash scripts/helm/smoke_kind.sh" in workflow
    assert "SKEINRANK_IMAGE_TAG: ${{ inputs.image_tag }}" in workflow


def test_helm_smoke_docs_are_discoverable() -> None:
    smoke_doc = _read(SMOKE_DOC)
    helm_doc = _read(HELM_DOC)
    production_doc = _read(HELM_PRODUCTION_DOC)
    readme = _read(ROOT_README)
    docs_readme = _read(DOCS_README)
    docker_images_doc = _read(DOCKER_IMAGES_DOC)

    for fragment in (
        "Optional kind Helm smoke test",
        "bash scripts/helm/smoke_kind.sh",
        "charts/skeinrank/values-kind-smoke.yaml",
        "SKEINRANK_IMAGE_TAG=v0.10.0-beta.1",
        "SKEINRANK_KEEP_KIND_CLUSTER=1",
        "GitHub → Actions → helm-smoke → Run workflow",
        "The workflow is not a required branch-protection check",
        "k3d alternative",
    ):
        assert fragment in smoke_doc

    assert "helm-smoke-test.md" in helm_doc
    assert "values-kind-smoke.yaml" in helm_doc
    assert "helm-smoke-test.md" in production_doc
    assert "docs/deployment/helm-smoke-test.md" in readme
    assert "deployment/helm-smoke-test.md" in docs_readme
    assert "helm-smoke-test.md" in docker_images_doc
