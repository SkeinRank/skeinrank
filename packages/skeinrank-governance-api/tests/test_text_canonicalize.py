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
            json={"canonical_value": "kubernetes", "slot": "TOOL"},
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
            json={"canonical_value": "postgresql", "slot": "DATABASE"},
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
    assert payload["matched_aliases"] == ["k8s", "pg"]
    assert [item["matched_text"] for item in payload["replacements"]] == ["k8s", "pg"]
    assert payload["replacements"][0]["start"] == 0
    assert payload["replacements"][0]["end"] == 3
    assert payload["evidence"][0]["reason"] == "Alias matched active canonical term"
    assert payload["evidence"][1]["canonical_value"] == "postgresql"


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
