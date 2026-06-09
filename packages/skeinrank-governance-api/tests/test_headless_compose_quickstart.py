from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def test_headless_compose_declares_api_postgres_only_stack() -> None:
    compose = _read("docker-compose.headless.yml")

    for service_name in (
        "postgres",
        "governance-migrate",
        "governance-api",
    ):
        assert f"  {service_name}:" in compose

    for excluded_service in (
        "rabbitmq",
        "elasticsearch",
        "governance-worker",
        "ui",
        "prometheus",
        "grafana",
    ):
        assert f"  {excluded_service}:" not in compose

    assert "skeinrank-postgres-headless" in compose
    assert "skeinrank-governance-api-headless" in compose
    assert "SKEINRANK_GOVERNANCE_API_DATABASE_URL" in compose
    assert "SKEINRANK_GOVERNANCE_API_AUTH_ENABLED" in compose
    assert "${SKEINRANK_GOVERNANCE_API_AUTH_ENABLED:-false}" in compose
    assert "SKEINRANK_GOVERNANCE_API_ENRICHMENT_JOBS_BACKEND" in compose
    assert "${SKEINRANK_GOVERNANCE_API_ENRICHMENT_JOBS_BACKEND:-sync}" in compose
    assert "127.0.0.1:${GOVERNANCE_API_PORT:-8010}:8010" in compose
    assert "/readyz" in compose
    assert "service_completed_successfully" in compose
    assert "service_healthy" in compose


def test_headless_env_example_documents_local_defaults() -> None:
    env_example = _read("deploy/docker/headless.env.example")

    expected_settings = (
        "POSTGRES_DB=app_db",
        "POSTGRES_USER=app_user",
        "POSTGRES_PASSWORD=skeinrank_headless_password",
        "POSTGRES_PORT=15433",
        "GOVERNANCE_API_PORT=8010",
        "SKEINRANK_GOVERNANCE_API_AUTH_ENABLED=false",
        "SKEINRANK_GOVERNANCE_API_BOOTSTRAP_ADMIN=false",
        "SKEINRANK_GOVERNANCE_API_ENRICHMENT_JOBS_BACKEND=sync",
        "SKEINRANK_GOVERNANCE_API_METRICS_ENABLED=true",
        "SKEINRANK_GOVERNANCE_API_TRACING_ENABLED=false",
    )
    for setting in expected_settings:
        assert setting in env_example


def test_headless_quickstart_documents_golden_path() -> None:
    guide = _read("docs/deployment/headless-quickstart.md")

    expected_fragments = (
        "docker compose \\",
        "--env-file deploy/docker/headless.env.example",
        "-f docker-compose.headless.yml",
        "deploy/docker/scripts/headless-golden-path.sh",
        "/v1/headless/dictionaries/validate",
        "/v1/headless/dictionaries/apply",
        "/v1/governance/elasticsearch/bindings",
        "/v1/headless/snapshots/export?binding_id=",
        "skeinrank.runtime_snapshot_artifact.v1",
        "skeinrank-migrate snapshot-inspect",
        "docker compose -f docker-compose.headless.yml down -v",
    )
    for fragment in expected_fragments:
        assert fragment in guide


def test_headless_golden_path_script_uses_stable_contracts() -> None:
    script = _read("deploy/docker/scripts/headless-golden-path.sh")

    expected_fragments = (
        "set -euo pipefail",
        "SKEINRANK_HEADLESS_API_URL",
        "examples/migration/console_dictionary.example.json",
        "/v1/headless/dictionaries/apply",
        "/v1/governance/elasticsearch/bindings",
        "/v1/headless/snapshots/export?binding_id=",
        "schema_version",
        "artifact_type",
        "alias_entries_total",
    )
    for fragment in expected_fragments:
        assert fragment in script


def test_makefile_exposes_headless_targets() -> None:
    makefile = _read("Makefile")

    expected_fragments = (
        "HEADLESS_COMPOSE := docker compose --env-file deploy/docker/headless.env.example -f docker-compose.headless.yml",
        "headless-up:",
        "headless-down:",
        "headless-reset:",
        "headless-golden-path:",
        "deploy/docker/scripts/headless-golden-path.sh",
    )
    for fragment in expected_fragments:
        assert fragment in makefile


def test_root_and_docs_link_headless_quickstart() -> None:
    readme = _read("README.md")
    docs_readme = _read("docs/README.md")
    deploy_readme = _read("deploy/docker/README.md")

    for text in (readme, docs_readme, deploy_readme):
        assert (
            "docs/deployment/headless-quickstart.md" in text
            or "deployment/headless-quickstart.md" in text
        )

    package_readme = _read("packages/skeinrank-governance-api/README.md")
    assert "docker-compose.headless.yml" in deploy_readme
    assert "docker-compose.headless.yml" in package_readme
    assert "Headless Compose quickstart" in package_readme
