from __future__ import annotations

import json

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


def _seed_run_observation(client: TestClient) -> tuple[int, int]:
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
            "run_id": "run-dataset-001",
            "status": "running",
            "trigger_type": "scheduled",
            "profile_name": "default_it",
            "binding_id": binding.json()["id"],
            "agent_version": "dataset-v1",
            "prompt_version": "alias-scout-v2",
            "openrouter_model": "openai/gpt-4o-mini",
        },
    )
    assert run.status_code == 201, run.text
    visit = client.post(
        "/v1/agents/runs/run-dataset-001/document-visits",
        json={
            "source_id": "doc-001",
            "source_type": "elasticsearch_hit",
            "index_name": "default-it-docs",
            "content": "payments-core replaced the old checkout service name.",
        },
    )
    assert visit.status_code == 201, visit.text
    observation = client.post(
        "/v1/agents/runs/run-dataset-001/candidate-observations",
        json={
            "candidate_alias": "payments-core",
            "document_visit_id": visit.json()["id"],
            "possible_canonical": "checkout",
            "slot": "service",
            "observation_status": "queued_for_review",
            "candidate_pack": {"cluster_id": "cluster-payments-core"},
            "evidence_windows": [
                {
                    "source_id": "doc-001",
                    "field": "body",
                    "text": "payments-core replaced the old checkout service name.",
                    "metadata": {"evidence_role": "positive"},
                }
            ],
        },
    )
    assert observation.status_code == 201, observation.text
    return binding.json()["id"], observation.json()["id"]


def test_review_dataset_events_are_stored_and_exported_after_review(tmp_path):
    client = _client(tmp_path)
    binding_id, observation_id = _seed_run_observation(client)

    review = client.post(
        "/v1/agents/runs/run-dataset-001/llm-reviews",
        json={
            "candidate_alias": "payments-core",
            "candidate_observation_id": observation_id,
            "review_status": "proposed",
            "action": "propose",
            "confidence": 0.88,
            "response_id": "resp-dataset-001",
            "judgment": {
                "decision_trace": ["new form appears in evidence"],
                "proposal_payload": {
                    "alias_value": "payments-core",
                    "canonical_value": "checkout",
                    "slot": "SERVICE",
                },
            },
        },
    )
    assert review.status_code == 201, review.text

    suggestion = client.post(
        "/v1/governance/profiles/default_it/suggestions",
        json={
            "canonical_value": "checkout",
            "alias_value": "payments-core",
            "slot": "service",
            "confidence": 0.88,
            "source": "discovery",
            "binding_id": binding_id,
            "proposal_source_type": "agent",
            "proposal_source_name": "openrouter-alias-scout",
            "idempotency_key": "dataset:payments-core",
            "source_payload": {"candidate_alias": "payments-core"},
            "validation_summary": {"status": "passed", "checks": {}},
        },
    )
    assert suggestion.status_code == 201, suggestion.text

    attempt = client.post(
        "/v1/agents/runs/run-dataset-001/proposal-attempts",
        json={
            "alias_value": "payments-core",
            "candidate_observation_id": observation_id,
            "llm_review_id": review.json()["id"],
            "governance_suggestion_id": suggestion.json()["id"],
            "canonical_value": "checkout",
            "slot": "service",
            "attempt_status": "submitted",
            "validation_status": "passed",
            "validation_category": "validation_passed",
            "confidence": 0.88,
            "idempotency_key": "dataset:payments-core",
            "submitted": True,
            "source_payload": {
                "candidate_cluster": {"cluster_id": "cluster-payments-core"}
            },
        },
    )
    assert attempt.status_code == 201, attempt.text

    events = client.get("/v1/agents/review-dataset/events?run_id=run-dataset-001")
    assert events.status_code == 200, events.text
    event_types = [item["event_type"] for item in events.json()]
    assert event_types == ["model_judgment", "proposal_attempt"]
    proposal_event = events.json()[1]
    assert proposal_event["dataset_status"] == "pending_review"
    assert proposal_event["input_pack"]["candidate_pack"] == {
        "cluster_id": "cluster-payments-core"
    }
    assert proposal_event["model_output"]["judgment"]["decision_trace"] == [
        "new form appears in evidence"
    ]

    rejected = client.post(
        "/v1/governance/profiles/default_it/suggestions/"
        f"{suggestion.json()['id']}/reject",
        json={"review_comment": "canonical direction needs human confirmation"},
    )
    assert rejected.status_code == 200, rejected.text

    reviewed_events = client.get(
        "/v1/agents/review-dataset/events?run_id=run-dataset-001&status=reviewed"
    )
    assert reviewed_events.status_code == 200, reviewed_events.text
    assert len(reviewed_events.json()) == 1
    reviewed = reviewed_events.json()[0]
    assert reviewed["event_type"] == "proposal_attempt"
    assert reviewed["human_decision"]["decision"] == "rejected"
    assert reviewed["human_decision"]["review_comment"] == (
        "canonical direction needs human confirmation"
    )

    export = client.get(
        "/v1/agents/review-dataset/events/export.jsonl?run_id=run-dataset-001"
    )
    assert export.status_code == 200, export.text
    assert export.headers["content-type"].startswith("application/x-ndjson")
    lines = [json.loads(line) for line in export.text.splitlines()]
    assert len(lines) == 1
    assert lines[0]["event_type"] == "proposal_attempt"
    assert lines[0]["human_decision"]["decision"] == "rejected"
    assert lines[0]["input"]["candidate_pack"] == {
        "cluster_id": "cluster-payments-core"
    }


def test_review_dataset_export_defaults_to_reviewed_events(tmp_path):
    client = _client(tmp_path)
    _binding_id, observation_id = _seed_run_observation(client)

    review = client.post(
        "/v1/agents/runs/run-dataset-001/llm-reviews",
        json={
            "candidate_alias": "payments-core",
            "candidate_observation_id": observation_id,
            "review_status": "needs_evidence",
            "confidence": 0.3,
        },
    )
    assert review.status_code == 201, review.text

    pending_export = client.get(
        "/v1/agents/review-dataset/events/export.jsonl?run_id=run-dataset-001"
    )
    assert pending_export.status_code == 200, pending_export.text
    assert pending_export.text == ""

    all_events = client.get(
        "/v1/agents/review-dataset/events/export.jsonl"
        "?run_id=run-dataset-001&status=pending_review"
    )
    assert all_events.status_code == 200, all_events.text
    line = json.loads(all_events.text)
    assert line["event_type"] == "model_judgment"
    assert line["dataset_status"] == "pending_review"
