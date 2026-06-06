from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
DOC_PATHS = (
    REPO_ROOT / "docs/deployment/observability.md",
    REPO_ROOT / "docs/deployment/gitops-delivery-runbook.md",
    REPO_ROOT / "docs/deployment/migration-safety.md",
)
DOCKER_COMPOSE_DOC = REPO_ROOT / "docs/deployment/docker-compose.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _markdown_links(content: str) -> list[str]:
    return re.findall(r"\[[^\]]+\]\(([^)]+)\)", content)


def test_observability_and_gitops_docs_are_productized() -> None:
    forbidden = (
        "Patch",
        "patch",
        "31A",
        "31B",
        "31C",
        "43D",
        "45A",
        "45B",
        "46A",
        "59A",
        "60A",
        "60B",
        "60C",
        "future patches",
        "later patch",
    )
    for path in DOC_PATHS:
        content = _read(path)
        for fragment in forbidden:
            assert fragment not in content, f"{fragment!r} leaked into {path}"

    docker_compose = _read(DOCKER_COMPOSE_DOC)
    assert "59A guided" not in docker_compose
    assert "guided Control Plane walkthrough" in docker_compose


def test_observability_doc_keeps_real_operator_surfaces() -> None:
    content = _read(REPO_ROOT / "docs/deployment/observability.md")

    expected_fragments = (
        "GET /metrics",
        "GET /healthz",
        "GET /readyz",
        "GET /schema/health",
        "X-Request-ID",
        "JSON logs",
        "SKEINRANK_GOVERNANCE_API_LOG_FORMAT",
        "SKEINRANK_GOVERNANCE_API_METRICS_ENABLED",
        "SKEINRANK_GOVERNANCE_API_TRACING_ENABLED",
        "SKEINRANK_GOVERNANCE_API_OTEL_CAPTURE_QUERY_TEXT",
        "docker compose -f docker-compose.dev.yml --profile observability up --build",
        "docker compose --env-file .env -f docker-compose.prod.yml --profile observability up -d prometheus grafana",
        "deploy/prometheus/prometheus.yml",
        "deploy/grafana/dashboards/skeinrank-overview.json",
        "deploy/otel/collector.yml",
        "skeinrank_database_up",
        "skeinrank_agent_runs_current",
        "poetry run python -m skeinrank_governance_api.troubleshooting report",
        "ops:reports:read",
    )
    for fragment in expected_fragments:
        assert fragment in content


def test_gitops_doc_keeps_existing_delivery_contract() -> None:
    content = _read(REPO_ROOT / "docs/deployment/gitops-delivery-runbook.md")

    expected_fragments = (
        "GitLab CI",
        "ArgoCD",
        "Flux",
        "SKEINRANK_CONSOLE_API_URL",
        "SKEINRANK_API_TOKEN",
        "SKEINRANK_DICTIONARY_FILE",
        "SKEINRANK_PROFILE_NAME",
        "SKEINRANK_BINDING_ID",
        "skeinrank-migrate lint",
        "skeinrank-migrate plan",
        "skeinrank-migrate apply",
        "--plan-output",
        "skeinrank-migrate export",
        "skeinrank-migrate snapshot-export",
        "skeinrank-migrate snapshot-inspect",
        "`snapshot-export` writes a binding-scoped artifact",
        "rollback is a Git revert",
        "SkeinRank does not need a project-specific reload endpoint",
    )
    for fragment in expected_fragments:
        assert fragment in content

    for nonexistent_surface in (
        "skeinrank-cli apply",
        "skeinrank gitops",
        "/api/v1/reload-config",
        "/v1/runtime/reload",
        "terraform apply",
    ):
        assert nonexistent_surface not in content


def test_migration_safety_doc_keeps_existing_schema_checks() -> None:
    content = _read(REPO_ROOT / "docs/deployment/migration-safety.md")

    expected_fragments = (
        "python -m skeinrank_governance_api.migrations check",
        "GET /schema/health",
        "GET /readyz",
        "current_matches_head=true",
        "multiple_heads=false",
        "make prod-schema-check",
        "make prod-upgrade",
        "SKEINRANK_GOVERNANCE_API_CREATE_TABLES=true",
    )
    for fragment in expected_fragments:
        assert fragment in content


def test_observability_gitops_markdown_links_resolve() -> None:
    for path in DOC_PATHS:
        for link in _markdown_links(_read(path)):
            if link.startswith(("http://", "https://", "mailto:", "#")):
                continue
            target = link.split("#", 1)[0]
            if not target:
                continue
            resolved = (path.parent / target).resolve()
            assert resolved.exists(), f"broken link in {path}: {link}"
