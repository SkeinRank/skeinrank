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


def _seed_profile(client: TestClient) -> None:
    response = client.post("/v1/governance/profiles", json={"name": "default_it"})
    assert response.status_code == 201, response.text
    response = client.post(
        "/v1/governance/profiles/default_it/terms",
        json={"canonical_value": "kubernetes", "slot": "tool"},
    )
    assert response.status_code == 201, response.text


def test_suggestion_response_exposes_lifecycle_state(tmp_path):
    client = _client(tmp_path)
    _seed_profile(client)

    response = client.post(
        "/v1/governance/profiles/default_it/suggestions",
        json={
            "canonical_value": "kubernetes",
            "alias_value": "kube",
            "slot": "tool",
            "validation_summary": {
                "schema_version": "skeinrank.proposal_validation.v1",
                "status": "passed",
                "counts": {"passed": 3, "warning": 0, "blocked": 0},
                "checks": {},
            },
        },
    )

    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["status"] == "pending"
    assert payload["validation_status"] == "passed"
    assert payload["lifecycle_status"] == "pending_reviewable"
    assert payload["can_approve"] is True
    assert payload["can_apply"] is True


def test_single_approval_rejects_blocked_validation(tmp_path):
    client = _client(tmp_path)
    _seed_profile(client)

    suggestion = client.post(
        "/v1/governance/profiles/default_it/suggestions",
        json={
            "canonical_value": "kubernetes",
            "alias_value": "kube",
            "slot": "tool",
            "validation_summary": {
                "schema_version": "skeinrank.proposal_validation.v1",
                "status": "blocked",
                "counts": {"passed": 2, "warning": 0, "blocked": 1},
                "checks": {
                    "stop_list": {
                        "status": "blocked",
                        "severity": "error",
                        "message": "Alias is blocked by stop list.",
                    }
                },
            },
        },
    )
    assert suggestion.status_code == 201, suggestion.text
    suggestion_payload = suggestion.json()
    assert suggestion_payload["lifecycle_status"] == "pending_blocked"
    assert suggestion_payload["can_approve"] is False

    approve = client.post(
        f"/v1/governance/profiles/default_it/suggestions/{suggestion_payload['id']}/approve",
        json={"review_comment": "Do not approve blocked proposals."},
    )

    assert approve.status_code == 409, approve.text
    assert "validation is blocked" in approve.json()["detail"]


def test_single_approval_requires_explicit_warning_override(tmp_path):
    client = _client(tmp_path)
    _seed_profile(client)

    suggestion = client.post(
        "/v1/governance/profiles/default_it/suggestions",
        json={
            "canonical_value": "kubernetes",
            "alias_value": "kube",
            "slot": "tool",
            "proposal_source_type": "agent",
            "proposal_source_name": "unit-test-scout",
            "source_payload": {"candidate_alias": "kube"},
            "validation_summary": {
                "schema_version": "skeinrank.proposal_validation.v1",
                "status": "warning",
                "counts": {"passed": 2, "warning": 1, "blocked": 0},
                "checks": {
                    "alias_state": {
                        "status": "warning",
                        "severity": "warning",
                        "message": "Alias already maps to this canonical in another source.",
                    }
                },
            },
        },
    )
    assert suggestion.status_code == 201, suggestion.text
    suggestion_payload = suggestion.json()
    assert suggestion_payload["lifecycle_status"] == "pending_needs_review"
    assert suggestion_payload["can_approve"] is False

    approve_without_override = client.post(
        f"/v1/governance/profiles/default_it/suggestions/{suggestion_payload['id']}/approve",
        json={"review_comment": "Needs explicit override."},
    )
    assert approve_without_override.status_code == 409

    approve_with_override = client.post(
        f"/v1/governance/profiles/default_it/suggestions/{suggestion_payload['id']}/approve",
        json={"review_comment": "Reviewed warning.", "allow_warnings": True},
    )
    assert approve_with_override.status_code == 200, approve_with_override.text
    payload = approve_with_override.json()
    assert payload["status"] == "approved"
    assert payload["lifecycle_status"] == "approved_applied"
    assert payload["can_approve"] is False
