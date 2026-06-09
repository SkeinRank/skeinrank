from __future__ import annotations

from public_docs_guard import assert_productized_text, read_repo_file


def _read(path: str) -> str:
    return read_repo_file(path)


def test_compose_api_healthchecks_use_expected_operational_endpoints() -> None:
    dev_compose = _read("docker-compose.dev.yml")
    prod_compose = _read("docker-compose.prod.yml")

    # The dev stack keeps the stricter readiness healthcheck because it includes
    # a local Elasticsearch service. The production-oriented stack uses liveness/DB/schema
    # health so optional external search backends do not block first bootstrap.
    assert "http://127.0.0.1:8010/readyz" in dev_compose
    assert "http://127.0.0.1:8010/healthz" not in dev_compose

    assert "http://127.0.0.1:8010/healthz" in prod_compose
    assert "http://127.0.0.1:8010/readyz" not in prod_compose


def test_dev_smoke_script_checks_core_deployment_endpoints() -> None:
    script = _read("deploy/docker/scripts/dev-smoke-test.sh")

    expected_fragments = (
        "set -euo pipefail",
        "SKEINRANK_SMOKE_API_URL",
        "/livez",
        "/readyz",
        "/v1/auth/login",
        "/v1/auth/me",
        "/v1/governance/elasticsearch/connection/status",
        "SkeinRank dev stack smoke test passed.",
    )
    for fragment in expected_fragments:
        assert fragment in script


def test_deployment_docs_reference_smoke_helper_and_readiness() -> None:
    docker_guide = _read("docs/deployment/docker-compose.md")
    troubleshooting = _read("docs/deployment/dev-stack-troubleshooting.md")
    docker_readme = _read("deploy/docker/README.md")

    for content in (docker_guide, troubleshooting, docker_readme):
        assert "deploy/docker/scripts/dev-smoke-test.sh" in content
        assert "/readyz" in content

    assert "GET /readyz" in docker_guide
    assert "GET /livez" in docker_guide


def test_deployment_docs_reference_observability_foundation() -> None:
    observability = _read("docs/deployment/observability.md")
    docker_guide = _read("docs/deployment/docker-compose.md")
    docker_readme = _read("deploy/docker/README.md")

    expected_fragments = (
        "Observability foundation",
        "SKEINRANK_GOVERNANCE_API_LOG_FORMAT",
        "SKEINRANK_GOVERNANCE_API_REQUEST_ID_HEADER",
        "X-Request-ID",
        "JSON logs",
    )
    for fragment in expected_fragments:
        assert fragment in observability

    assert "docs/deployment/observability.md" in docker_guide
    assert "docs/deployment/observability.md" in docker_readme


def test_deploy_docker_readme_uses_product_language() -> None:
    readme = _read("deploy/docker/README.md")

    assert_productized_text(
        readme,
        source="deploy/docker/README.md",
        extra_forbidden=("milestone",),
    )

    expected_sections = (
        "Release Compose with GHCR images",
        "Development quick start",
        "First-search walkthrough",
        "Production-oriented profile",
        "OpenRouter alias scout Compose demo",
        "Controlled upgrade flow",
    )
    for section in expected_sections:
        assert section in readme
