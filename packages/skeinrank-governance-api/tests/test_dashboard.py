from __future__ import annotations

from fastapi.testclient import TestClient
from skeinrank_governance.models import (
    ElasticsearchBinding,
    ElasticsearchEnrichmentJob,
    utc_now,
)
from skeinrank_governance_api import GovernanceApiConfig, create_app
from skeinrank_governance_api.routes import dashboard as dashboard_routes
from sqlalchemy import select


def _client(tmp_path, **config_overrides) -> TestClient:
    app = create_app(
        GovernanceApiConfig(
            database_url=f"sqlite:///{tmp_path / 'governance.db'}",
            create_tables_on_startup=True,
            service_version="test",
            **config_overrides,
        )
    )
    return TestClient(app)


def test_dashboard_summary_empty_database(tmp_path):
    client = _client(tmp_path)

    response = client.get("/v1/dashboard/summary")

    assert response.status_code == 200
    payload = response.json()
    assert payload["counts"] == {
        "profiles": 0,
        "canonical_terms": 0,
        "aliases": 0,
        "bindings": 0,
        "ready_bindings": 0,
        "stale_bindings": 0,
        "updating_bindings": 0,
        "failed_bindings": 0,
        "never_enriched_bindings": 0,
        "running_jobs": 0,
        "failed_jobs": 0,
    }
    assert payload["setup"] == {
        "has_profile": False,
        "has_terms": False,
        "has_binding": False,
        "has_successful_enrichment": False,
        "has_runtime_snapshot": False,
    }
    assert payload["bindings"] == []
    assert payload["recent_jobs"] == []
    assert payload["readiness"]["database"]["status"] == "ok"
    assert payload["readiness"]["elasticsearch"]["status"] == "not_configured"
    assert payload["readiness"]["rabbitmq"]["status"] == "not_required"
    assert payload["readiness"]["worker"]["status"] == "not_required"


def test_dashboard_summary_reports_setup_progress_and_recent_jobs(tmp_path):
    client = _client(tmp_path)
    client.post("/v1/governance/profiles", json={"name": "default_it"})
    client.post(
        "/v1/governance/profiles/default_it/terms",
        json={"canonical_value": "kubernetes", "slot": "TOOL"},
    )
    client.post(
        "/v1/governance/profiles/default_it/terms/kubernetes/aliases",
        json={"alias_value": "k8s", "confidence": 0.97},
    )
    binding_response = client.post(
        "/v1/governance/elasticsearch/bindings",
        json={
            "name": "infra docs",
            "profile_name": "default_it",
            "index_name": "docs",
            "text_fields": ["title", "body"],
            "target_field": "skeinrank",
            "mode": "write",
            "write_strategy": "reindex_alias_swap",
        },
    )
    assert binding_response.status_code == 201

    session_factory = client.app.state.governance_session_factory
    with session_factory() as session:
        binding = session.scalar(select(ElasticsearchBinding))
        assert binding is not None
        now = utc_now()
        job = ElasticsearchEnrichmentJob(
            binding_id=binding.id,
            profile_id=binding.profile_id,
            status="succeeded",
            write_strategy=binding.write_strategy,
            source_index=binding.index_name,
            target_index="docs__skeinrank_job_1",
            alias_name="docs",
            snapshot_version="default_it@abc123",
            previous_snapshot_version=None,
            requested_by="admin",
            documents_seen=12,
            documents_enriched=10,
            documents_failed=2,
            result_json={"updated_document_ids": ["doc-1"]},
            started_at=now,
            finished_at=now,
        )
        session.add(job)
        session.flush()
        binding.last_successful_snapshot_version = "default_it@abc123"
        binding.last_successful_snapshot_at = now
        binding.last_successful_job_id = job.id
        binding.runtime_snapshot_json = {"version": "default_it@abc123"}
        session.commit()

    response = client.get("/v1/dashboard/summary")

    assert response.status_code == 200
    payload = response.json()
    assert payload["counts"]["profiles"] == 1
    assert payload["counts"]["canonical_terms"] == 1
    assert payload["counts"]["aliases"] == 1
    assert payload["counts"]["bindings"] == 1
    assert payload["counts"]["ready_bindings"] == 1
    assert payload["setup"] == {
        "has_profile": True,
        "has_terms": True,
        "has_binding": True,
        "has_successful_enrichment": True,
        "has_runtime_snapshot": True,
    }
    assert payload["bindings"][0]["name"] == "infra docs"
    assert payload["bindings"][0]["status"] == "ready"
    assert payload["bindings"][0]["snapshot_version"] == "default_it@abc123"
    assert payload["recent_jobs"][0]["status"] == "succeeded"
    assert payload["recent_jobs"][0]["documents_enriched"] == 10


def test_dashboard_summary_reports_celery_readiness_ok(tmp_path, monkeypatch):
    broker_url = "amqp://guest:secret@rabbitmq:5672//"
    monkeypatch.setattr(
        dashboard_routes,
        "_check_celery_broker",
        lambda url, *, timeout_seconds: None,
    )
    monkeypatch.setattr(
        dashboard_routes,
        "_ping_celery_workers",
        lambda url, *, timeout_seconds: {"celery@test-worker": {"ok": "pong"}},
    )
    client = _client(
        tmp_path,
        enrichment_jobs_backend="celery",
        celery_broker_url=broker_url,
    )

    response = client.get("/v1/dashboard/summary")

    assert response.status_code == 200
    readiness = response.json()["readiness"]
    assert readiness["rabbitmq"]["status"] == "ok"
    assert readiness["rabbitmq"]["url"] == "amqp://***@rabbitmq:5672//"
    assert readiness["worker"]["status"] == "ok"
    assert readiness["worker"]["name"] == "celery@test-worker"
    assert readiness["worker"]["url"] == "amqp://***@rabbitmq:5672//"


def test_dashboard_summary_reports_celery_readiness_degraded(tmp_path, monkeypatch):
    broker_url = "amqp://guest:secret@rabbitmq:5672//"

    def raise_broker_error(url, *, timeout_seconds):
        raise RuntimeError("broker unreachable")

    monkeypatch.setattr(
        dashboard_routes,
        "_check_celery_broker",
        raise_broker_error,
    )
    monkeypatch.setattr(
        dashboard_routes,
        "_ping_celery_workers",
        lambda url, *, timeout_seconds: None,
    )
    client = _client(
        tmp_path,
        enrichment_jobs_backend="celery",
        celery_broker_url=broker_url,
    )

    response = client.get("/v1/dashboard/summary")

    assert response.status_code == 200
    readiness = response.json()["readiness"]
    assert readiness["rabbitmq"]["status"] == "degraded"
    assert "broker unreachable" in readiness["rabbitmq"]["message"]
    assert readiness["worker"]["status"] == "degraded"
    assert (
        readiness["worker"]["message"]
        == "No Celery enrichment workers responded to ping."
    )
