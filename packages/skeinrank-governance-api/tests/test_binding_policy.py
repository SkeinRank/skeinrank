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


def _seed_binding(client: TestClient) -> int:
    assert (
        client.post("/v1/governance/profiles", json={"name": "default_it"}).status_code
        == 201
    )
    term = client.post(
        "/v1/governance/profiles/default_it/terms",
        json={
            "canonical_value": "postgresql",
            "slot": "database",
            "tags": ["infra", "backend"],
        },
    )
    assert term.status_code == 201, term.text
    binding = client.post(
        "/v1/governance/elasticsearch/bindings",
        json={
            "name": "Infra Docs",
            "profile_name": "default_it",
            "index_name": "docs",
            "text_fields": ["title", "body"],
            "target_field": "skeinrank",
        },
    )
    assert binding.status_code == 201, binding.text
    return int(binding.json()["id"])


def test_create_get_update_and_delete_binding_policy(tmp_path):
    client = _client(tmp_path)
    binding_id = _seed_binding(client)

    missing = client.get(f"/v1/governance/elasticsearch/bindings/{binding_id}/policy")
    assert missing.status_code == 404

    created = client.put(
        f"/v1/governance/elasticsearch/bindings/{binding_id}/policy",
        json={
            "preferred_slots": ["database", " service ", "database"],
            "allowed_tags": ["Infra", " backend "],
            "deny_slots": ["document_component"],
            "context_rules": [
                {
                    "surface": "PG",
                    "prefer": "PostgreSQL",
                    "slot": "database",
                    "reason": "Infra binding",
                }
            ],
        },
    )
    assert created.status_code == 201, created.text
    payload = created.json()
    assert payload["binding_id"] == binding_id
    assert payload["profile_name"] == "default_it"
    assert payload["status"] == "active"
    assert payload["preferred_slots"] == ["DATABASE", "SERVICE"]
    assert payload["allowed_tags"] == ["backend", "infra"]
    assert payload["deny_slots"] == ["DOCUMENT_COMPONENT"]
    assert payload["context_rules"][0]["normalized_surface"] == "pg"
    assert payload["context_rules"][0]["normalized_prefer"] == "postgresql"
    assert payload["context_rules"][0]["slot"] == "DATABASE"
    assert payload["created_by"] == "local_dev"
    assert payload["updated_by"] == "local_dev"

    fetched = client.get(f"/v1/governance/elasticsearch/bindings/{binding_id}/policy")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == payload["id"]

    updated = client.put(
        f"/v1/governance/elasticsearch/bindings/{binding_id}/policy",
        json={
            "status": "disabled",
            "preferred_slots": ["technology"],
            "allowed_tags": [],
            "deny_slots": [],
            "context_rules": [],
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["status"] == "disabled"
    assert updated.json()["preferred_slots"] == ["TECHNOLOGY"]

    deleted = client.delete(
        f"/v1/governance/elasticsearch/bindings/{binding_id}/policy"
    )
    assert deleted.status_code == 204
    assert (
        client.get(
            f"/v1/governance/elasticsearch/bindings/{binding_id}/policy"
        ).status_code
        == 404
    )


def test_binding_policy_rejects_invalid_status(tmp_path):
    client = _client(tmp_path)
    binding_id = _seed_binding(client)

    response = client.put(
        f"/v1/governance/elasticsearch/bindings/{binding_id}/policy",
        json={"status": "paused"},
    )

    assert response.status_code == 422
    assert "Invalid binding policy status" in response.json()["detail"]
