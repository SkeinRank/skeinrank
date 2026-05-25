from __future__ import annotations

from fastapi.testclient import TestClient
from skeinrank_governance_api import GovernanceApiConfig, create_app
from skeinrank_governance_api.observability.metrics import registry


def _client(tmp_path) -> TestClient:
    registry.reset()
    app = create_app(
        GovernanceApiConfig(
            database_url=f"sqlite:///{tmp_path / 'governance.db'}",
            create_tables_on_startup=True,
            service_version="test",
            access_log_enabled=False,
        )
    )
    return TestClient(app)


def test_metrics_refreshes_operational_health_gauges(tmp_path):
    client = _client(tmp_path)

    readyz_response = client.get("/readyz")
    metrics_response = client.get("/metrics")

    assert readyz_response.status_code == 200
    assert metrics_response.status_code == 200
    body = metrics_response.text
    assert "skeinrank_database_up 1" in body
    assert "skeinrank_schema_ok 0" in body
    assert "skeinrank_schema_current_matches_head 0" in body
    assert "skeinrank_schema_missing_tables 0" in body
    assert 'skeinrank_elasticsearch_up{configured="false"} 0' in body
    assert (
        'skeinrank_health_checks_total{endpoint="readyz",status="degraded"} 1' in body
    )
    assert 'skeinrank_operational_metrics_refresh_total{status="succeeded"} 1' in body
    assert "skeinrank_operational_metrics_last_refresh_success 1" in body


def test_metrics_refreshes_agent_tracking_gauges(tmp_path):
    client = _client(tmp_path)

    queued = client.post("/v1/agents/runs", json={"run_id": "agent-run-queued"})
    running = client.post(
        "/v1/agents/runs",
        json={"run_id": "agent-run-running", "status": "running"},
    )
    assert queued.status_code == 201, queued.text
    assert running.status_code == 201, running.text

    metrics_response = client.get("/metrics")

    assert metrics_response.status_code == 200
    body = metrics_response.text
    assert 'skeinrank_agent_runs_current{status="queued"} 1' in body
    assert 'skeinrank_agent_runs_current{status="running"} 1' in body
    assert 'skeinrank_agent_runs_current{status="failed"} 0' in body
    assert 'skeinrank_agent_document_visits_current{status="new_document"} 0' in body
    assert (
        'skeinrank_agent_candidate_observations_current{status="discovered"} 0' in body
    )
    assert 'skeinrank_agent_llm_reviews_current{status="proposed"} 0' in body
    assert 'skeinrank_agent_proposal_attempts_current{status="submitted"} 0' in body
    assert "skeinrank_agent_evidence_windows_current 0" in body
