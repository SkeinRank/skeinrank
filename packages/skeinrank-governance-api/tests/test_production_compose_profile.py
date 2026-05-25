from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def test_production_env_example_contains_required_compose_settings() -> None:
    env_example = _read(".env.production.example")

    required_settings = (
        "COMPOSE_PROJECT_NAME=skeinrank-prod",
        "POSTGRES_PASSWORD=CHANGE_ME_STRONG_POSTGRES_PASSWORD",
        "RABBITMQ_DEFAULT_PASS=CHANGE_ME_STRONG_RABBITMQ_PASSWORD",
        "SKEINRANK_ENV=production",
        "SKEINRANK_GOVERNANCE_API_ENV=production",
        "SKEINRANK_GOVERNANCE_API_AUTH_ENABLED=true",
        "SKEINRANK_GOVERNANCE_API_PRODUCTION_SECURITY_ENABLED=true",
        "SKEINRANK_GOVERNANCE_API_CORS_ORIGINS=https://skeinrank.example.com",
        "SKEINRANK_GOVERNANCE_API_ELASTICSEARCH_URL=",
        "SKEINRANK_GOVERNANCE_API_LOG_FORMAT=json",
        "SKEINRANK_GOVERNANCE_API_METRICS_ENABLED=true",
        "GRAFANA_ADMIN_PASSWORD=CHANGE_ME_STRONG_GRAFANA_PASSWORD",
        "VITE_SKEINRANK_GOVERNANCE_API_URL=https://skeinrank-api.example.com",
    )
    for setting in required_settings:
        assert setting in env_example

    assert ".env.production.example" in _read(".dockerignore")


def test_production_compose_declares_ops_and_observability_profiles() -> None:
    compose = _read("docker-compose.prod.yml")

    expected_fragments = (
        "name: ${COMPOSE_PROJECT_NAME:-skeinrank-prod}",
        "x-skeinrank-logging: &skeinrank_logging",
        "x-governance-healthcheck: &governance_healthcheck",
        "healthcheck: *governance_healthcheck",
        "governance-schema-check:",
        "python",
        "-m",
        "skeinrank_governance_api.migrations",
        "check",
        "governance-backup-export:",
        "skeinrank_governance_api.backup_restore export",
        'profiles: ["ops"]',
        "prometheus:",
        "grafana:",
        'profiles: ["observability"]',
        "skeinrank_postgres_backups:",
        "skeinrank_prometheus_data:",
        "skeinrank_grafana_data:",
    )
    for fragment in expected_fragments:
        assert fragment in compose

    assert "127.0.0.1:${GOVERNANCE_API_PORT:-8010}:8010" in compose
    assert "127.0.0.1:${UI_PORT:-5173}:5173" in compose
    assert "image: postgres:16.4-alpine" in compose
    assert "image: rabbitmq:3.13.7-management" in compose
    assert "image: rabbitmq:3-management" not in compose
    assert "5432:5432" not in compose
    assert "5672:5672" not in compose
    assert "service_completed_successfully" in compose
    assert "http://127.0.0.1:8010/healthz" in compose
    assert "http://127.0.0.1:8010/readyz" not in compose
    assert (
        "SKEINRANK_GOVERNANCE_API_ELASTICSEARCH_URL: ${SKEINRANK_GOVERNANCE_API_ELASTICSEARCH_URL:-}"
        in compose
    )


def test_production_smoke_script_checks_operational_endpoints() -> None:
    script_path = REPO_ROOT / "deploy/docker/scripts/prod-smoke-test.sh"
    script = script_path.read_text(encoding="utf-8")

    expected_fragments = (
        "set -euo pipefail",
        "SKEINRANK_PROD_SMOKE_API_URL",
        "/livez",
        "/healthz",
        "/readyz",
        "--strict",
        "/schema/health",
        "/metrics",
        "skeinrank_database_up",
        "skeinrank_schema_ok",
        "/v1/ops/troubleshooting/report",
        "SkeinRank production-oriented Compose smoke test passed.",
    )
    for fragment in expected_fragments:
        assert fragment in script

    subprocess.run(["bash", "-n", str(script_path)], check=True)


def test_production_compose_docs_reference_ops_flow() -> None:
    production_guide = _read("docs/deployment/production-compose.md")
    docker_readme = _read("deploy/docker/README.md")
    security = _read("docs/deployment/security.md")
    docs_index = _read("docs/README.md")
    root_readme = _read("README.md")
    package_readme = _read("packages/skeinrank-governance-api/README.md")
    makefile = _read("Makefile")

    expected_fragments = (
        "cp .env.production.example .env",
        "docker compose --env-file .env -f docker-compose.prod.yml config",
        "deploy/docker/scripts/prod-smoke-test.sh",
        "make prod-env-check",
        "make prod-up",
        "make prod-smoke",
        "governance-schema-check",
        "governance-backup-export",
        "--profile observability",
        "Prometheus",
        "Grafana",
        "rabbitmq:3.13.7-management",
    )
    for fragment in expected_fragments:
        assert fragment in production_guide
        assert fragment in docker_readme

    assert "docs/deployment/production-compose.md" in security
    assert "deployment/production-compose.md" in docs_index
    assert "docs/deployment/production-compose.md" in root_readme
    assert "docs/deployment/production-compose.md" in package_readme
    assert "deploy/docker/scripts/prod-smoke-test.sh" in package_readme

    for target in (
        "prod-env-check:",
        "prod-env-check-strict:",
        "prod-config:",
        "prod-up:",
        "prod-smoke:",
        "prod-smoke-strict:",
        "prod-down:",
        "prod-schema-check:",
        "prod-backup-export:",
    ):
        assert target in makefile
