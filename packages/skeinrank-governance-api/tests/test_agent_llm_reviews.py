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


def _seed_run_visit_and_observation(client: TestClient) -> int:
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
            "agent_version": "llm-review-v1",
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
        },
    )
    assert visit.status_code == 201, visit.text
    observation = client.post(
        "/v1/agents/runs/run-001/candidate-observations",
        json={
            "candidate_alias": "k8s",
            "document_visit_id": visit.json()["id"],
            "possible_canonical": "kubernetes",
            "slot": "technology",
            "observation_status": "queued_for_review",
        },
    )
    assert observation.status_code == 201, observation.text
    return observation.json()["id"]


def test_llm_review_and_proposal_attempt_are_persisted(tmp_path):
    client = _client(tmp_path)
    observation_id = _seed_run_visit_and_observation(client)

    review = client.post(
        "/v1/agents/runs/run-001/llm-reviews",
        json={
            "candidate_alias": "k8s",
            "candidate_observation_id": observation_id,
            "review_status": "proposed",
            "action": "propose",
            "confidence": 0.9,
            "response_id": "resp-001",
            "usage": {"total_tokens": 321},
            "judgment": {"reason": "evidence matches Kubernetes"},
            "raw_response": {"id": "resp-001"},
        },
    )
    assert review.status_code == 201, review.text
    review_payload = review.json()
    assert review_payload["candidate_alias"] == "k8s"
    assert review_payload["possible_canonical"] == "kubernetes"
    assert review_payload["slot"] == "TECHNOLOGY"
    assert review_payload["review_status"] == "proposed"
    assert review_payload["model"] == "openai/gpt-4o-mini"
    assert review_payload["usage"] == {"total_tokens": 321}
    assert review_payload["review_hash"]

    attempt = client.post(
        "/v1/agents/runs/run-001/proposal-attempts",
        json={
            "alias_value": "k8s",
            "candidate_observation_id": observation_id,
            "llm_review_id": review_payload["id"],
            "canonical_value": "kubernetes",
            "slot": "technology",
            "attempt_status": "validation_passed",
            "validation_status": "passed",
            "validation_category": "validation_passed",
            "confidence": 0.9,
            "idempotency_key": "openrouter-alias-scout:run-001:k8s",
            "validation_response": {"status": "passed"},
            "source_payload": {"candidate_alias": "k8s"},
        },
    )
    assert attempt.status_code == 201, attempt.text
    attempt_payload = attempt.json()
    assert attempt_payload["alias_value"] == "k8s"
    assert attempt_payload["canonical_value"] == "kubernetes"
    assert attempt_payload["attempt_status"] == "validation_passed"
    assert attempt_payload["validation_response"] == {"status": "passed"}
    assert attempt_payload["submitted"] is False

    reviews = client.get("/v1/agents/runs/run-001/llm-reviews?status=proposed")
    assert reviews.status_code == 200, reviews.text
    assert [item["candidate_alias"] for item in reviews.json()] == ["k8s"]

    attempts = client.get(
        "/v1/agents/runs/run-001/proposal-attempts?status=validation_passed"
    )
    assert attempts.status_code == 200, attempts.text
    assert [item["alias_value"] for item in attempts.json()] == ["k8s"]


def test_llm_review_and_proposal_attempt_reject_duplicates_and_wrong_links(tmp_path):
    client = _client(tmp_path)
    observation_id = _seed_run_visit_and_observation(client)

    first = client.post(
        "/v1/agents/runs/run-001/llm-reviews",
        json={
            "candidate_alias": "k8s",
            "candidate_observation_id": observation_id,
            "review_status": "proposed",
            "review_hash": "review123456789",
        },
    )
    assert first.status_code == 201, first.text
    duplicate = client.post(
        "/v1/agents/runs/run-001/llm-reviews",
        json={
            "candidate_alias": "K8S",
            "candidate_observation_id": observation_id,
            "review_status": "proposed",
            "review_hash": "review123456789",
        },
    )
    assert duplicate.status_code == 409, duplicate.text

    attempt = client.post(
        "/v1/agents/runs/run-001/proposal-attempts",
        json={
            "alias_value": "k8s",
            "llm_review_id": first.json()["id"],
            "idempotency_key": "run-001:k8s",
        },
    )
    assert attempt.status_code == 201, attempt.text
    duplicate_attempt = client.post(
        "/v1/agents/runs/run-001/proposal-attempts",
        json={
            "alias_value": "k8s",
            "llm_review_id": first.json()["id"],
            "idempotency_key": "run-001:k8s",
        },
    )
    assert duplicate_attempt.status_code == 409, duplicate_attempt.text

    other_run = client.post("/v1/agents/runs", json={"run_id": "run-002"})
    assert other_run.status_code == 201, other_run.text
    wrong_link = client.post(
        "/v1/agents/runs/run-002/proposal-attempts",
        json={"alias_value": "pg", "llm_review_id": first.json()["id"]},
    )
    assert wrong_link.status_code == 400, wrong_link.text
    assert "different agent run" in wrong_link.json()["detail"]


def test_llm_review_status_filters_and_validation(tmp_path):
    client = _client(tmp_path)
    _seed_run_visit_and_observation(client)

    for alias, status in [("pg", "needs_evidence"), ("k8s", "proposed")]:
        response = client.post(
            "/v1/agents/runs/run-001/llm-reviews",
            json={"candidate_alias": alias, "review_status": status},
        )
        assert response.status_code == 201, response.text

    filtered = client.get("/v1/agents/runs/run-001/llm-reviews?candidate_alias=K8S")
    assert filtered.status_code == 200, filtered.text
    assert [item["candidate_alias"] for item in filtered.json()] == ["k8s"]

    invalid = client.post(
        "/v1/agents/runs/run-001/proposal-attempts",
        json={"alias_value": "k8s", "attempt_status": "done"},
    )
    assert invalid.status_code == 400, invalid.text
    assert "Invalid proposal attempt status" in invalid.json()["detail"]
