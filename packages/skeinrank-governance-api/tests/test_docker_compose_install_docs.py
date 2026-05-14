from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def test_docker_compose_install_guide_documents_first_search_flow() -> None:
    guide = _read("docs/deployment/docker-compose.md")

    expected_fragments = (
        "cp .env.example .env",
        "docker compose -f docker-compose.dev.yml up --build",
        "GET /readyz",
        "/v1/auth/login",
        "/v1/console/dictionary/import",
        "examples/migration/console_dictionary.example.json",
        "/v1/governance/elasticsearch/bindings",
        "/v1/governance/elasticsearch/bindings/$BINDING_ID/jobs",
        "/v1/search",
        "/v1/search/multi",
        "docker compose -f docker-compose.dev.yml down -v",
    )
    for fragment in expected_fragments:
        assert fragment in guide


def test_docker_compose_install_guide_documents_runtime_contract() -> None:
    guide = _read("docs/deployment/docker-compose.md")

    assert "dictionary import" in guide
    assert "Elasticsearch binding" in guide
    assert "enrichment job" in guide
    assert "runtime search" in guide
    assert "binding_id" in guide
    assert "skeinrank.snapshot_version" in guide
    assert "documents_seen: 3" in guide
    assert "documents_enriched: 2" in guide
    assert "documents_failed: 0" in guide


def test_deploy_readme_links_full_install_docs() -> None:
    readme = _read("deploy/docker/README.md")

    assert "docs/deployment/docker-compose.md" in readme
    assert "docs/deployment/dev-stack-troubleshooting.md" in readme
    assert "create demo Elasticsearch index" in readme
    assert "run enrichment job" in readme
    assert "runtime search" in readme


def test_troubleshooting_guide_documents_common_dev_failures() -> None:
    guide = _read("docs/deployment/dev-stack-troubleshooting.md")

    expected_fragments = (
        "Port is already in use",
        "lsof -nP -iTCP:5672",
        "Worker keeps restarting",
        "docker compose -f docker-compose.dev.yml logs -f governance-worker",
        "Migrations failed",
        "API is up but UI cannot log in",
        "down -v",
    )
    for fragment in expected_fragments:
        assert fragment in guide


def test_root_readme_mentions_docker_compose_docs() -> None:
    readme = _read("README.md")

    assert "## Docker Compose dev stack" in readme
    assert "docs/deployment/docker-compose.md" in readme
    assert "docs/deployment/dev-stack-troubleshooting.md" in readme
    assert "docs/deployment/security.md" in readme
    assert "docker-compose.prod.yml" in readme
