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


def _create_term(client: TestClient, profile: str, canonical: str, slot: str) -> None:
    response = client.post(
        f"/v1/governance/profiles/{profile}/terms",
        json={"canonical_value": canonical, "slot": slot},
    )
    assert response.status_code == 201, response.text


def _create_alias(client: TestClient, profile: str, canonical: str, alias: str) -> None:
    response = client.post(
        f"/v1/governance/profiles/{profile}/terms/{canonical}/aliases",
        json={"alias_value": alias},
    )
    assert response.status_code == 201, response.text


def test_conflict_report_detects_cross_profile_alias_mapping(tmp_path):
    client = _client(tmp_path)
    assert (
        client.post("/v1/governance/profiles", json={"name": "infra"}).status_code
        == 201
    )
    assert (
        client.post("/v1/governance/profiles", json={"name": "docs"}).status_code == 201
    )
    _create_term(client, "infra", "postgresql", "database")
    _create_term(client, "docs", "page", "document_component")
    _create_alias(client, "infra", "postgresql", "pg")
    _create_alias(client, "docs", "page", "pg")

    response = client.get("/v1/governance/conflicts")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    conflict = payload["conflicts"][0]
    assert conflict["conflict_type"] == "alias_maps_to_multiple_canonicals"
    assert conflict["normalized_value"] == "pg"
    assert conflict["scope"] == "cross_profile"
    assert {entity["canonical_value"] for entity in conflict["entities"]} == {
        "postgresql",
        "page",
    }


def test_conflict_report_detects_stop_list_drift(tmp_path):
    client = _client(tmp_path)
    assert (
        client.post("/v1/governance/profiles", json={"name": "default_it"}).status_code
        == 201
    )
    _create_term(client, "default_it", "kubernetes", "tool")
    _create_alias(client, "default_it", "kubernetes", "k8s")
    stop = client.post(
        "/v1/governance/profiles/default_it/stop-list",
        json={"value": "k8s", "target": "alias", "reason": "too noisy"},
    )
    assert stop.status_code == 201

    response = client.get("/v1/governance/conflicts?profile_name=default_it")

    assert response.status_code == 200
    payload = response.json()
    assert payload["profile_name"] == "default_it"
    assert payload["total"] == 1
    conflict = payload["conflicts"][0]
    assert conflict["conflict_type"] == "alias_stop_list_collision"
    assert conflict["normalized_value"] == "k8s"
    assert {entity["entity_type"] for entity in conflict["entities"]} == {
        "alias",
        "stop_list_entry",
    }


def test_conflict_report_detects_pending_proposal_vs_active_alias(tmp_path):
    client = _client(tmp_path)
    assert (
        client.post("/v1/governance/profiles", json={"name": "default_it"}).status_code
        == 201
    )
    _create_term(client, "default_it", "postgresql", "database")
    _create_term(client, "default_it", "page", "document_component")
    _create_alias(client, "default_it", "postgresql", "pg")

    suggestion = client.post(
        "/v1/governance/profiles/default_it/suggestions",
        json={
            "canonical_value": "page",
            "alias_value": "pg",
            "slot": "document_component",
            "proposal_source_type": "agent",
            "proposal_source_name": "docs-scout",
        },
    )
    assert suggestion.status_code == 201, suggestion.text
    assert suggestion.json()["validation_summary"]["status"] == "blocked"

    response = client.get("/v1/governance/conflicts?profile_name=default_it")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    conflict = payload["conflicts"][0]
    assert conflict["conflict_type"] == "pending_alias_conflicts_with_active_alias"
    assert {entity["entity_type"] for entity in conflict["entities"]} == {
        "suggestion",
        "alias",
    }


