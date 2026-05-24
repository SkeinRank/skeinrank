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


def _seed_profile_binding_and_run(client: TestClient, run_id: str) -> int:
    profile = client.post("/v1/governance/profiles", json={"name": "default_it"})
    assert profile.status_code == 201, profile.text
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
    binding_id = binding.json()["id"]
    run = client.post(
        "/v1/agents/runs",
        json={
            "run_id": run_id,
            "status": "running",
            "trigger_type": "scheduled",
            "profile_name": "default_it",
            "binding_id": binding_id,
            "agent_version": "44B",
            "prompt_version": "prompt-v1",
            "openrouter_model": "openai/gpt-4o-mini",
            "config_hash": "cfg-v1",
        },
    )
    assert run.status_code == 201, run.text
    return binding_id


def test_document_visit_tracks_new_and_unchanged_documents(tmp_path):
    client = _client(tmp_path)
    _seed_profile_binding_and_run(client, "run-001")

    first = client.post(
        "/v1/agents/runs/run-001/document-visits",
        json={
            "source_id": "doc-001",
            "source_type": "elasticsearch_hit",
            "index_name": "default-it-docs",
            "content": "k8s rollout notes",
            "metadata": {"title": "Kubernetes rollout"},
            "evidence_windows_found": 2,
        },
    )
    assert first.status_code == 201, first.text
    first_payload = first.json()
    assert first_payload["visit_status"] == "new_document"
    assert first_payload["should_scan"] is True
    assert first_payload["evidence_windows_found"] == 2
    assert first_payload["metadata"] == {"title": "Kubernetes rollout"}

    create_second_run = client.post(
        "/v1/agents/runs",
        json={
            "run_id": "run-002",
            "status": "running",
            "trigger_type": "scheduled",
            "profile_name": "default_it",
            "binding_id": first_payload["binding_id"],
            "agent_version": "44B",
            "prompt_version": "prompt-v1",
            "openrouter_model": "openai/gpt-4o-mini",
            "config_hash": "cfg-v1",
        },
    )
    assert create_second_run.status_code == 201, create_second_run.text
    second = client.post(
        "/v1/agents/runs/run-002/document-visits",
        json={"source_id": "doc-001", "content": "k8s rollout notes"},
    )
    assert second.status_code == 201, second.text
    assert second.json()["visit_status"] == "unchanged_seen"
    assert second.json()["should_scan"] is False

    list_response = client.get("/v1/agents/runs/run-002/document-visits")
    assert list_response.status_code == 200, list_response.text
    assert [item["source_id"] for item in list_response.json()] == ["doc-001"]


def test_document_visit_detects_content_and_context_changes(tmp_path):
    client = _client(tmp_path)
    binding_id = _seed_profile_binding_and_run(client, "run-001")

    first = client.post(
        "/v1/agents/runs/run-001/document-visits",
        json={"source_id": "doc-001", "content": "original content"},
    )
    assert first.status_code == 201, first.text

    content_run = client.post(
        "/v1/agents/runs",
        json={
            "run_id": "run-content-change",
            "status": "running",
            "profile_name": "default_it",
            "binding_id": binding_id,
            "agent_version": "44B",
            "prompt_version": "prompt-v1",
            "openrouter_model": "openai/gpt-4o-mini",
            "config_hash": "cfg-v1",
        },
    )
    assert content_run.status_code == 201, content_run.text
    changed = client.post(
        "/v1/agents/runs/run-content-change/document-visits",
        json={"source_id": "doc-001", "content": "changed content"},
    )
    assert changed.status_code == 201, changed.text
    assert changed.json()["visit_status"] == "content_changed"
    assert changed.json()["should_scan"] is True

    context_run = client.post(
        "/v1/agents/runs",
        json={
            "run_id": "run-context-change",
            "status": "running",
            "profile_name": "default_it",
            "binding_id": binding_id,
            "agent_version": "44B",
            "prompt_version": "prompt-v2",
            "openrouter_model": "openai/gpt-4o-mini",
            "config_hash": "cfg-v1",
        },
    )
    assert context_run.status_code == 201, context_run.text
    context_changed = client.post(
        "/v1/agents/runs/run-context-change/document-visits",
        json={"source_id": "doc-001", "content": "changed content"},
    )
    assert context_changed.status_code == 201, context_changed.text
    assert context_changed.json()["visit_status"] == "context_changed"
    assert context_changed.json()["should_scan"] is True


def test_document_visit_rejects_missing_content_and_duplicate_source(tmp_path):
    client = _client(tmp_path)
    _seed_profile_binding_and_run(client, "run-001")

    missing_content = client.post(
        "/v1/agents/runs/run-001/document-visits",
        json={"source_id": "doc-001"},
    )
    assert missing_content.status_code == 400, missing_content.text
    assert "content_hash or content" in missing_content.json()["detail"]

    first = client.post(
        "/v1/agents/runs/run-001/document-visits",
        json={"source_id": "doc-001", "content": "same run"},
    )
    assert first.status_code == 201, first.text
    duplicate = client.post(
        "/v1/agents/runs/run-001/document-visits",
        json={"source_id": "doc-001", "content": "same run"},
    )
    assert duplicate.status_code == 409, duplicate.text


def test_document_visits_can_filter_by_scan_decision(tmp_path):
    client = _client(tmp_path)
    binding_id = _seed_profile_binding_and_run(client, "run-001")
    first = client.post(
        "/v1/agents/runs/run-001/document-visits",
        json={"source_id": "doc-001", "content": "same content"},
    )
    assert first.status_code == 201, first.text

    second_run = client.post(
        "/v1/agents/runs",
        json={
            "run_id": "run-002",
            "status": "running",
            "profile_name": "default_it",
            "binding_id": binding_id,
            "agent_version": "44B",
            "prompt_version": "prompt-v1",
            "openrouter_model": "openai/gpt-4o-mini",
            "config_hash": "cfg-v1",
        },
    )
    assert second_run.status_code == 201, second_run.text
    second = client.post(
        "/v1/agents/runs/run-002/document-visits",
        json={"source_id": "doc-001", "content": "same content"},
    )
    assert second.status_code == 201, second.text

    scan_false = client.get("/v1/agents/runs/run-002/document-visits?should_scan=false")
    assert scan_false.status_code == 200, scan_false.text
    assert [item["visit_status"] for item in scan_false.json()] == ["unchanged_seen"]

    scan_true = client.get("/v1/agents/runs/run-002/document-visits?should_scan=true")
    assert scan_true.status_code == 200, scan_true.text
    assert scan_true.json() == []
