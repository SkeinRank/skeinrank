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
    for canonical, slot in [
        ("kubernetes", "tool"),
        ("postgresql", "database"),
        ("page", "document_component"),
    ]:
        response = client.post(
            "/v1/governance/profiles/default_it/terms",
            json={"canonical_value": canonical, "slot": slot},
        )
        assert response.status_code == 201, response.text


def _create_binding(client: TestClient) -> int:
    response = client.post(
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
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_conflicting_active_alias_proposal_creates_ambiguous_candidates(tmp_path):
    client = _client(tmp_path)
    _seed_profile(client)
    active_alias = client.post(
        "/v1/governance/profiles/default_it/terms/kubernetes/aliases",
        json={"alias_value": "pg", "confidence": 0.97},
    )
    assert active_alias.status_code == 201, active_alias.text

    suggestion = client.post(
        "/v1/governance/profiles/default_it/suggestions",
        json={
            "canonical_value": "postgresql",
            "alias_value": "PG",
            "slot": "database",
            "proposal_source_type": "agent",
            "proposal_source_name": "search-log-scout",
            "idempotency_key": "search-log-scout:default_it:pg",
            "source_payload": {"query_count": 42},
        },
    )

    assert suggestion.status_code == 201, suggestion.text
    assert suggestion.json()["validation_summary"]["status"] == "blocked"

    ambiguous = client.get("/v1/governance/profiles/default_it/ambiguous-aliases/pg")
    assert ambiguous.status_code == 200, ambiguous.text
    payload = ambiguous.json()
    assert payload["normalized_surface"] == "pg"
    candidates = {
        (candidate["normalized_canonical"], candidate["slot"]): candidate
        for candidate in payload["candidates"]
    }
    assert set(candidates) == {
        ("kubernetes", "TOOL"),
        ("postgresql", "DATABASE"),
    }
    assert candidates[("kubernetes", "TOOL")]["source"] == "active_alias"
    assert candidates[("kubernetes", "TOOL")]["status"] == "preferred"
    assert candidates[("postgresql", "DATABASE")]["source"] == "suggestion"
    assert (
        candidates[("postgresql", "DATABASE")]["evidence"]["suggestion_id"]
        == suggestion.json()["id"]
    )


def test_pending_proposal_disagreement_creates_ambiguous_candidates(tmp_path):
    client = _client(tmp_path)
    _seed_profile(client)

    first = client.post(
        "/v1/governance/profiles/default_it/suggestions",
        json={
            "canonical_value": "postgresql",
            "alias_value": "pg",
            "slot": "database",
            "proposal_source_type": "agent",
            "idempotency_key": "agent:pg:postgresql",
        },
    )
    assert first.status_code == 201, first.text
    assert (
        client.get(
            "/v1/governance/profiles/default_it/ambiguous-aliases/pg"
        ).status_code
        == 404
    )

    second = client.post(
        "/v1/governance/profiles/default_it/suggestions",
        json={
            "canonical_value": "page",
            "alias_value": "PG",
            "slot": "document_component",
            "proposal_source_type": "agent",
            "idempotency_key": "agent:pg:page",
        },
    )
    assert second.status_code == 201, second.text

    ambiguous = client.get("/v1/governance/profiles/default_it/ambiguous-aliases/pg")
    assert ambiguous.status_code == 200, ambiguous.text
    candidates = {
        (candidate["normalized_canonical"], candidate["slot"])
        for candidate in ambiguous.json()["candidates"]
    }
    assert candidates == {
        ("postgresql", "DATABASE"),
        ("page", "DOCUMENT_COMPONENT"),
    }


def test_agent_tool_conflicting_alias_creates_ambiguous_candidates(tmp_path):
    client = _client(tmp_path)
    _seed_profile(client)
    binding_id = _create_binding(client)
    active_alias = client.post(
        "/v1/governance/profiles/default_it/terms/kubernetes/aliases",
        json={"alias_value": "pg"},
    )
    assert active_alias.status_code == 201, active_alias.text

    response = client.post(
        "/v1/tools/suggest-alias",
        json={
            "binding_id": binding_id,
            "canonical_value": "postgresql",
            "alias_value": "pg",
            "slot": "database",
            "proposal_source_name": "search-log-scout",
            "idempotency_key": "search-log-scout:default_it:pg",
            "source_payload": {"query_count": 7},
        },
    )

    assert response.status_code == 201, response.text
    assert response.json()["created"] is True
    ambiguous = client.get("/v1/governance/profiles/default_it/ambiguous-aliases/pg")
    assert ambiguous.status_code == 200, ambiguous.text
    assert len(ambiguous.json()["candidates"]) == 2
