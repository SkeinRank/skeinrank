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


def _create_run(client: TestClient, run_id: str, binding_id: int) -> None:
    response = client.post(
        "/v1/agents/runs",
        json={
            "run_id": run_id,
            "status": "running",
            "trigger_type": "worker",
            "profile_name": "default_it",
            "binding_id": binding_id,
            "agent_version": "52B",
            "prompt_version": "prompt-v1",
            "openrouter_model": "openai/gpt-4o-mini",
            "summary": {"expected_documents_total": 5, "phase": "reviewing"},
        },
    )
    assert response.status_code == 201, response.text


def test_agent_run_resume_plan_batches_resume_and_retry_items(tmp_path):
    client = _client(tmp_path)
    binding_id = _seed_profile_and_binding(client)
    _create_run(client, "resume-run-001", binding_id)

    visit = client.post(
        "/v1/agents/runs/resume-run-001/document-visits",
        json={
            "source_id": "doc-001",
            "source_type": "elasticsearch_hit",
            "index_name": "default-it-docs",
            "content": "The k8s rollout was stuck after a bad image tag.",
        },
    )
    assert visit.status_code == 201, visit.text

    error_visit = client.post(
        "/v1/agents/runs/resume-run-001/document-visits",
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
        "/v1/agents/runs/resume-run-001/candidate-observations",
        json={
            "candidate_alias": "pg",
            "document_visit_id": visit.json()["id"],
            "possible_canonical": "postgresql",
            "slot": "database",
            "observation_status": "error",
            "error_message": "candidate pack could not be built",
        },
    )
    assert candidate.status_code == 201, candidate.text

    review = client.post(
        "/v1/agents/runs/resume-run-001/llm-reviews",
        json={
            "candidate_alias": "k8s",
            "candidate_observation_id": candidate.json()["id"],
            "possible_canonical": "kubernetes",
            "slot": "technology",
            "review_status": "error",
            "confidence": 0.0,
            "model": "openai/gpt-4o-mini",
            "review_hash": "reviewhash0002",
            "error_message": "provider timeout",
        },
    )
    assert review.status_code == 201, review.text

    attempt = client.post(
        "/v1/agents/runs/resume-run-001/proposal-attempts",
        json={
            "alias_value": "k8s",
            "candidate_observation_id": candidate.json()["id"],
            "llm_review_id": review.json()["id"],
            "canonical_value": "kubernetes",
            "slot": "technology",
            "attempt_status": "error",
            "confidence": 0.0,
            "idempotency_key": "resume-run-001:k8s:error",
            "error_message": "governance API unavailable",
        },
    )
    assert attempt.status_code == 201, attempt.text

    response = client.post(
        "/v1/agents/runs/resume-run-001/resume-plan",
        json={"batch_limit": 3, "retry_errors": True},
    )
    assert response.status_code == 200, response.text
    payload = response.json()

    assert payload["schema_version"] == "skeinrank.agent_run_resume_plan.v1"
    assert payload["run_id"] == "resume-run-001"
    assert payload["status"] == "running"
    assert payload["can_resume"] is True
    assert payload["limits"] == {
        "batch_limit": 3,
        "requested_source_ids": None,
        "available_work_items": 5,
        "selected_work_items": 3,
        "has_more": True,
    }
    assert payload["summary"]["by_kind"] == {
        "resume_unfinished_document": 1,
        "retry_candidate_error": 1,
        "retry_document_error": 1,
        "retry_llm_review_error": 1,
        "retry_proposal_error": 1,
    }
    assert [item["kind"] for item in payload["work_items"]] == [
        "retry_document_error",
        "resume_unfinished_document",
        "retry_candidate_error",
    ]
    assert payload["work_items"][0]["source_id"] == "doc-002"
    assert payload["work_items"][0]["tracking_table"] == "agent_document_visits"
    assert payload["work_items"][2]["candidate_alias"] == "pg"

    progress = client.get("/v1/agents/runs/resume-run-001/progress")
    assert progress.status_code == 200, progress.text
    assert progress.json()["documents"]["visited"] == 2


def test_agent_run_resume_plan_scopes_source_ids_and_retry_skipped(tmp_path):
    client = _client(tmp_path)
    binding_id = _seed_profile_and_binding(client)

    _create_run(client, "previous-run", binding_id)
    previous_visit = client.post(
        "/v1/agents/runs/previous-run/document-visits",
        json={"source_id": "doc-skip", "content": "same content"},
    )
    assert previous_visit.status_code == 201, previous_visit.text

    _create_run(client, "resume-run-002", binding_id)
    skipped_visit = client.post(
        "/v1/agents/runs/resume-run-002/document-visits",
        json={"source_id": "doc-skip", "content": "same content"},
    )
    assert skipped_visit.status_code == 201, skipped_visit.text
    assert skipped_visit.json()["visit_status"] == "unchanged_seen"
    assert skipped_visit.json()["should_scan"] is False

    default_plan = client.post(
        "/v1/agents/runs/resume-run-002/resume-plan",
        json={"source_ids": ["doc-skip", "doc-missing"]},
    )
    assert default_plan.status_code == 200, default_plan.text
    assert [item["kind"] for item in default_plan.json()["work_items"]] == [
        "resume_unfinished_document"
    ]
    assert default_plan.json()["work_items"][0]["source_id"] == "doc-missing"

    retry_skipped_plan = client.post(
        "/v1/agents/runs/resume-run-002/resume-plan",
        json={
            "source_ids": ["doc-skip", "doc-missing"],
            "retry_skipped": True,
        },
    )
    assert retry_skipped_plan.status_code == 200, retry_skipped_plan.text
    payload = retry_skipped_plan.json()

    assert payload["options"]["source_ids"] == ["doc-skip", "doc-missing"]
    assert payload["limits"]["requested_source_ids"] == 2
    assert payload["summary"]["by_kind"] == {
        "resume_unfinished_document": 1,
        "retry_skipped_document": 1,
    }
    assert [item["source_id"] for item in payload["work_items"]] == [
        "doc-skip",
        "doc-missing",
    ]


def test_agent_run_resume_plan_supports_force_rescan_without_retry_errors(tmp_path):
    client = _client(tmp_path)
    binding_id = _seed_profile_and_binding(client)
    _create_run(client, "resume-run-003", binding_id)

    visit = client.post(
        "/v1/agents/runs/resume-run-003/document-visits",
        json={
            "source_id": "doc-force",
            "source_type": "elasticsearch_hit",
            "content": "The run should be forced through a rescan.",
        },
    )
    assert visit.status_code == 201, visit.text

    response = client.post(
        "/v1/agents/runs/resume-run-003/resume-plan",
        json={"force_rescan": True, "retry_errors": False},
    )
    assert response.status_code == 200, response.text
    payload = response.json()

    assert payload["work_items"][0]["kind"] == "force_rescan"
    assert payload["work_items"][0]["source_id"] == "doc-force"
    assert "force_rescan requested" in " ".join(payload["summary"]["notes"])


def test_agent_run_resume_plan_returns_404_for_missing_run(tmp_path):
    client = _client(tmp_path)

    response = client.post("/v1/agents/runs/missing-run/resume-plan", json={})

    assert response.status_code == 404, response.text
    assert "Agent run not found" in response.json()["detail"]
