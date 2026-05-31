from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
CHART = REPO_ROOT / "charts" / "skeinrank"
TEMPLATES = CHART / "templates"
PROD_VALUES = CHART / "values-production.example.yaml"
HELM_PRODUCTION_DOC = REPO_ROOT / "docs" / "deployment" / "helm-production.md"
HELM_DOC = REPO_ROOT / "docs" / "deployment" / "helm-chart.md"
HELM_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "helm-chart.yml"
ROOT_README = REPO_ROOT / "README.md"
DOCS_README = REPO_ROOT / "docs" / "README.md"
DOCKER_IMAGES_DOC = REPO_ROOT / "docs" / "deployment" / "docker-images.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_helm_values_include_production_example_and_runtime_safety_knobs() -> None:
    values = _read(CHART / "values.yaml")
    prod_values = _read(PROD_VALUES)

    assert PROD_VALUES.exists()
    assert "ingress:" in values
    assert "ui:" in values
    assert "api:" in values
    assert "podDisruptionBudgets:" in values
    assert "governanceApi:" in values
    assert "governanceWorker:" in values
    assert "resources:" in values

    for fragment in (
        "existingSecret: skeinrank-runtime-secrets",
        'corsOrigins: "https://skeinrank.example.com"',
        'uiGovernanceApiUrl: "https://api.skeinrank.example.com"',
        'elasticsearchUrl: "https://opensearch.example.com:9200"',
        "replicaCount: 2",
        "requests:",
        "limits:",
        "ingress:",
        "className: nginx",
        "host: skeinrank.example.com",
        "host: api.skeinrank.example.com",
        "podDisruptionBudgets:",
        "minAvailable: 1",
    ):
        assert fragment in prod_values


def test_helm_templates_render_optional_ingress_and_pod_disruption_budgets() -> None:
    ingress = _read(TEMPLATES / "ingress.yaml")
    pdb = _read(TEMPLATES / "poddisruptionbudgets.yaml")

    assert "networking.k8s.io/v1" in ingress
    assert "kind: Ingress" in ingress
    assert ".Values.ingress.enabled" in ingress
    assert ".Values.ingress.ui.enabled" in ingress
    assert ".Values.ingress.api.enabled" in ingress
    assert "skeinrank.fullname" in ingress
    assert "-ui" in ingress
    assert "-governance-api" in ingress
    assert "tlsSecretName" in ingress

    assert "policy/v1" in pdb
    assert "kind: PodDisruptionBudget" in pdb
    assert ".Values.podDisruptionBudgets.governanceApi.enabled" in pdb
    assert ".Values.podDisruptionBudgets.governanceWorker.enabled" in pdb
    assert ".Values.podDisruptionBudgets.ui.enabled" in pdb
    assert "app.kubernetes.io/component: governance-api" in pdb
    assert "app.kubernetes.io/component: governance-worker" in pdb
    assert "app.kubernetes.io/component: ui" in pdb


def test_helm_workflow_renders_production_values_example() -> None:
    workflow = _read(HELM_WORKFLOW)

    assert "charts/skeinrank/values-production.example.yaml" in workflow
    assert "docs/deployment/helm-production.md" in workflow
    assert "tests/test_helm_values_production_notes.py" in workflow
    assert "Render production values example" in workflow
    assert "-f charts/skeinrank/values-production.example.yaml" in workflow
    assert "kind: Ingress" in workflow
    assert "kind: PodDisruptionBudget" in workflow
    assert "kind create cluster" not in workflow
    assert "k3d cluster create" not in workflow


def test_helm_production_docs_are_discoverable() -> None:
    helm_doc = _read(HELM_DOC)
    production_doc = _read(HELM_PRODUCTION_DOC)
    readme = _read(ROOT_README)
    docs_readme = _read(DOCS_README)
    docker_images_doc = _read(DOCKER_IMAGES_DOC)

    for fragment in (
        "Helm production values guide",
        "charts/skeinrank/values-production.example.yaml",
        "secrets.existingSecret",
        "SKEINRANK_GOVERNANCE_API_DATABASE_URL",
        "External dependencies",
        "Ingress",
        "Resource requests and limits",
        "Pod disruption budgets",
        "Preflight checklist",
        "optional kind smoke test is available",
    ):
        assert fragment in production_doc

    assert "values-production.example.yaml" in helm_doc
    assert "helm-production.md" in helm_doc
    assert "ingress.enabled" in helm_doc
    assert "podDisruptionBudgets.*.enabled" in helm_doc
    assert "docs/deployment/helm-production.md" in readme
    assert "deployment/helm-production.md" in docs_readme
    assert "helm-production.md" in docker_images_doc
