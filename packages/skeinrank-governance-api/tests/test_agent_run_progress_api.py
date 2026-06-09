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
    return binding.json()["id"]


def test_agent_run_progress_endpoint_summarizes_tracking_tables(tmp_path):
    client = _client(tmp_path)
    binding_id = _seed_profile_and_binding(client)

    run = client.post(
        "/v1/agents/runs",
        json={
            "run_id": "progress-run-001",
            "status": "running",
            "trigger_type": "worker",
            "profile_name": "default_it",
            "binding_id": binding_id,
            "agent_version": "agent-progress-v1",
            "prompt_version": "prompt-v1",
            "openrouter_model": "openai/gpt-4o-mini",
            "summary": {"expected_documents_total": 4, "phase": "scanning"},
        },
    )
    assert run.status_code == 201, run.text

    ok_visit = client.post(
        "/v1/agents/runs/progress-run-001/document-visits",
        json={
            "source_id": "doc-001",
            "source_type": "elasticsearch_hit",
            "index_name": "default-it-docs",
            "content": "The k8s rollout was stuck after a bad image tag.",
            "metadata": {"title": "Kubernetes rollout"},
            "evidence_windows_found": 1,
        },
    )
    assert ok_visit.status_code == 201, ok_visit.text

    error_visit = client.post(
        "/v1/agents/runs/progress-run-001/document-visits",
        json={
            "source_id": "doc-002",
            "source_type": "elasticsearch_hit",
            "index_name": "default-it-docs",
            "content": "Broken payload",
            "error_message": "source document failed to parse",
        },
    )
    assert error_visit.status_code == 201, error_visit.text

    candidate = client.post(
        "/v1/agents/runs/progress-run-001/candidate-observations",
        json={
            "candidate_alias": "k8s",
            "document_visit_id": ok_visit.json()["id"],
            "possible_canonical": "kubernetes",
            "slot": "technology",
            "observation_status": "queued_for_review",
            "evidence_windows": [
                {
                    "source_id": "doc-001",
                    "source_type": "elasticsearch_hit",
                    "field": "body",
                    "text": "The k8s rollout was stuck after a bad image tag.",
                }
            ],
        },
    )
    assert candidate.status_code == 201, candidate.text

    review = client.post(
        "/v1/agents/runs/progress-run-001/llm-reviews",
        json={
            "candidate_alias": "k8s",
            "candidate_observation_id": candidate.json()["id"],
            "possible_canonical": "kubernetes",
            "slot": "technology",
            "review_status": "proposed",
            "action": "propose_alias",
            "confidence": 0.91,
            "model": "openai/gpt-4o-mini",
            "review_hash": "reviewhash0001",
        },
    )
    assert review.status_code == 201, review.text

    attempt = client.post(
        "/v1/agents/runs/progress-run-001/proposal-attempts",
        json={
            "alias_value": "k8s",
            "candidate_observation_id": candidate.json()["id"],
            "llm_review_id": review.json()["id"],
            "canonical_value": "kubernetes",
            "slot": "technology",
            "attempt_status": "validation_warning",
            "validation_status": "warning",
            "confidence": 0.91,
            "idempotency_key": "progress-run-001:k8s",
            "submitted": False,
        },
    )
    assert attempt.status_code == 201, attempt.text

    response = client.get("/v1/agents/runs/progress-run-001/progress")
    assert response.status_code == 200, response.text
    payload = response.json()

    assert payload["schema_version"] == "skeinrank.agent_run_progress.v1"
    assert payload["run_id"] == "progress-run-001"
    assert payload["status"] == "running"
    assert payload["phase"] == "scanning"
    assert payload["is_terminal"] is False
    assert payload["percent_complete"] == 0.5

    assert payload["documents"]["total_expected"] == 4
    assert payload["documents"]["visited"] == 2
    assert payload["documents"]["pending"] == 2
    assert payload["documents"]["errors"] == 1
    assert payload["documents"]["by_status"] == {"error": 1, "new_document": 1}

    assert payload["candidates"]["observed"] == 1
    assert payload["candidates"]["queued_for_review"] == 1
    assert payload["evidence"]["windows"] == 1
    assert payload["evidence"]["windows_reported_by_visits"] == 1
    assert payload["llm_reviews"]["total"] == 1
    assert payload["llm_reviews"]["proposed"] == 1
    assert payload["proposals"]["total"] == 1
    assert payload["proposals"]["validation_warning"] == 1
    assert payload["proposals"]["submitted"] == 0
    assert payload["errors"]["total"] == 1
    assert payload["errors"]["document_errors"] == 1


def test_agent_run_progress_endpoint_handles_terminal_runs_without_expected_total(
    tmp_path,
):
    client = _client(tmp_path)

    create_response = client.post(
        "/v1/agents/runs",
        json={"run_id": "finished-run", "status": "succeeded"},
    )
    assert create_response.status_code == 201, create_response.text

    response = client.get("/v1/agents/runs/finished-run/progress")
    assert response.status_code == 200, response.text
    payload = response.json()

    assert payload["is_terminal"] is True
    assert payload["percent_complete"] == 1.0
    assert payload["documents"]["total_expected"] is None
    assert payload["documents"]["visited"] == 0
    assert payload["phase"] == "succeeded"


def test_agent_run_progress_endpoint_returns_404_for_missing_run(tmp_path):
    client = _client(tmp_path)

    response = client.get("/v1/agents/runs/missing-run/progress")

    assert response.status_code == 404, response.text
    assert "Agent run not found" in response.json()["detail"]
