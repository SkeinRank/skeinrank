from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def test_compose_api_healthchecks_use_readiness_endpoint() -> None:
    dev_compose = _read("docker-compose.dev.yml")
    prod_compose = _read("docker-compose.prod.yml")

    assert "http://127.0.0.1:8010/readyz" in dev_compose
    assert "http://127.0.0.1:8010/readyz" in prod_compose
    assert "http://127.0.0.1:8010/healthz" not in dev_compose
    assert "http://127.0.0.1:8010/healthz" not in prod_compose


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
