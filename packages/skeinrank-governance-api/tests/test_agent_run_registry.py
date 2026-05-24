from __future__ import annotations

from fastapi.testclient import TestClient
from skeinrank_governance_api import GovernanceApiConfig, create_app


def _client(tmp_path) -> TestClient:
    app = create_app(
        GovernanceApiConfig(
            database_url=f"sqlite:///{tmp_path / 'governance.db'}",
            create_tables_on_startup=True,
            service_version="test",
        )
    )
    return TestClient(app)


def _seed_profile_and_binding(client: TestClient) -> int:
    response = client.post("/v1/governance/profiles", json={"name": "default_it"})
    assert response.status_code == 201, response.text
    binding = client.post(
        "/v1/governance/elasticsearch/bindings",
        json={
            "name": "Default IT docs",
            "profile_name": "default_it",
            "index_name": "default-it-docs",
            "text_fields": ["title", "body"],
            "target_field": "skeinrank",
            "mode": "dry_run",
        },
    )
    assert binding.status_code == 201, binding.text
    return binding.json()["id"]


def test_agent_run_registry_create_list_get_and_update(tmp_path):
    client = _client(tmp_path)
    binding_id = _seed_profile_and_binding(client)

    create_response = client.post(
        "/v1/agents/runs",
        json={
            "run_id": "agent-run-001",
            "agent_name": "openrouter_alias_scout",
            "agent_version": "44A",
            "status": "queued",
            "trigger_type": "scheduled",
            "profile_name": "Default IT",
            "binding_id": binding_id,
            "openrouter_model": "openai/gpt-4o-mini",
            "prompt_version": "prompt-v1",
            "workflow_engine": "dependency_light_state_machine",
            "config_hash": "abc123",
            "artifacts_uri": "reports/agent-run-001",
            "report_uri": "reports/agent-run-001/manifest.json",
            "summary": {"stage": "created"},
        },
    )

    assert create_response.status_code == 201, create_response.text
    payload = create_response.json()
    assert payload["run_id"] == "agent-run-001"
    assert payload["normalized_profile_name"] == "default_it"
    assert payload["binding_id"] == binding_id
    assert payload["requested_by"] == "local_dev"
    assert payload["summary"] == {"stage": "created"}

    list_response = client.get("/v1/agents/runs?profile_name=default_it")
    assert list_response.status_code == 200, list_response.text
    assert [item["run_id"] for item in list_response.json()] == ["agent-run-001"]

    get_response = client.get("/v1/agents/runs/agent-run-001")
    assert get_response.status_code == 200, get_response.text
    assert get_response.json()["run_id"] == "agent-run-001"

    update_response = client.patch(
        "/v1/agents/runs/agent-run-001",
        json={
            "status": "succeeded",
            "summary": {"candidates": 3, "proposals_prepared": 2},
            "report_uri": "reports/agent-run-001/cycle_report.json",
        },
    )
    assert update_response.status_code == 200, update_response.text
    updated = update_response.json()
    assert updated["status"] == "succeeded"
    assert updated["finished_at"] is not None
    assert updated["summary"] == {"candidates": 3, "proposals_prepared": 2}


def test_agent_run_registry_rejects_duplicate_run_id(tmp_path):
    client = _client(tmp_path)

    first = client.post("/v1/agents/runs", json={"run_id": "duplicate-run"})
    assert first.status_code == 201, first.text

    second = client.post("/v1/agents/runs", json={"run_id": "duplicate-run"})
    assert second.status_code == 409, second.text
    assert "already exists" in second.json()["detail"]


def test_agent_run_registry_validates_profile_and_status(tmp_path):
    client = _client(tmp_path)

    missing_profile = client.post(
        "/v1/agents/runs",
        json={"run_id": "missing-profile", "profile_name": "does-not-exist"},
    )
    assert missing_profile.status_code == 400, missing_profile.text
    assert "Profile not found" in missing_profile.json()["detail"]

    invalid_status = client.post(
        "/v1/agents/runs",
        json={"run_id": "bad-status", "status": "done"},
    )
    assert invalid_status.status_code == 400, invalid_status.text
    assert "Invalid agent run status" in invalid_status.json()["detail"]
