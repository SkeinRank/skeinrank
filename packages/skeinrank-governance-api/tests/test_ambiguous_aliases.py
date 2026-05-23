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
    assert (
        client.post("/v1/governance/profiles", json={"name": "default_it"}).status_code
        == 201
    )
    for canonical, slot in [("postgresql", "database"), ("page", "document_component")]:
        response = client.post(
            "/v1/governance/profiles/default_it/terms",
            json={"canonical_value": canonical, "slot": slot},
        )
        assert response.status_code == 201, response.text


def test_create_and_list_ambiguous_alias_candidates(tmp_path):
    client = _client(tmp_path)
    _seed_profile(client)

    response = client.post(
        "/v1/governance/profiles/default_it/ambiguous-aliases",
        json={
            "surface_value": "PG",
            "candidates": [
                {
                    "canonical_value": "postgresql",
                    "slot": "database",
                    "source": "active_alias",
                    "confidence": 0.95,
                    "status": "preferred",
                    "evidence": {"reason": "infra docs"},
                },
                {
                    "canonical_value": "page",
                    "slot": "document_component",
                    "source": "suggestion",
                    "confidence": 0.61,
                },
            ],
        },
    )

    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["surface_value"] == "PG"
    assert payload["normalized_surface"] == "pg"
    assert payload["status"] == "open"
    assert [candidate["canonical_value"] for candidate in payload["candidates"]] == [
        "postgresql",
        "page",
    ]
    assert payload["candidates"][0]["slot"] == "DATABASE"
    assert payload["candidates"][0]["status"] == "preferred"
    assert payload["candidates"][0]["evidence"] == {"reason": "infra docs"}

    listed = client.get("/v1/governance/profiles/default_it/ambiguous-aliases")
    assert listed.status_code == 200
    assert [item["normalized_surface"] for item in listed.json()] == ["pg"]


def test_upsert_ambiguous_alias_updates_candidates_idempotently(tmp_path):
    client = _client(tmp_path)
    _seed_profile(client)

    first = client.post(
        "/v1/governance/profiles/default_it/ambiguous-aliases",
        json={
            "surface_value": "pg",
            "candidates": [
                {"canonical_value": "postgresql", "slot": "database"},
            ],
        },
    )
    second = client.post(
        "/v1/governance/profiles/default_it/ambiguous-aliases",
        json={
            "surface_value": "pg",
            "review_note": "Captured from conflict report",
            "candidates": [
                {"canonical_value": "postgresql", "slot": "database"},
                {"canonical_value": "page", "slot": "document_component"},
            ],
        },
    )

    assert first.status_code == 201, first.text
    assert second.status_code == 200, second.text
    payload = second.json()
    assert payload["review_note"] == "Captured from conflict report"
    assert len(payload["candidates"]) == 2
    assert {
        candidate["normalized_canonical"] for candidate in payload["candidates"]
    } == {
        "postgresql",
        "page",
    }


def test_update_ambiguous_alias_review_state(tmp_path):
    client = _client(tmp_path)
    _seed_profile(client)
    created = client.post(
        "/v1/governance/profiles/default_it/ambiguous-aliases",
        json={
            "surface_value": "pg",
            "candidates": [{"canonical_value": "postgresql", "slot": "database"}],
        },
    )
    assert created.status_code == 201

    response = client.patch(
        "/v1/governance/profiles/default_it/ambiguous-aliases/PG",
        json={"status": "resolved", "review_note": "Binding policy will decide."},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "resolved"
    assert payload["review_note"] == "Binding policy will decide."
    assert payload["reviewed_by"] == "local_dev"


def test_ambiguous_alias_rejects_invalid_candidate_source(tmp_path):
    client = _client(tmp_path)
    _seed_profile(client)

    response = client.post(
        "/v1/governance/profiles/default_it/ambiguous-aliases",
        json={
            "surface_value": "pg",
            "candidates": [
                {
                    "canonical_value": "postgresql",
                    "slot": "database",
                    "source": "unknown",
                }
            ],
        },
    )

    assert response.status_code == 422
    assert "Invalid ambiguous alias candidate source" in response.json()["detail"]
