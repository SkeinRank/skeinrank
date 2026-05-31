from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
CHART = REPO_ROOT / "charts" / "skeinrank"
TEMPLATES = CHART / "templates"
HELM_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "helm-chart.yml"
HELM_DOC = REPO_ROOT / "docs" / "deployment" / "helm-chart.md"
ROOT_README = REPO_ROOT / "README.md"
DOCS_README = REPO_ROOT / "docs" / "README.md"
DOCKER_IMAGES_DOC = REPO_ROOT / "docs" / "deployment" / "docker-images.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_helm_chart_alpha_has_expected_file_layout() -> None:
    expected_files = {
        CHART / "Chart.yaml",
        CHART / "values.yaml",
        TEMPLATES / "_helpers.tpl",
        TEMPLATES / "configmap.yaml",
        TEMPLATES / "secret.yaml",
        TEMPLATES / "serviceaccount.yaml",
        TEMPLATES / "governance-migration-job.yaml",
        TEMPLATES / "governance-api-deployment.yaml",
        TEMPLATES / "governance-api-service.yaml",
        TEMPLATES / "governance-worker-deployment.yaml",
        TEMPLATES / "ui-deployment.yaml",
        TEMPLATES / "ui-service.yaml",
        TEMPLATES / "NOTES.txt",
    }

    for path in expected_files:
        assert path.exists(), path


def test_helm_chart_uses_ghcr_release_images_and_external_dependencies() -> None:
    chart = _read(CHART / "Chart.yaml")
    values = _read(CHART / "values.yaml")

    assert "name: skeinrank" in chart
    assert 'appVersion: "v0.10.0-beta.1"' in chart
    assert "registry: ghcr.io" in values
    assert "namespace: skeinrank" in values
    assert "tag: v0.10.0-beta.1" in values
    assert "repository: skeinrank-governance-api" in values
    assert "repository: skeinrank-governance-worker" in values
    assert "repository: skeinrank-ui" in values
    assert (
        "It intentionally does not deploy PostgreSQL, RabbitMQ, or Elasticsearch"
        in values
    )
    assert "dependencies:" not in chart
    assert "bitnami" not in chart.lower()


def test_helm_templates_preserve_skeinrank_runtime_commands_and_secret_contract() -> (
    None
):
    configmap = _read(TEMPLATES / "configmap.yaml")
    secret = _read(TEMPLATES / "secret.yaml")
    migrate = _read(TEMPLATES / "governance-migration-job.yaml")
    api = _read(TEMPLATES / "governance-api-deployment.yaml")
    worker = _read(TEMPLATES / "governance-worker-deployment.yaml")
    ui = _read(TEMPLATES / "ui-deployment.yaml")

    for env_name in (
        "SKEINRANK_GOVERNANCE_API_ELASTICSEARCH_URL",
        "SKEINRANK_GOVERNANCE_API_AUTH_ENABLED",
        "SKEINRANK_GOVERNANCE_API_CELERY_TASK_QUEUE",
        "SKEINRANK_GOVERNANCE_API_OBSERVABILITY_ENABLED",
        "SKEINRANK_GOVERNANCE_API_REQUEST_ID_HEADER",
        "VITE_SKEINRANK_GOVERNANCE_API_URL",
    ):
        assert env_name in configmap

    for secret_key_template in (
        ".Values.secrets.keys.databaseUrl",
        ".Values.secrets.keys.adminPassword",
        ".Values.secrets.keys.celeryBrokerUrl",
        ".Values.secrets.keys.elasticsearchApiKey",
    ):
        assert secret_key_template in secret

    assert (
        'command: ["python", "-m", "skeinrank_governance_api.migrations", "upgrade", "head"]'
        in migrate
    )
    values = _read(CHART / "values.yaml")
    assert "enabled: false" in values
    assert '"helm.sh/hook": pre-install,pre-upgrade' in migrate
    assert 'command: ["skeinrank-governance-api"]' in api
    assert (
        'args: ["--host", "0.0.0.0", "--port", "{{ .Values.governanceApi.containerPort }}"]'
        in api
    )
    assert 'command: ["skeinrank-governance-worker"]' in worker
    assert '"--queues"' in worker
    assert "secretRef:" in api
    assert "configMapRef:" in api
    assert "VITE_SKEINRANK_GOVERNANCE_API_URL" in ui


def test_helm_workflow_lints_and_templates_chart_without_kind_smoke() -> None:
    workflow = _read(HELM_WORKFLOW)

    assert "name: helm-chart" in workflow
    assert "charts/**" in workflow
    assert "azure/setup-helm@v4" in workflow
    assert "helm lint charts/skeinrank" in workflow
    assert "helm template skeinrank charts/skeinrank" in workflow
    assert "kind create cluster" not in workflow
    assert "k3d cluster create" not in workflow
    assert "workflow_dispatch:" in workflow


def test_helm_docs_are_discoverable_and_state_alpha_limitations() -> None:
    helm_doc = _read(HELM_DOC)
    readme = _read(ROOT_README)
    docs_readme = _read(DOCS_README)
    docker_images_doc = _read(DOCKER_IMAGES_DOC)

    for fragment in (
        "Helm chart alpha",
        "helm lint charts/skeinrank",
        "helm template skeinrank charts/skeinrank",
        "secrets.existingSecret",
        "SKEINRANK_GOVERNANCE_API_DATABASE_URL",
        "The chart is intentionally small in this first alpha",
        "Helm hook mode is available but disabled in alpha values",
        "full kind/k3d smoke tests are planned separately",
    ):
        assert fragment in helm_doc

    assert "docs/deployment/helm-chart.md" in readme
    assert "charts/skeinrank" in readme
    assert "deployment/helm-chart.md" in docs_readme
    assert "helm-chart.md" in docker_images_doc
