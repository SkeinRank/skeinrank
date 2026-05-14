from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def test_dev_compose_declares_expected_services() -> None:
    compose = _read("docker-compose.dev.yml")

    for service_name in (
        "postgres",
        "rabbitmq",
        "elasticsearch",
        "governance-migrate",
        "governance-api",
        "governance-worker",
        "ui",
    ):
        assert f"  {service_name}:" in compose

    assert "service_completed_successfully" in compose
    assert "service_healthy" in compose
    assert "127.0.0.1:${GOVERNANCE_API_PORT:-8010}:8010" in compose
    assert "127.0.0.1:${UI_PORT:-5173}:5173" in compose


def test_dev_compose_wires_governance_runtime_environment() -> None:
    compose = _read("docker-compose.dev.yml")

    expected_env_names = (
        "SKEINRANK_GOVERNANCE_API_DATABASE_URL",
        "SKEINRANK_GOVERNANCE_API_ELASTICSEARCH_URL",
        "SKEINRANK_GOVERNANCE_API_AUTH_ENABLED",
        "SKEINRANK_GOVERNANCE_API_BOOTSTRAP_ADMIN",
        "SKEINRANK_GOVERNANCE_API_CELERY_BROKER_URL",
        "SKEINRANK_GOVERNANCE_API_CELERY_TASK_QUEUE",
        "SKEINRANK_GOVERNANCE_API_ENRICHMENT_JOBS_BACKEND",
        "VITE_SKEINRANK_GOVERNANCE_API_URL",
    )
    for env_name in expected_env_names:
        assert env_name in compose

    assert "postgresql+psycopg://" in compose
    assert "http://elasticsearch:9200" in compose
    assert "amqp://${RABBITMQ_DEFAULT_USER" in compose


def test_dev_env_example_contains_required_settings() -> None:
    env_example = _read(".env.example")

    required_settings = (
        "GOVERNANCE_API_PORT=8010",
        "UI_PORT=5173",
        "POSTGRES_PASSWORD=",
        "RABBITMQ_DEFAULT_USER=",
        "RABBITMQ_DEFAULT_PASS=",
        "SKEINRANK_GOVERNANCE_API_AUTH_ENABLED=true",
        "SKEINRANK_GOVERNANCE_API_ADMIN_USERNAME=admin",
        "SKEINRANK_GOVERNANCE_API_ADMIN_PASSWORD=change-me",
        "SKEINRANK_GOVERNANCE_API_ENRICHMENT_JOBS_BACKEND=celery",
        "VITE_SKEINRANK_GOVERNANCE_API_URL=http://127.0.0.1:8010",
    )
    for setting in required_settings:
        assert setting in env_example


def test_deploy_docker_readme_documents_bootstrap_flow() -> None:
    readme = _read("deploy/docker/README.md")

    assert "docker compose -f docker-compose.dev.yml up --build" in readme
    assert "governance-migrate" in readme
    assert "http://127.0.0.1:5173" in readme
    assert "http://127.0.0.1:8010" in readme
    assert "examples/migration/console_dictionary.example.json" in readme
    assert "docker compose -f docker-compose.dev.yml down -v" in readme
