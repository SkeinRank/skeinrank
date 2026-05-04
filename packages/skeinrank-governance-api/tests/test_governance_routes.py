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


def test_profile_term_alias_workflow(tmp_path):
    client = _client(tmp_path)

    profile_response = client.post(
        "/v1/governance/profiles",
        json={"name": "default_it", "description": "Default IT terms"},
    )
    assert profile_response.status_code == 201
    assert profile_response.json()["name"] == "default_it"
    assert profile_response.json()["normalized_name"] == "default_it"

    profiles_response = client.get("/v1/governance/profiles")
    assert profiles_response.status_code == 200
    assert [item["name"] for item in profiles_response.json()] == ["default_it"]

    term_response = client.post(
        "/v1/governance/profiles/default_it/terms",
        json={"canonical_value": "kubernetes", "slot": "tool"},
    )
    assert term_response.status_code == 201
    assert term_response.json()["canonical_value"] == "kubernetes"
    assert term_response.json()["slot"] == "TOOL"
    assert term_response.json()["aliases"] == []

    alias_response = client.post(
        "/v1/governance/profiles/default_it/terms/kubernetes/aliases",
        json={"alias_value": "k8s", "confidence": 0.97},
    )
    assert alias_response.status_code == 201
    assert alias_response.json()["alias_value"] == "k8s"
    assert alias_response.json()["normalized_alias"] == "k8s"
    assert alias_response.json()["confidence"] == 0.97

    terms_response = client.get("/v1/governance/profiles/default_it/terms")
    assert terms_response.status_code == 200
    terms = terms_response.json()
    assert len(terms) == 1
    assert terms[0]["canonical_value"] == "kubernetes"
    assert terms[0]["aliases"][0]["alias_value"] == "k8s"

    term_detail_response = client.get(
        "/v1/governance/profiles/default_it/terms/kubernetes"
    )
    assert term_detail_response.status_code == 200
    assert term_detail_response.json()["aliases"][0]["alias_value"] == "k8s"


def test_duplicate_profile_returns_conflict(tmp_path):
    client = _client(tmp_path)

    assert (
        client.post("/v1/governance/profiles", json={"name": "default_it"}).status_code
        == 201
    )

    response = client.post("/v1/governance/profiles", json={"name": "Default IT"})

    assert response.status_code == 409
    assert "Profile already exists" in response.json()["detail"]


def test_missing_profile_returns_404_for_term_create(tmp_path):
    client = _client(tmp_path)

    response = client.post(
        "/v1/governance/profiles/missing/terms",
        json={"canonical_value": "kubernetes", "slot": "TOOL"},
    )

    assert response.status_code == 404
    assert "Profile not found" in response.json()["detail"]


def test_alias_collision_returns_conflict(tmp_path):
    client = _client(tmp_path)
    client.post("/v1/governance/profiles", json={"name": "default_it"})
    client.post(
        "/v1/governance/profiles/default_it/terms",
        json={"canonical_value": "postgresql", "slot": "DB"},
    )
    client.post(
        "/v1/governance/profiles/default_it/terms",
        json={"canonical_value": "payment-gateway", "slot": "SERVICE"},
    )
    first = client.post(
        "/v1/governance/profiles/default_it/terms/postgresql/aliases",
        json={"alias_value": "pg"},
    )
    assert first.status_code == 201

    response = client.post(
        "/v1/governance/profiles/default_it/terms/payment-gateway/aliases",
        json={"alias_value": "pg"},
    )

    assert response.status_code == 409
    assert "Alias already exists" in response.json()["detail"]


def test_missing_term_returns_404_for_alias_create(tmp_path):
    client = _client(tmp_path)
    client.post("/v1/governance/profiles", json={"name": "default_it"})

    response = client.post(
        "/v1/governance/profiles/default_it/terms/kubernetes/aliases",
        json={"alias_value": "k8s"},
    )

    assert response.status_code == 404
    assert "Canonical term not found" in response.json()["detail"]
