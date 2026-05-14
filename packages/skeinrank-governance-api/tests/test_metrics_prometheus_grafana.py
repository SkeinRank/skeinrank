from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[3]


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def test_dev_compose_declares_observability_profile() -> None:
    compose = _read("docker-compose.dev.yml")

    assert "prom/prometheus:v2.55.1" in compose
    assert "grafana/grafana:11.5.2" in compose
    assert 'profiles: ["observability"]' in compose
    assert "${PROMETHEUS_PORT:-9090}:9090" in compose
    assert "${GRAFANA_PORT:-3000}:3000" in compose
    assert (
        "./deploy/prometheus/prometheus.yml:/etc/prometheus/prometheus.yml:ro"
        in compose
    )
    assert "./deploy/grafana/provisioning:/etc/grafana/provisioning:ro" in compose
    assert "SKEINRANK_GOVERNANCE_API_METRICS_ENABLED" in compose
    assert "SKEINRANK_GOVERNANCE_API_METRICS_PATH" in compose


def test_prometheus_scrapes_governance_api_metrics() -> None:
    prometheus = _read("deploy/prometheus/prometheus.yml")

    assert "job_name: skeinrank-governance-api" in prometheus
    assert "metrics_path: /metrics" in prometheus
    assert "governance-api:8010" in prometheus


def test_grafana_provisioning_references_dashboard_and_prometheus() -> None:
    datasource = _read("deploy/grafana/provisioning/datasources/prometheus.yml")
    dashboard_provider = _read("deploy/grafana/provisioning/dashboards/skeinrank.yml")
    dashboard = json.loads(_read("deploy/grafana/dashboards/skeinrank-overview.json"))

    assert "url: http://prometheus:9090" in datasource
    assert "path: /var/lib/grafana/dashboards" in dashboard_provider
    assert dashboard["title"] == "SkeinRank Overview"
    assert "skeinrank_http_requests_total" in json.dumps(dashboard)
    assert "skeinrank_runtime_search_requests_total" in json.dumps(dashboard)
    assert "skeinrank_enrichment_jobs_total" in json.dumps(dashboard)


def test_observability_docs_reference_metrics_stack() -> None:
    observability = _read("docs/deployment/observability.md")
    docker_guide = _read("docs/deployment/docker-compose.md")
    docker_readme = _read("deploy/docker/README.md")

    expected = (
        "GET /metrics",
        "SKEINRANK_GOVERNANCE_API_METRICS_ENABLED",
        "docker compose -f docker-compose.dev.yml --profile observability up --build",
        "deploy/prometheus/prometheus.yml",
        "deploy/grafana/dashboards/skeinrank-overview.json",
    )
    for fragment in expected:
        assert fragment in observability

    assert "--profile observability" in docker_guide
    assert "--profile observability" in docker_readme


def test_enrichment_job_metrics_handle_mixed_datetime_awareness(monkeypatch) -> None:
    from skeinrank_governance_api import job_runner

    calls: list[dict[str, object]] = []

    def fake_record_enrichment_job(**kwargs: object) -> None:
        calls.append(kwargs)

    monkeypatch.setattr(job_runner, "record_enrichment_job", fake_record_enrichment_job)

    job = SimpleNamespace(
        started_at=datetime(2026, 5, 14, 10, 53, 27),
        finished_at=datetime(2026, 5, 14, 10, 53, 29, tzinfo=timezone.utc),
        write_strategy="in_place",
        documents_seen=3,
        documents_enriched=2,
        documents_failed=0,
    )

    job_runner._record_job_metrics(job, status="succeeded")

    assert calls == [
        {
            "status": "succeeded",
            "write_strategy": "in_place",
            "duration_seconds": 2.0,
            "documents_seen": 3,
            "documents_enriched": 2,
            "documents_failed": 0,
        }
    ]
