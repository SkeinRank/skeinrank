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
    client.post("/v1/governance/profiles", json={"name": "default_it"})
    client.post(
        "/v1/governance/profiles/default_it/terms",
        json={"canonical_value": "kubernetes", "slot": "tool"},
    )
    client.post(
        "/v1/governance/profiles/default_it/terms/kubernetes/aliases",
        json={"alias_value": "k8s", "confidence": 0.97},
    )


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


def test_agent_tools_list_binding_contexts(tmp_path):
    client = _client(tmp_path)
    _seed_profile(client)
    binding_id = _create_binding(client)

    response = client.get("/v1/tools/bindings")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["id"] == binding_id
    assert payload[0]["profile_name"] == "default_it"
    assert payload[0]["text_fields"] == ["title", "body"]
    assert payload[0]["snapshot_status"] == "uninitialized"


def test_agent_tools_validate_alias_without_persisting(tmp_path):
    client = _client(tmp_path)
    _seed_profile(client)
    binding_id = _create_binding(client)

    response = client.post(
        "/v1/tools/validate-alias",
        json={
            "binding_id": binding_id,
            "canonical_value": "kubernetes",
            "alias_value": "kube",
            "slot": "tool",
            "confidence": 0.9,
            "proposal_source_name": "search-log-scout",
            "idempotency_key": "search-log-scout:default_it:kube",
            "source_payload": {"query_count": 17},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["profile_name"] == "default_it"
    assert payload["binding_id"] == binding_id
    assert payload["validation_summary"]["status"] == "passed"

    suggestions = client.get("/v1/governance/profiles/default_it/suggestions")
    assert suggestions.status_code == 200
    assert suggestions.json() == []


def test_agent_tools_suggest_alias_creates_pending_agent_proposal(tmp_path):
    client = _client(tmp_path)
    _seed_profile(client)
    binding_id = _create_binding(client)

    response = client.post(
        "/v1/tools/suggest-alias",
        json={
            "binding_id": binding_id,
            "canonical_value": "kubernetes",
            "alias_value": "kube",
            "slot": "tool",
            "confidence": 0.88,
            "proposal_source_name": "search-log-scout",
            "idempotency_key": "search-log-scout:default_it:kube",
            "source_payload": {"query_count": 42},
            "context": "Observed in failed search logs.",
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["created"] is True
    suggestion = payload["suggestion"]
    assert suggestion["status"] == "pending"
    assert suggestion["binding_id"] == binding_id
    assert suggestion["proposal_source_type"] == "agent"
    assert suggestion["proposal_source_name"] == "search-log-scout"
    assert suggestion["source_payload"] == {"query_count": 42}
    assert suggestion["validation_summary"]["status"] == "passed"


def test_agent_tools_explain_query_uses_runtime_binding_context(tmp_path):
    client = _client(tmp_path)
    _seed_profile(client)
    binding_id = _create_binding(client)

    response = client.post(
        "/v1/tools/explain-query",
        json={"binding_id": binding_id, "query": "k8s timeout"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["binding_id"] == binding_id
    assert payload["profile_name"] == "default_it"
    assert payload["canonical_query"] == "kubernetes timeout"
    assert payload["changed"] is True
    assert payload["matched_aliases"] == ["k8s"]
    assert payload["text_fields"] == ["title", "body"]
    assert payload["target_field"] == "skeinrank"


def test_agent_tools_reject_profile_binding_mismatch(tmp_path):
    client = _client(tmp_path)
    _seed_profile(client)
    client.post("/v1/governance/profiles", json={"name": "other"})
    binding_id = _create_binding(client)

    response = client.post(
        "/v1/tools/validate-alias",
        json={
            "profile_name": "other",
            "binding_id": binding_id,
            "canonical_value": "kubernetes",
            "alias_value": "kube",
            "slot": "tool",
        },
    )

    assert response.status_code == 409
    assert "Binding does not belong" in response.json()["detail"]
