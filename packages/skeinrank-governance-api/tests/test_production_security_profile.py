from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def test_production_compose_declares_hardened_services() -> None:
    compose = _read("docker-compose.prod.yml")

    for service_name in (
        "postgres",
        "rabbitmq",
        "governance-migrate",
        "governance-api",
        "governance-worker",
        "ui",
    ):
        assert f"  {service_name}:" in compose

    assert "elasticsearch:" not in compose
    assert "SKEINRANK_ENV: production" in compose
    assert "SKEINRANK_GOVERNANCE_API_ENV: production" in compose
    assert 'SKEINRANK_GOVERNANCE_API_AUTH_ENABLED: "true"' in compose
    assert "SKEINRANK_GOVERNANCE_API_PRODUCTION_SECURITY_ENABLED" in compose
    assert "SKEINRANK_GOVERNANCE_API_ELASTICSEARCH_URL" in compose
    assert "127.0.0.1:${GOVERNANCE_API_PORT:-8010}:8010" in compose
    assert "127.0.0.1:${UI_PORT:-5173}:5173" in compose


def test_production_compose_does_not_publish_internal_datastores() -> None:
    compose = _read("docker-compose.prod.yml")

    assert "15432:5432" not in compose
    assert "5432:5432" not in compose
    assert "5672:5672" not in compose
    assert "15672:15672" not in compose
    assert "19200:9200" not in compose
    assert "9200:9200" not in compose


def test_production_env_example_documents_required_secrets() -> None:
    env_example = _read(".env.production.example")

    required_fragments = (
        "SKEINRANK_ENV=production",
        "SKEINRANK_GOVERNANCE_API_ENV=production",
        "SKEINRANK_GOVERNANCE_API_AUTH_ENABLED=true",
        "SKEINRANK_GOVERNANCE_API_PRODUCTION_SECURITY_ENABLED=true",
        "POSTGRES_PASSWORD=CHANGE_ME_STRONG_POSTGRES_PASSWORD",
        "RABBITMQ_DEFAULT_PASS=CHANGE_ME_STRONG_RABBITMQ_PASSWORD",
        "SKEINRANK_GOVERNANCE_API_ADMIN_PASSWORD=CHANGE_ME_STRONG_BOOTSTRAP_ADMIN_PASSWORD",
        "SKEINRANK_GOVERNANCE_API_CORS_ORIGINS=https://skeinrank.example.com",
        "SKEINRANK_GOVERNANCE_API_ELASTICSEARCH_URL=https://elasticsearch.example.com:9200",
    )
    for fragment in required_fragments:
        assert fragment in env_example


def test_security_guide_documents_production_guardrails() -> None:
    guide = _read("docs/deployment/security.md")

    expected_fragments = (
        "Production security profile",
        "docker-compose.prod.yml",
        "cp .env.production.example .env",
        "SKEINRANK_ENV=production",
        "auth is disabled",
        "SQLite is used as the database",
        "wildcard CORS",
        "Celery uses default broker credentials",
        "Elasticsearch URL is missing",
        "PostgreSQL, RabbitMQ, and Elasticsearch should not be exposed directly",
    )
    for fragment in expected_fragments:
        assert fragment in guide


def test_gitignore_keeps_env_examples_tracked() -> None:
    gitignore = _read(".gitignore")

    assert "!.env.example" in gitignore
    assert "!.env.production.example" in gitignore
