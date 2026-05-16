from __future__ import annotations

from fastapi.testclient import TestClient
from skeinrank_governance.models import (
    ElasticsearchBinding,
    ElasticsearchEnrichmentJob,
    TerminologyProfile,
    utc_now,
)
from skeinrank_governance_api import GovernanceApiConfig, create_app
from skeinrank_governance_api.runtime_snapshots import build_runtime_snapshot_payload
from sqlalchemy import select


def _client(tmp_path) -> TestClient:
    app = create_app(
        GovernanceApiConfig(
            database_url=f"sqlite:///{tmp_path / 'governance.db'}",
            create_tables_on_startup=True,
            service_version="test",
        )
    )
    return TestClient(app)


def test_snapshot_summary_empty_database(tmp_path):
    client = _client(tmp_path)

    response = client.get("/v1/snapshots/summary")

    assert response.status_code == 200
    payload = response.json()
    assert payload["counts"] == {
        "bindings": 0,
        "active_snapshots": 0,
        "stale_snapshots": 0,
        "pending_snapshots": 0,
        "failed_updates": 0,
        "never_enriched": 0,
        "rollback_available": 0,
    }
    assert payload["bindings"] == []
    assert payload["history"] == []


def test_snapshot_summary_reports_active_snapshot_history_and_profile_drift(tmp_path):
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
            "filter_field": "team",
            "filter_value": "infra",
            "mode": "write",
            "write_strategy": "reindex_alias_swap",
        },
    )
    assert binding_response.status_code == 201

    session_factory = client.app.state.governance_session_factory
    with session_factory() as session:
        profile = session.scalar(select(TerminologyProfile))
        binding = session.scalar(select(ElasticsearchBinding))
        assert profile is not None
        assert binding is not None
        snapshot_payload = build_runtime_snapshot_payload(
            session,
            profile,
            snapshot_version="default_it@abc123",
        )
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
            snapshot_json=snapshot_payload,
            previous_snapshot_version="default_it@old001",
            requested_by="admin",
            documents_seen=12,
            documents_enriched=10,
            documents_failed=2,
            result_json={"rollout": {"rollback_available": True}},
            started_at=now,
            finished_at=now,
        )
        session.add(job)
        session.flush()
        binding.last_successful_snapshot_version = "default_it@abc123"
        binding.last_successful_snapshot_at = now
        binding.last_successful_job_id = job.id
        binding.runtime_snapshot_json = snapshot_payload
        session.commit()

    client.post(
        "/v1/governance/profiles/default_it/terms/kubernetes/aliases",
        json={"alias_value": "kube", "confidence": 0.94},
    )

    response = client.get("/v1/snapshots/summary")

    assert response.status_code == 200
    payload = response.json()
    assert payload["counts"]["bindings"] == 1
    assert payload["counts"]["active_snapshots"] == 1
    assert payload["counts"]["stale_snapshots"] == 1
    assert payload["counts"]["rollback_available"] == 1
    binding = payload["bindings"][0]
    assert binding["name"] == "infra docs"
    assert binding["status"] == "stale"
    assert binding["active_snapshot_version"] == "default_it@abc123"
    assert binding["filter_field"] == "team"
    assert binding["filter_value"] == "infra"
    assert binding["snapshot_aliases_total"] == 1
    assert binding["current_aliases_total"] == 2
    assert binding["diff"]["added_aliases"] == 1
    assert binding["diff"]["changed"] is True
    assert payload["history"][0]["job_id"] == binding["last_successful_job_id"]
    assert payload["history"][0]["snapshot_version"] == "default_it@abc123"
    assert payload["history"][0]["alias_entries_total"] == 1
    assert payload["history"][0]["rollback_available"] is True