def test_conflict_report_can_skip_suggestions(tmp_path):
    client = _client(tmp_path)
    assert (
        client.post("/v1/governance/profiles", json={"name": "default_it"}).status_code
        == 201
    )
    _create_term(client, "default_it", "postgresql", "database")
    _create_term(client, "default_it", "page", "document_component")
    _create_alias(client, "default_it", "postgresql", "pg")
    assert (
        client.post(
            "/v1/governance/profiles/default_it/suggestions",
            json={
                "canonical_value": "page",
                "alias_value": "pg",
                "slot": "document_component",
            },
        ).status_code
        == 201
    )

    response = client.get(
        "/v1/governance/conflicts?profile_name=default_it&include_suggestions=false"
    )

    assert response.status_code == 200
    assert response.json()["include_suggestions"] is False
    assert response.json()["total"] == 0


def test_conflict_report_missing_profile_returns_404(tmp_path):
    client = _client(tmp_path)

    response = client.get("/v1/governance/conflicts?profile_name=missing")

    assert response.status_code == 404
    assert "Profile not found" in response.json()["detail"]


def test_conflict_report_includes_default_severity_and_review_state(tmp_path):
    client = _client(tmp_path)
    assert (
        client.post("/v1/governance/profiles", json={"name": "infra"}).status_code
        == 201
    )
    assert (
        client.post("/v1/governance/profiles", json={"name": "docs"}).status_code == 201
    )
    _create_term(client, "infra", "postgresql", "database")
    _create_term(client, "docs", "page", "document_component")
    _create_alias(client, "infra", "postgresql", "pg")
    _create_alias(client, "docs", "page", "pg")

    response = client.get("/v1/governance/conflicts")

    assert response.status_code == 200
    conflict = response.json()["conflicts"][0]
    assert len(conflict["fingerprint"]) == 64
    assert conflict["severity"] == "high"
    assert conflict["review_status"] == "open"
    assert conflict["review_note"] is None
    assert conflict["reviewed_by"] is None
    assert conflict["reviewed_at"] is None


def test_conflict_review_state_can_be_updated_and_read_back(tmp_path):
    client = _client(tmp_path)
    assert (
        client.post("/v1/governance/profiles", json={"name": "default_it"}).status_code
        == 201
    )
    _create_term(client, "default_it", "kubernetes", "tool")
    _create_alias(client, "default_it", "kubernetes", "k8s")
    stop = client.post(
        "/v1/governance/profiles/default_it/stop-list",
        json={"value": "k8s", "target": "alias", "reason": "too noisy"},
    )
    assert stop.status_code == 201
    conflict = client.get("/v1/governance/conflicts?profile_name=default_it").json()[
        "conflicts"
    ][0]

    reviewed = client.patch(
        f"/v1/governance/conflicts/{conflict['fingerprint']}/review?profile_name=default_it",
        json={
            "severity": "medium",
            "review_status": "ignored",
            "review_note": "Known legacy alias kept for compatibility.",
        },
    )

    assert reviewed.status_code == 200, reviewed.text
    reviewed_payload = reviewed.json()
    assert reviewed_payload["fingerprint"] == conflict["fingerprint"]
    assert reviewed_payload["severity"] == "medium"
    assert reviewed_payload["review_status"] == "ignored"
    assert (
        reviewed_payload["review_note"] == "Known legacy alias kept for compatibility."
    )
    assert reviewed_payload["reviewed_by"] == "local_dev"
    assert reviewed_payload["reviewed_at"] is not None

    response = client.get("/v1/governance/conflicts?profile_name=default_it")
    assert response.status_code == 200
    persisted = response.json()["conflicts"][0]
    assert persisted["severity"] == "medium"
    assert persisted["review_status"] == "ignored"
    assert persisted["review_note"] == "Known legacy alias kept for compatibility."


def test_conflict_review_rejects_unknown_fingerprint(tmp_path):
    client = _client(tmp_path)

    response = client.patch(
        "/v1/governance/conflicts/missing/review",
        json={"review_status": "ignored"},
    )

    assert response.status_code == 404
    assert "Current conflict not found" in response.json()["detail"]
