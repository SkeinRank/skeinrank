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


def _create_run(
    client: TestClient, run_id: str, binding_id: int, *, status: str = "running"
) -> None:
    response = client.post(
        "/v1/agents/runs",
        json={
            "run_id": run_id,
            "status": status,
            "trigger_type": "worker",
            "profile_name": "default_it",
            "binding_id": binding_id,
            "agent_version": "52C",
            "prompt_version": "prompt-v1",
            "openrouter_model": "openai/gpt-4o-mini",
            "artifacts_uri": "file:///tmp/run-artifacts/report-run-001",
            "summary": {
                "expected_documents_total": 4,
                "phase": "proposal_validation",
                "budget_limit_usd": 0.01,
            },
        },
    )
    assert response.status_code == 201, response.text


def test_agent_run_report_endpoint_summarizes_diagnostics_and_usage(tmp_path):
    client = _client(tmp_path)
    binding_id = _seed_profile_and_binding(client)
    _create_run(client, "report-run-001", binding_id)

    ok_visit = client.post(
        "/v1/agents/runs/report-run-001/document-visits",
        json={
            "source_id": "doc-001",
            "source_type": "elasticsearch_hit",
            "index_name": "default-it-docs",
            "content": "The k8s rollout failed after pg replica lag.",
            "evidence_windows_found": 1,
        },
    )
    assert ok_visit.status_code == 201, ok_visit.text

    error_visit = client.post(
        "/v1/agents/runs/report-run-001/document-visits",
        json={
            "source_id": "doc-002",
            "source_type": "elasticsearch_hit",
            "index_name": "default-it-docs",
            "content": "Broken payload",
            "error_message": "source document failed to parse",
        },
    )
    assert error_visit.status_code == 201, error_visit.text

    _create_run(client, "report-previous-run", binding_id, status="succeeded")
    previous_visit = client.post(
        "/v1/agents/runs/report-previous-run/document-visits",
        json={"source_id": "doc-skip", "content": "same content"},
    )
    assert previous_visit.status_code == 201, previous_visit.text
    skipped_visit = client.post(
        "/v1/agents/runs/report-run-001/document-visits",
        json={"source_id": "doc-skip", "content": "same content"},
    )
    assert skipped_visit.status_code == 201, skipped_visit.text
    assert skipped_visit.json()["visit_status"] == "unchanged_seen"

    candidate = client.post(
        "/v1/agents/runs/report-run-001/candidate-observations",
        json={
            "candidate_alias": "pg",
            "document_visit_id": ok_visit.json()["id"],
            "possible_canonical": "postgresql",
            "slot": "database",
            "observation_status": "queued_for_review",
            "document_frequency": 2,
            "evidence_windows_found": 1,
        },
    )
    assert candidate.status_code == 201, candidate.text

    review = client.post(
        "/v1/agents/runs/report-run-001/llm-reviews",
        json={
            "candidate_alias": "pg",
            "candidate_observation_id": candidate.json()["id"],
            "possible_canonical": "postgresql",
            "slot": "database",
            "review_status": "needs_evidence",
            "action": "manual_review",
            "confidence": 0.52,
            "model": "openai/gpt-4o-mini",
            "review_hash": "reportreviewhash001",
            "usage": {
                "prompt_tokens": 120,
                "completion_tokens": 30,
                "total_tokens": 150,
                "estimated_cost_usd": 0.02,
            },
        },
    )
    assert review.status_code == 201, review.text

    blocked_attempt = client.post(
        "/v1/agents/runs/report-run-001/proposal-attempts",
        json={
            "alias_value": "pg",
            "candidate_observation_id": candidate.json()["id"],
            "llm_review_id": review.json()["id"],
            "canonical_value": "postgresql",
            "slot": "database",
            "attempt_status": "validation_blocked",
            "validation_status": "blocked",
            "validation_category": "ambiguous_alias",
            "confidence": 0.52,
            "idempotency_key": "report-run-001:pg:blocked",
        },
    )
    assert blocked_attempt.status_code == 201, blocked_attempt.text

    response = client.get("/v1/agents/runs/report-run-001/report")
    assert response.status_code == 200, response.text
    payload = response.json()

    assert payload["schema_version"] == "skeinrank.agent_run_report.v1"
    assert payload["run_id"] == "report-run-001"
    assert payload["phase"] == "proposal_validation"
    assert payload["diagnostics"]["status"] == "degraded"
    assert payload["run"]["agent_name"] == "openrouter_alias_scout"
    assert payload["run"]["binding_id"] == binding_id

    assert payload["progress"]["documents"]["visited"] == 3
    assert payload["progress"]["documents"]["errors"] == 1
    assert payload["documents"]["error_samples"][0]["source_id"] == "doc-002"
    assert payload["documents"]["skipped_samples"][0]["source_id"] == "doc-skip"

    assert payload["usage"]["llm_reviews"] == 1
    assert payload["usage"]["prompt_tokens"] == 120
    assert payload["usage"]["completion_tokens"] == 30
    assert payload["usage"]["total_tokens"] == 150
    assert payload["usage"]["estimated_cost_usd"] == 0.02
    assert payload["usage"]["budget_limit_usd"] == 0.01
    assert payload["usage"]["budget_exceeded"] is True

    assert payload["proposals"]["blocked"] == 1
    assert payload["proposals"]["by_validation_category"] == {"ambiguous_alias": 1}
    assert payload["candidates"]["needs_evidence"] == 1
    assert payload["manual_review_items"][0]["candidate_alias"] == "pg"
    assert {finding["code"] for finding in payload["diagnostics"]["findings"]} >= {
        "agent_run_errors_present",
        "documents_skipped_or_unchanged",
        "manual_review_required",
        "proposal_validation_blocked",
        "budget_limit_exceeded",
    }
    assert any(
        "resume-plan" in item for item in payload["diagnostics"]["recommendations"]
    )


def test_agent_run_report_endpoint_reports_ok_for_clean_terminal_run(tmp_path):
    client = _client(tmp_path)

    create_response = client.post(
        "/v1/agents/runs",
        json={"run_id": "clean-report-run", "status": "succeeded"},
    )
    assert create_response.status_code == 201, create_response.text

    response = client.get("/v1/agents/runs/clean-report-run/report")
    assert response.status_code == 200, response.text
    payload = response.json()

    assert payload["diagnostics"]["status"] == "ok"
    assert payload["diagnostics"]["findings"] == [
        {
            "severity": "info",
            "code": "no_diagnostics_found",
            "message": (
                "No errors or manual-review blockers were found in persisted "
                "tracking rows."
            ),
            "details": {},
        }
    ]
    assert payload["progress"]["percent_complete"] == 1.0
    assert payload["errors"] == []


def test_agent_run_report_endpoint_returns_404_for_missing_run(tmp_path):
    client = _client(tmp_path)

    response = client.get("/v1/agents/runs/missing-run/report")

    assert response.status_code == 404, response.text
    assert "Agent run not found" in response.json()["detail"]
