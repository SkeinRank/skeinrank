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


def test_governance_suggestion_idempotent_retry_returns_existing(tmp_path):
    client = _client(tmp_path)
    _seed_profile(client)
    payload = {
        "canonical_value": "kubernetes",
        "alias_value": "kube",
        "slot": "tool",
        "proposal_source_type": "agent",
        "proposal_source_name": "search-log-scout",
        "idempotency_key": "search-log-scout:default_it:kube",
        "source_payload": {"query_count": 42},
    }

    first = client.post("/v1/governance/profiles/default_it/suggestions", json=payload)
    retry = client.post("/v1/governance/profiles/default_it/suggestions", json=payload)

    assert first.status_code == 201, first.text
    assert retry.status_code == 200, retry.text
    assert retry.json()["id"] == first.json()["id"]
    assert retry.json()["idempotency_key"] == payload["idempotency_key"]

    listed = client.get("/v1/governance/profiles/default_it/suggestions")
    assert listed.status_code == 200
    assert len(listed.json()) == 1


def test_governance_suggestion_rejects_idempotency_key_reuse_for_different_payload(
    tmp_path,
):
    client = _client(tmp_path)
    _seed_profile(client)
    key = "search-log-scout:default_it:kube"

    first = client.post(
        "/v1/governance/profiles/default_it/suggestions",
        json={
            "canonical_value": "kubernetes",
            "alias_value": "kube",
            "slot": "tool",
            "proposal_source_type": "agent",
            "idempotency_key": key,
        },
    )
    conflict = client.post(
        "/v1/governance/profiles/default_it/suggestions",
        json={
            "canonical_value": "kubernetes",
            "alias_value": "k8s-short",
            "slot": "tool",
            "proposal_source_type": "agent",
            "idempotency_key": key,
        },
    )

    assert first.status_code == 201, first.text
    assert conflict.status_code == 409
    assert "Idempotency key" in conflict.json()["detail"]


def test_agent_tool_suggest_alias_idempotent_retry_returns_existing(tmp_path):
    client = _client(tmp_path)
    _seed_profile(client)
    binding_id = _create_binding(client)
    payload = {
        "binding_id": binding_id,
        "canonical_value": "kubernetes",
        "alias_value": "kube",
        "slot": "tool",
        "proposal_source_name": "search-log-scout",
        "idempotency_key": "search-log-scout:default_it:kube",
        "source_payload": {"query_count": 42},
    }

    first = client.post("/v1/tools/suggest-alias", json=payload)
    retry = client.post("/v1/tools/suggest-alias", json=payload)

    assert first.status_code == 201, first.text
    assert retry.status_code == 200, retry.text
    assert first.json()["created"] is True
    assert retry.json()["created"] is False
    assert retry.json()["suggestion"]["id"] == first.json()["suggestion"]["id"]

    listed = client.get("/v1/governance/profiles/default_it/suggestions")
    assert listed.status_code == 200
    assert len(listed.json()) == 1


def test_agent_tool_rejects_idempotency_key_reuse_for_different_binding(tmp_path):
    client = _client(tmp_path)
    _seed_profile(client)
    binding_id = _create_binding(client)
    key = "search-log-scout:default_it:kube"

    first = client.post(
        "/v1/tools/suggest-alias",
        json={
            "binding_id": binding_id,
            "canonical_value": "kubernetes",
            "alias_value": "kube",
            "slot": "tool",
            "idempotency_key": key,
        },
    )
    conflict = client.post(
        "/v1/tools/suggest-alias",
        json={
            "binding_id": binding_id,
            "canonical_value": "kubernetes",
            "alias_value": "kube-other",
            "slot": "tool",
            "idempotency_key": key,
        },
    )

    assert first.status_code == 201, first.text
    assert conflict.status_code == 409
    assert "Idempotency key" in conflict.json()["detail"]
