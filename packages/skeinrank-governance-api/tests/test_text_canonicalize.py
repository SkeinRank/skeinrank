from __future__ import annotations

from fastapi.testclient import TestClient
from skeinrank_governance_api import GovernanceApiConfig, create_app


def _client(tmp_path, *, auth_enabled: bool = False) -> TestClient:
    app = create_app(
        GovernanceApiConfig(
            database_url=f"sqlite:///{tmp_path / 'governance.db'}",
            create_tables_on_startup=True,
            auth_enabled=auth_enabled,
            bootstrap_admin=auth_enabled,
            admin_username="admin",
            admin_password="admin-secret",
            service_version="test",
        )
    )
    return TestClient(app)


def _login(client: TestClient) -> str:
    response = client.post(
        "/v1/auth/login",
        json={"username": "admin", "password": "admin-secret"},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _seed_dictionary(client: TestClient, headers: dict[str, str] | None = None) -> None:
    headers = headers or {}
    assert (
        client.post(
            "/v1/governance/profiles",
            json={"name": "infra_incidents"},
            headers=headers,
        ).status_code
        == 201
    )
    assert (
        client.post(
            "/v1/governance/profiles/infra_incidents/terms",
            json={
                "canonical_value": "kubernetes",
                "slot": "TOOL",
                "tags": ["infra", "orchestration"],
            },
            headers=headers,
        ).status_code
        == 201
    )
    assert (
        client.post(
            "/v1/governance/profiles/infra_incidents/terms/kubernetes/aliases",
            json={"alias_value": "k8s", "confidence": 1.0},
            headers=headers,
        ).status_code
        == 201
    )
    assert (
        client.post(
            "/v1/governance/profiles/infra_incidents/terms/kubernetes/aliases",
            json={"alias_value": "kube", "confidence": 0.95},
            headers=headers,
        ).status_code
        == 201
    )
    assert (
        client.post(
            "/v1/governance/profiles/infra_incidents/terms",
            json={
                "canonical_value": "postgresql",
                "slot": "DATABASE",
                "tags": ["backend", "storage"],
            },
            headers=headers,
        ).status_code
        == 201
    )
    assert (
        client.post(
            "/v1/governance/profiles/infra_incidents/terms/postgresql/aliases",
            json={"alias_value": "pg"},
            headers=headers,
        ).status_code
        == 201
    )
    assert (
        client.post(
            "/v1/governance/profiles/infra_incidents/terms/postgresql/aliases",
            json={"alias_value": "postgres"},
            headers=headers,
        ).status_code
        == 201
    )


def test_text_canonicalize_replace_returns_canonical_text_and_evidence(tmp_path):
    client = _client(tmp_path)
    _seed_dictionary(client)

    response = client.post(
        "/v1/text/canonicalize",
        json={
            "profile_name": "infra_incidents",
            "text": "k8s rollout failed after pg migration",
            "mode": "replace",
            "include_evidence": True,
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["profile_name"] == "infra_incidents"
    assert payload["mode"] == "replace"
    assert payload["original_text"] == "k8s rollout failed after pg migration"
    assert payload["canonical_text"] == (
        "kubernetes rollout failed after postgresql migration"
    )
    assert payload["changed"] is True
    assert payload["canonical_values"] == ["kubernetes", "postgresql"]
    assert payload["slots"] == {
        "DATABASE": ["postgresql"],
        "TOOL": ["kubernetes"],
    }
    assert payload["tags"] == {
        "kubernetes": ["infra", "orchestration"],
        "postgresql": ["backend", "storage"],
    }
    assert payload["matched_aliases"] == ["k8s", "pg"]
    assert [item["matched_text"] for item in payload["replacements"]] == ["k8s", "pg"]
    assert payload["replacements"][0]["start"] == 0
    assert payload["replacements"][0]["end"] == 3
    assert payload["replacements"][0]["tags"] == ["infra", "orchestration"]
    assert payload["evidence"][0]["reason"] == "Alias matched active canonical term"
    assert payload["evidence"][1]["canonical_value"] == "postgresql"
    assert payload["evidence"][1]["tags"] == ["backend", "storage"]


def test_text_canonicalize_annotate_does_not_change_text(tmp_path):
    client = _client(tmp_path)
    _seed_dictionary(client)

    response = client.post(
        "/v1/text/canonicalize",
        json={
            "profile_name": "infra_incidents",
            "text": "K8S and Postgres need attention",
            "mode": "annotate",
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["canonical_text"] == "K8S and Postgres need attention"
    assert payload["changed"] is False
    assert payload["canonical_values"] == ["kubernetes", "postgresql"]
    assert [item["matched_text"] for item in payload["replacements"]] == [
        "K8S",
        "Postgres",
    ]


def test_text_canonicalize_attributes_mode_returns_no_replacements(tmp_path):
    client = _client(tmp_path)
    _seed_dictionary(client)

    response = client.post(
        "/v1/text/canonicalize",
        json={
            "profile_name": "infra_incidents",
            "text": "kube and pg",
            "mode": "attributes",
            "include_evidence": False,
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["canonical_text"] == "kube and pg"
    assert payload["changed"] is False
    assert payload["canonical_values"] == ["kubernetes", "postgresql"]
    assert payload["replacements"] == []
    assert payload["evidence"] == []


def test_text_canonicalize_respects_stop_lists(tmp_path):
    client = _client(tmp_path)
    _seed_dictionary(client)
    assert (
        client.post(
            "/v1/governance/profiles/infra_incidents/stop-list",
            json={"value": "pg", "target": "alias", "reason": "too noisy"},
        ).status_code
        == 201
    )

    response = client.post(
        "/v1/text/canonicalize",
        json={
            "profile_name": "infra_incidents",
            "text": "k8s talks to pg",
            "mode": "replace",
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["canonical_text"] == "kubernetes talks to pg"
    assert payload["canonical_values"] == ["kubernetes"]
    assert payload["matched_aliases"] == ["k8s"]


def test_text_canonicalize_requires_known_profile(tmp_path):
    client = _client(tmp_path)

    response = client.post(
        "/v1/text/canonicalize",
        json={"profile_name": "missing", "text": "k8s", "mode": "replace"},
    )

    assert response.status_code == 404
    assert "Profile not found" in response.json()["detail"]


def test_text_canonicalize_rejects_invalid_mode(tmp_path):
    client = _client(tmp_path)
    _seed_dictionary(client)

    response = client.post(
        "/v1/text/canonicalize",
        json={"profile_name": "infra_incidents", "text": "k8s", "mode": "rewrite"},
    )

    assert response.status_code == 422
    assert "Invalid canonicalization mode" in response.json()["detail"]


def test_text_canonicalize_is_protected_when_auth_enabled(tmp_path):
    client = _client(tmp_path, auth_enabled=True)
    token = _login(client)
    headers = _auth(token)
    _seed_dictionary(client, headers=headers)

    unauthorized = client.post(
        "/v1/text/canonicalize",
        json={"profile_name": "infra_incidents", "text": "k8s"},
    )
    assert unauthorized.status_code == 401

    authorized = client.post(
        "/v1/text/canonicalize",
        json={"profile_name": "infra_incidents", "text": "k8s", "mode": "replace"},
        headers=headers,
    )
    assert authorized.status_code == 200
    assert authorized.json()["canonical_text"] == "kubernetes"


def test_text_canonicalize_accepts_binding_id_and_uses_runtime_snapshot(tmp_path):
    from skeinrank_governance.models import ElasticsearchBinding, TerminologyProfile
    from skeinrank_governance_api.runtime_snapshots import (
        build_runtime_snapshot_payload,
    )

    client = _client(tmp_path)
    _seed_dictionary(client)
    binding_response = client.post(
        "/v1/governance/elasticsearch/bindings",
        json={
            "name": "infra docs",
            "profile_name": "infra_incidents",
            "index_name": "kb",
            "text_fields": ["title", "text"],
            "target_field": "skeinrank",
            "mode": "write",
            "write_strategy": "in_place",
        },
    )
    assert binding_response.status_code == 201
    binding_id = binding_response.json()["id"]

    session_factory = client.app.state.governance_session_factory
    with session_factory() as session:
        profile = (
            session.query(TerminologyProfile)
            .filter_by(normalized_name="infra_incidents")
            .one()
        )
        binding = session.get(ElasticsearchBinding, binding_id)
        snapshot = build_runtime_snapshot_payload(session, profile)
        binding.last_successful_snapshot_version = snapshot["version"]
        binding.runtime_snapshot_json = snapshot
        session.commit()

    created_alias = client.post(
        "/v1/governance/profiles/infra_incidents/terms/postgresql/aliases",
        json={"alias_value": "pgx"},
    )
    assert created_alias.status_code == 201

    latest_response = client.post(
        "/v1/text/canonicalize",
        json={"profile_name": "infra_incidents", "text": "pgx migration"},
    )
    assert latest_response.status_code == 200, latest_response.text
    assert latest_response.json()["matched_aliases"] == ["pgx"]
    assert latest_response.json()["snapshot_source"] == "latest_profile"

    binding_response = client.post(
        "/v1/text/canonicalize",
        json={"binding_id": binding_id, "text": "pgx migration"},
    )
    assert binding_response.status_code == 200, binding_response.text
    payload = binding_response.json()
    assert payload["profile_name"] == "infra_incidents"
    assert payload["binding_id"] == binding_id
    assert payload["snapshot_source"] == "binding_runtime_snapshot"
    assert payload["canonical_values"] == []
    assert payload["matched_aliases"] == []


def test_text_canonicalize_accepts_binding_name_and_returns_runtime_context(tmp_path):
    client = _client(tmp_path)
    _seed_dictionary(client)
    binding_response = client.post(
        "/v1/governance/elasticsearch/bindings",
        json={
            "name": "infra incidents prod",
            "profile_name": "infra_incidents",
            "index_name": "incidents-prod",
            "text_fields": ["title", "body"],
            "target_field": "skeinrank",
            "filter_field": "team",
            "filter_value": "infra",
        },
    )
    assert binding_response.status_code == 201, binding_response.text

    response = client.post(
        "/v1/text/canonicalize",
        json={
            "binding_name": "infra incidents prod",
            "text": "k8s pg timeout",
            "mode": "replace",
            "application_scope": {
                "workspace": "infra",
                "selected_scope": "incidents",
                "nested": {"ignored": "as string"},
            },
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["binding_name"] == "infra incidents prod"
    assert payload["canonical_text"] == "kubernetes postgresql timeout"
    assert payload["runtime_context"] == {
        "mode": "binding_latest_profile",
        "profile_name": "infra_incidents",
        "normalized_profile_name": "infra_incidents",
        "binding_id": binding_response.json()["id"],
        "binding_name": "infra incidents prod",
        "normalized_binding_name": "infra_incidents_prod",
        "index_name": "incidents-prod",
        "text_fields": ["title", "body"],
        "target_field": "skeinrank",
        "filter_field": "team",
        "filter_value": "infra",
        "snapshot_version": payload["snapshot_version"],
        "snapshot_source": "latest_profile",
        "application_scope": {
            "workspace": "infra",
            "selected_scope": "incidents",
            "nested": "{'ignored': 'as string'}",
        },
    }


def test_text_canonicalize_rejects_binding_id_name_mismatch(tmp_path):
    client = _client(tmp_path)
    _seed_dictionary(client)
    left = client.post(
        "/v1/governance/elasticsearch/bindings",
        json={
            "name": "infra incidents prod",
            "profile_name": "infra_incidents",
            "index_name": "incidents-prod",
            "text_fields": ["title"],
            "target_field": "skeinrank",
        },
    )
    assert left.status_code == 201, left.text
    right = client.post(
        "/v1/governance/elasticsearch/bindings",
        json={
            "name": "infra runbooks prod",
            "profile_name": "infra_incidents",
            "index_name": "runbooks-prod",
            "text_fields": ["title"],
            "target_field": "skeinrank",
        },
    )
    assert right.status_code == 201, right.text

    response = client.post(
        "/v1/text/canonicalize",
        json={
            "binding_id": left.json()["id"],
            "binding_name": "infra runbooks prod",
            "text": "pg timeout",
        },
    )

    assert response.status_code == 409
    assert "binding_id and binding_name" in response.json()["detail"]
