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


def _seed_run_and_visit(client: TestClient) -> int:
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
    run = client.post(
        "/v1/agents/runs",
        json={
            "run_id": "run-001",
            "status": "running",
            "trigger_type": "scheduled",
            "profile_name": "default_it",
            "binding_id": binding.json()["id"],
            "agent_version": "44C",
            "prompt_version": "prompt-v1",
            "openrouter_model": "openai/gpt-4o-mini",
            "config_hash": "cfg-v1",
        },
    )
    assert run.status_code == 201, run.text
    visit = client.post(
        "/v1/agents/runs/run-001/document-visits",
        json={
            "source_id": "doc-001",
            "source_type": "elasticsearch_hit",
            "index_name": "default-it-docs",
            "content": "The k8s rollout was stuck after a bad image tag.",
            "metadata": {"title": "Kubernetes rollout"},
            "evidence_windows_found": 1,
        },
    )
    assert visit.status_code == 201, visit.text
    return visit.json()["id"]


def test_candidate_observation_persists_evidence_windows(tmp_path):
    client = _client(tmp_path)
    visit_id = _seed_run_and_visit(client)

    response = client.post(
        "/v1/agents/runs/run-001/candidate-observations",
        json={
            "candidate_alias": "k8s",
            "document_visit_id": visit_id,
            "possible_canonical": "kubernetes",
            "slot": "technology",
            "observation_status": "queued_for_review",
            "discovery_score": 12.5,
            "weighted_count": 7.0,
            "document_frequency": 1,
            "discovery_reasons": ["mixed_alpha_digit"],
            "canonical_hint": {"reason": "single_configured_alias_match"},
            "candidate_pack": {"possible_canonical": "kubernetes"},
            "metadata": {"source": "unit-test"},
            "evidence_windows": [
                {
                    "source_id": "doc-001",
                    "source_type": "elasticsearch_hit",
                    "field": "body",
                    "start_char": 4,
                    "end_char": 7,
                    "text": "The k8s rollout was stuck after a bad image tag.",
                    "metadata": {"title": "Kubernetes rollout"},
                }
            ],
        },
    )

    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["candidate_alias"] == "k8s"
    assert payload["normalized_alias"] == "k8s"
    assert payload["possible_canonical"] == "kubernetes"
    assert payload["normalized_canonical"] == "kubernetes"
    assert payload["slot"] == "TECHNOLOGY"
    assert payload["observation_status"] == "queued_for_review"
    assert payload["evidence_windows_found"] == 1
    assert payload["discovery_reasons"] == ["mixed_alpha_digit"]
    assert payload["canonical_hint"] == {"reason": "single_configured_alias_match"}
    assert payload["evidence_windows"][0]["source_id"] == "doc-001"
    assert payload["evidence_windows"][0]["evidence_hash"]

    list_response = client.get("/v1/agents/runs/run-001/candidate-observations")
    assert list_response.status_code == 200, list_response.text
    assert [item["candidate_alias"] for item in list_response.json()] == ["k8s"]

    windows = client.get("/v1/agents/runs/run-001/evidence-windows")
    assert windows.status_code == 200, windows.text
    assert [item["candidate_alias"] for item in windows.json()] == ["k8s"]


def test_candidate_observation_rejects_duplicates_and_wrong_visit(tmp_path):
    client = _client(tmp_path)
    visit_id = _seed_run_and_visit(client)

    first = client.post(
        "/v1/agents/runs/run-001/candidate-observations",
        json={"candidate_alias": "kube", "document_visit_id": visit_id},
    )
    assert first.status_code == 201, first.text
    duplicate = client.post(
        "/v1/agents/runs/run-001/candidate-observations",
        json={"candidate_alias": "KUBE"},
    )
    assert duplicate.status_code == 409, duplicate.text

    second_run = client.post("/v1/agents/runs", json={"run_id": "run-002"})
    assert second_run.status_code == 201, second_run.text
    wrong_visit = client.post(
        "/v1/agents/runs/run-002/candidate-observations",
        json={"candidate_alias": "pg", "document_visit_id": visit_id},
    )
    assert wrong_visit.status_code == 400, wrong_visit.text
    assert "different agent run" in wrong_visit.json()["detail"]


def test_candidate_observations_filter_by_status_and_alias(tmp_path):
    client = _client(tmp_path)
    _seed_run_and_visit(client)

    for alias, status in [("pg", "needs_evidence"), ("k8s", "queued_for_review")]:
        response = client.post(
            "/v1/agents/runs/run-001/candidate-observations",
            json={"candidate_alias": alias, "observation_status": status},
        )
        assert response.status_code == 201, response.text

    status_filtered = client.get(
        "/v1/agents/runs/run-001/candidate-observations?status=needs_evidence"
    )
    assert status_filtered.status_code == 200, status_filtered.text
    assert [item["candidate_alias"] for item in status_filtered.json()] == ["pg"]

    alias_filtered = client.get(
        "/v1/agents/runs/run-001/candidate-observations?candidate_alias=K8S"
    )
    assert alias_filtered.status_code == 200, alias_filtered.text
    assert [item["candidate_alias"] for item in alias_filtered.json()] == ["k8s"]
