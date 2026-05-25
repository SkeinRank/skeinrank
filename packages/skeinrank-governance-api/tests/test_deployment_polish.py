from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def test_compose_api_healthchecks_use_expected_operational_endpoints() -> None:
    dev_compose = _read("docker-compose.dev.yml")
    prod_compose = _read("docker-compose.prod.yml")

    # The dev stack keeps the stricter readiness healthcheck because it includes
    # a local Elasticsearch service. The production-ish stack uses liveness/DB/schema
    # health so optional external search backends do not block the first bootstrap.
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
