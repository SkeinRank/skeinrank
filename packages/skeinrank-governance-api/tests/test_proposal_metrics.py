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
        )
    )
    return TestClient(app)


def _seed_profile(client: TestClient) -> None:
    response = client.post("/v1/governance/profiles", json={"name": "default_it"})
    assert response.status_code == 201, response.text
    response = client.post(
        "/v1/governance/profiles/default_it/terms",
        json={"canonical_value": "kubernetes", "slot": "tool"},
    )
    assert response.status_code == 201, response.text


def test_proposal_source_quality_aggregates_review_outcomes(tmp_path):
    client = _client(tmp_path)
    _seed_profile(client)

    first = client.post(
        "/v1/governance/profiles/default_it/suggestions",
        json={
            "canonical_value": "kubernetes",
            "alias_value": "kube",
            "slot": "tool",
            "confidence": 0.8,
            "proposal_source_type": "agent",
            "proposal_source_name": "search-log-scout",
            "idempotency_key": "search-log-scout:default_it:kube",
            "source_payload": {"query_count": 42},
        },
    )
    second = client.post(
        "/v1/governance/profiles/default_it/suggestions",
        json={
            "canonical_value": "kubernetes",
            "alias_value": "kubectl",
            "slot": "tool",
            "confidence": 0.6,
            "proposal_source_type": "agent",
            "proposal_source_name": "search-log-scout",
            "idempotency_key": "search-log-scout:default_it:kubectl",
            "source_payload": {"query_count": 9},
        },
    )
    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text

    approved = client.post(
        f"/v1/governance/profiles/default_it/suggestions/{first.json()['id']}/approve",
        json={"review_comment": "Looks useful."},
    )
    rejected = client.post(
        f"/v1/governance/profiles/default_it/suggestions/{second.json()['id']}/reject",
        json={"review_comment": "Too broad."},
    )
    assert approved.status_code == 200, approved.text
    assert rejected.status_code == 200, rejected.text

    response = client.get(
        "/v1/governance/proposals/source-quality?profile_name=default_it&proposal_source_type=agent"
    )

    assert response.status_code == 200, response.text
    assert response.json() == [
        {
            "proposal_source_type": "agent",
            "proposal_source_name": "search-log-scout",
            "proposals_total": 2,
            "pending": 0,
            "approved": 1,
            "rejected": 1,
            "validation_passed": 2,
            "validation_warning": 0,
            "validation_blocked": 0,
            "validation_unknown": 0,
            "approval_rate": 0.5,
            "rejection_rate": 0.5,
            "blocked_rate": 0.0,
            "average_confidence": 0.7,
        }
    ]


def test_proposal_metrics_are_exported_to_prometheus(tmp_path):
    client = _client(tmp_path)
    _seed_profile(client)

    suggestion = client.post(
        "/v1/governance/profiles/default_it/suggestions",
        json={
            "canonical_value": "kubernetes",
            "alias_value": "kube",
            "slot": "tool",
            "proposal_source_type": "agent",
            "proposal_source_name": "search-log-scout",
            "idempotency_key": "search-log-scout:default_it:kube",
            "source_payload": {"query_count": 42},
        },
    )
    retry = client.post(
        "/v1/governance/profiles/default_it/suggestions",
        json={
            "canonical_value": "kubernetes",
            "alias_value": "kube",
            "slot": "tool",
            "proposal_source_type": "agent",
            "proposal_source_name": "search-log-scout",
            "idempotency_key": "search-log-scout:default_it:kube",
            "source_payload": {"query_count": 42},
        },
    )
    approve = client.post(
        f"/v1/governance/profiles/default_it/suggestions/{suggestion.json()['id']}/approve"
    )
    assert suggestion.status_code == 201, suggestion.text
    assert retry.status_code == 200, retry.text
    assert approve.status_code == 200, approve.text

    metrics = client.get("/metrics")

    assert metrics.status_code == 200
    body = metrics.text
    assert "skeinrank_proposals_submitted_total" in body
    assert (
        'skeinrank_proposals_submitted_total{source_type="agent",suggestion_type="alias",validation_status="passed",outcome="created"} 1'
        in body
    )
    assert (
        'skeinrank_proposals_submitted_total{source_type="agent",suggestion_type="alias",validation_status="passed",outcome="idempotent_retry"} 1'
        in body
    )
    assert (
        'skeinrank_proposal_reviews_total{source_type="agent",decision="approved"} 1'
        in body
    )
