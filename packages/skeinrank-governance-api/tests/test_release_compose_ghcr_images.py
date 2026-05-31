from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
COMPOSE = REPO_ROOT / "docker-compose.yml"
ENV_EXAMPLE = REPO_ROOT / ".env.example"
RELEASE_DOC = REPO_ROOT / "docs" / "deployment" / "release-compose.md"
DOCKER_COMPOSE_DOC = REPO_ROOT / "docs" / "deployment" / "docker-compose.md"
DOCKER_IMAGES_DOC = REPO_ROOT / "docs" / "deployment" / "docker-images.md"
ROOT_README = REPO_ROOT / "README.md"
DOCS_README = REPO_ROOT / "docs" / "README.md"
DOCKER_README = REPO_ROOT / "deploy" / "docker" / "README.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _service_block(content: str, service_name: str) -> str:
    pattern = rf"\n  {re.escape(service_name)}:\n(?P<body>(?:    .+\n|\n)+?)(?=\n  [A-Za-z0-9_-]+:|\nvolumes:|\Z)"
    match = re.search(pattern, "\n" + content)
    assert match is not None, service_name
    return match.group("body")


def test_release_compose_uses_ghcr_images_without_local_builds() -> None:
    content = _read(COMPOSE)

    assert "name: ${COMPOSE_PROJECT_NAME:-skeinrank}" in content

    expected_images = {
        "governance-migrate": "image: ghcr.io/skeinrank/skeinrank-governance-api:${SKEINRANK_IMAGE_TAG:-v0.10.0-beta.1}",
        "governance-api": "image: ghcr.io/skeinrank/skeinrank-governance-api:${SKEINRANK_IMAGE_TAG:-v0.10.0-beta.1}",
        "governance-worker": "image: ghcr.io/skeinrank/skeinrank-governance-worker:${SKEINRANK_IMAGE_TAG:-v0.10.0-beta.1}",
        "ui": "image: ghcr.io/skeinrank/skeinrank-ui:${SKEINRANK_IMAGE_TAG:-v0.10.0-beta.1}",
    }
    for service_name, image_line in expected_images.items():
        block = _service_block(content, service_name)
        assert image_line in block
        assert "build:" not in block

    assert "image: postgres:16.4-alpine" in _service_block(content, "postgres")
    assert "image: rabbitmq:3.13.7-management" in _service_block(content, "rabbitmq")
    assert (
        "image: docker.elastic.co/elasticsearch/elasticsearch:8.12.2"
        in _service_block(content, "elasticsearch")
    )
    assert "skeinrank-governance-api:dev" not in content
    assert "skeinrank-governance-api:prod" not in content
    assert "dockerfile:" not in content


def test_release_compose_preserves_runtime_commands_and_dependencies() -> None:
    content = _read(COMPOSE)

    migrate = _service_block(content, "governance-migrate")
    api = _service_block(content, "governance-api")
    worker = _service_block(content, "governance-worker")
    ui = _service_block(content, "ui")

    assert (
        'command: ["python", "-m", "skeinrank_governance_api.migrations", "upgrade", "head"]'
        in migrate
    )
    assert (
        'command: ["skeinrank-governance-api", "--host", "0.0.0.0", "--port", "8010"]'
        in api
    )
    assert '"skeinrank-governance-worker",' in worker
    assert '"--queues",' in worker
    assert (
        '"${SKEINRANK_GOVERNANCE_API_CELERY_TASK_QUEUE:-skeinrank.enrichment}",'
        in worker
    )
    assert "governance-migrate:" in api
    assert "condition: service_completed_successfully" in api
    assert "elasticsearch:" in api
    assert "condition: service_healthy" in api
    assert "governance-api:" in ui
    assert '"127.0.0.1:${GOVERNANCE_API_PORT:-8010}:8010"' in api
    assert '"127.0.0.1:${UI_PORT:-5173}:5173"' in ui


def test_release_env_example_selects_tag_and_local_public_beta_defaults() -> None:
    content = _read(ENV_EXAMPLE)

    expected = (
        "COMPOSE_PROJECT_NAME=skeinrank",
        "SKEINRANK_IMAGE_TAG=v0.10.0-beta.1",
        "GOVERNANCE_API_PORT=8010",
        "UI_PORT=5173",
        "POSTGRES_PORT=15432",
        "ELASTICSEARCH_PORT=19200",
        "RABBITMQ_MANAGEMENT_PORT=15672",
        "SKEINRANK_ENV=development",
        "SKEINRANK_GOVERNANCE_API_ENV=development",
        "SKEINRANK_GOVERNANCE_API_AUTH_ENABLED=true",
        "SKEINRANK_GOVERNANCE_API_ADMIN_USERNAME=admin",
        "SKEINRANK_GOVERNANCE_API_ADMIN_PASSWORD=change-me",
        "SKEINRANK_GOVERNANCE_API_ELASTICSEARCH_URL=http://elasticsearch:9200",
        "VITE_SKEINRANK_GOVERNANCE_API_URL=http://127.0.0.1:8010",
    )
    for fragment in expected:
        assert fragment in content

    assert "!.env.example" in _read(REPO_ROOT / ".gitignore")
    assert "!.env.example" in _read(REPO_ROOT / ".dockerignore")


def test_release_compose_docs_and_indexes_are_discoverable() -> None:
    release_doc = _read(RELEASE_DOC)
    docker_compose_doc = _read(DOCKER_COMPOSE_DOC)
    docker_images_doc = _read(DOCKER_IMAGES_DOC)
    root_readme = _read(ROOT_README)
    docs_readme = _read(DOCS_README)
    docker_readme = _read(DOCKER_README)

    expected_release_fragments = (
        "Release Compose with GHCR images",
        "cp .env.example .env",
        "docker compose up -d",
        "ghcr.io/skeinrank/skeinrank-governance-api:${SKEINRANK_IMAGE_TAG:-v0.10.0-beta.1}",
        "ghcr.io/skeinrank/skeinrank-governance-worker:${SKEINRANK_IMAGE_TAG:-v0.10.0-beta.1}",
        "ghcr.io/skeinrank/skeinrank-ui:${SKEINRANK_IMAGE_TAG:-v0.10.0-beta.1}",
        "make demo-reset",
        "docker-compose.prod.yml",
    )
    for fragment in expected_release_fragments:
        assert fragment in release_doc

    assert "release-compose.md" in docker_compose_doc
    assert "release-compose.md" in docker_images_doc
    assert "docs/deployment/release-compose.md" in root_readme
    assert "docker-compose.yml" in root_readme
    assert "deployment/release-compose.md" in docs_readme
    assert "docs/deployment/release-compose.md" in docker_readme
