from __future__ import annotations

from fastapi.testclient import TestClient
from skeinrank_governance_api import GovernanceApiConfig, create_app


def _client(tmp_path) -> TestClient:
    app = create_app(
        GovernanceApiConfig(
            database_url=f"sqlite:///{tmp_path / 'governance.db'}",
            create_tables_on_startup=True,
            auth_enabled=True,
            bootstrap_admin=True,
            admin_username="admin",
            admin_password="admin-secret",
            token_ttl_hours=1,
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


def _create_agent_service_account(client: TestClient, admin_token: str) -> None:
    response = client.post(
        "/v1/auth/service-accounts",
        json={
            "name": "agent-writer",
            "display_name": "Agent Writer",
            "description": "Proposal-writing agent credential owner.",
            "role": "contributor",
        },
        headers=_auth(admin_token),
    )
    assert response.status_code == 201, response.text


def test_scoped_agent_credentials_policy_is_admin_readable(tmp_path):
    client = _client(tmp_path)
    admin_token = _login(client)

    response = client.get(
        "/v1/auth/scoped-agent-credentials",
        headers=_auth(admin_token),
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["schema_version"] == "skeinrank.scoped_agent_credentials.v1"
    assert payload["safety"]["auto_apply_allowed"] is False
    assert payload["safety"]["runtime_mutation_allowed"] is False
    assert payload["rotation"]["plaintext_token_returned_once"] is True
    names = {item["name"] for item in payload["recommended_credentials"]}
    assert {
        "agent-readonly-validator",
        "agent-proposal-writer",
        "agent-tracking-writer",
    } <= names

    proposal_profile = next(
        item
        for item in payload["recommended_credentials"]
        if item["name"] == "agent-proposal-writer"
    )
    assert proposal_profile["role"] == "contributor"
    assert proposal_profile["can_submit_proposals"] is True
    assert proposal_profile["can_mutate_runtime"] is False
    assert "agent:tools:suggest" in proposal_profile["scopes"]


def test_scoped_agent_credentials_policy_requires_admin(tmp_path):
    client = _client(tmp_path)
    admin_token = _login(client)
    user_response = client.post(
        "/v1/auth/users",
        json={
            "username": "reviewer",
            "password": "reviewer-secret",
            "role": "moderator",
        },
        headers=_auth(admin_token),
    )
    assert user_response.status_code == 201, user_response.text
    reviewer_token = client.post(
        "/v1/auth/login",
        json={"username": "reviewer", "password": "reviewer-secret"},
    ).json()["access_token"]

    response = client.get(
        "/v1/auth/scoped-agent-credentials",
        headers=_auth(reviewer_token),
    )

    assert response.status_code == 403


def test_admin_can_rotate_service_account_token_and_old_token_is_revoked(tmp_path):
    client = _client(tmp_path)
    admin_token = _login(client)
    _create_agent_service_account(client, admin_token)

    first_token_response = client.post(
        "/v1/auth/service-accounts/agent-writer/tokens",
        json={
            "name": "Agent token v1",
            "scopes": [
                "agent:runs:read",
                "agent:tools:validate",
                "agent:tools:suggest",
            ],
            "expires_in_days": 30,
        },
        headers=_auth(admin_token),
    )
    assert first_token_response.status_code == 201, first_token_response.text
    first_payload = first_token_response.json()
    first_token = first_payload["access_token"]

    assert client.get("/v1/auth/me", headers=_auth(first_token)).status_code == 200

    rotate_response = client.post(
        f"/v1/auth/service-accounts/agent-writer/tokens/{first_payload['id']}/rotate",
        json={"name": "Agent token v2", "expires_in_days": 60},
        headers=_auth(admin_token),
    )
    assert rotate_response.status_code == 201, rotate_response.text
    rotated = rotate_response.json()
    assert rotated["access_token"].startswith("sk_sat_")
    assert rotated["id"] != first_payload["id"]
    assert rotated["rotated_from_token_id"] == first_payload["id"]
    assert rotated["revoked_token_id"] == first_payload["id"]
    assert rotated["revoked_old_token"] is True
    assert rotated["name"] == "Agent token v2"
    assert rotated["scopes"] == sorted(first_payload["scopes"])
    assert rotated["owner_type"] == "service_account"
    assert rotated["owner_name"] == "agent-writer"

    assert client.get("/v1/auth/me", headers=_auth(first_token)).status_code == 401
    new_me = client.get("/v1/auth/me", headers=_auth(rotated["access_token"]))
    assert new_me.status_code == 200, new_me.text
    assert new_me.json()["username"] == "agent-writer"

    tokens = client.get(
        "/v1/auth/service-accounts/agent-writer/tokens",
        headers=_auth(admin_token),
    )
    assert tokens.status_code == 200, tokens.text
    by_id = {item["id"]: item for item in tokens.json()}
    assert by_id[first_payload["id"]]["revoked_at"] is not None
    assert by_id[rotated["id"]]["revoked_at"] is None
    assert "access_token" not in by_id[rotated["id"]]


def test_rotation_rejects_already_revoked_or_wrong_owner_tokens(tmp_path):
    client = _client(tmp_path)
    admin_token = _login(client)
    _create_agent_service_account(client, admin_token)
    other_account = client.post(
        "/v1/auth/service-accounts",
        json={"name": "other-agent", "role": "contributor"},
        headers=_auth(admin_token),
    )
    assert other_account.status_code == 201, other_account.text

    token_response = client.post(
        "/v1/auth/service-accounts/agent-writer/tokens",
        json={"name": "Agent token", "scopes": ["agent:tools:validate"]},
        headers=_auth(admin_token),
    )
    assert token_response.status_code == 201, token_response.text
    token_id = token_response.json()["id"]

    wrong_owner = client.post(
        f"/v1/auth/service-accounts/other-agent/tokens/{token_id}/rotate",
        json={},
        headers=_auth(admin_token),
    )
    assert wrong_owner.status_code == 404

    revoke = client.delete(
        f"/v1/auth/service-accounts/agent-writer/tokens/{token_id}",
        headers=_auth(admin_token),
    )
    assert revoke.status_code == 204
    rotate_revoked = client.post(
        f"/v1/auth/service-accounts/agent-writer/tokens/{token_id}/rotate",
        json={},
        headers=_auth(admin_token),
    )
    assert rotate_revoked.status_code == 409
    assert "already revoked" in rotate_revoked.json()["detail"]
