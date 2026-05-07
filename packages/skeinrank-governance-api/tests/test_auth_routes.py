from __future__ import annotations

from fastapi.testclient import TestClient
from skeinrank_governance_api import GovernanceApiConfig, create_app


def _client(tmp_path, *, auth_enabled: bool = True) -> TestClient:
    app = create_app(
        GovernanceApiConfig(
            database_url=f"sqlite:///{tmp_path / 'governance.db'}",
            create_tables_on_startup=True,
            auth_enabled=auth_enabled,
            bootstrap_admin=True,
            admin_username="admin",
            admin_password="admin-secret",
            admin_display_name="Admin User",
            token_ttl_hours=1,
            service_version="test",
        )
    )
    return TestClient(app)


def _login(
    client: TestClient, username: str = "admin", password: str = "admin-secret"
) -> str:
    response = client.post(
        "/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_bootstrap_admin_can_login_and_read_me(tmp_path):
    client = _client(tmp_path)

    response = client.post(
        "/v1/auth/login",
        json={"username": "admin", "password": "admin-secret"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["token_type"] == "bearer"
    assert payload["access_token"]
    assert payload["user"]["username"] == "admin"
    assert payload["user"]["role"] == "admin"

    me_response = client.get("/v1/auth/me", headers=_auth(payload["access_token"]))
    assert me_response.status_code == 200
    assert me_response.json()["username"] == "admin"


def test_invalid_login_returns_401(tmp_path):
    client = _client(tmp_path)

    response = client.post(
        "/v1/auth/login",
        json={"username": "admin", "password": "wrong"},
    )

    assert response.status_code == 401
    assert "Invalid username or password" in response.json()["detail"]


def test_user_management_requires_admin_role(tmp_path):
    client = _client(tmp_path)
    admin_token = _login(client)

    create_response = client.post(
        "/v1/auth/users",
        json={
            "username": "mod",
            "password": "mod-secret",
            "display_name": "Moderator",
            "role": "moderator",
        },
        headers=_auth(admin_token),
    )
    assert create_response.status_code == 201
    assert create_response.json()["role"] == "moderator"

    mod_token = _login(client, "mod", "mod-secret")
    forbidden = client.get("/v1/auth/users", headers=_auth(mod_token))
    assert forbidden.status_code == 403

    users_response = client.get("/v1/auth/users", headers=_auth(admin_token))
    assert users_response.status_code == 200
    assert [user["username"] for user in users_response.json()] == ["admin", "mod"]


def test_duplicate_user_returns_conflict(tmp_path):
    client = _client(tmp_path)
    token = _login(client)

    first = client.post(
        "/v1/auth/users",
        json={"username": "analyst", "password": "secret", "role": "contributor"},
        headers=_auth(token),
    )
    assert first.status_code == 201

    response = client.post(
        "/v1/auth/users",
        json={"username": "Analyst", "password": "secret", "role": "contributor"},
        headers=_auth(token),
    )

    assert response.status_code == 409
    assert "User already exists" in response.json()["detail"]


def test_update_user_rejects_invalid_role(tmp_path):
    client = _client(tmp_path)
    token = _login(client)

    response = client.patch(
        "/v1/auth/users/admin",
        json={"role": "owner"},
        headers=_auth(token),
    )

    assert response.status_code == 422
    assert "Invalid user role" in response.json()["detail"]


def test_logout_revokes_token(tmp_path):
    client = _client(tmp_path)
    token = _login(client)

    logout_response = client.post("/v1/auth/logout", headers=_auth(token))
    assert logout_response.status_code == 204

    me_response = client.get("/v1/auth/me", headers=_auth(token))
    assert me_response.status_code == 401


def test_auth_enabled_protects_governance_routes(tmp_path):
    client = _client(tmp_path)

    response = client.get("/v1/governance/profiles")

    assert response.status_code == 401


def test_moderator_can_edit_terms_but_not_profiles(tmp_path):
    client = _client(tmp_path)
    admin_token = _login(client)
    client.post(
        "/v1/auth/users",
        json={"username": "mod", "password": "mod-secret", "role": "moderator"},
        headers=_auth(admin_token),
    )
    mod_token = _login(client, "mod", "mod-secret")

    profile_response = client.post(
        "/v1/governance/profiles",
        json={"name": "default_it"},
        headers=_auth(admin_token),
    )
    assert profile_response.status_code == 201

    forbidden_profile = client.post(
        "/v1/governance/profiles",
        json={"name": "other"},
        headers=_auth(mod_token),
    )
    assert forbidden_profile.status_code == 403

    term_response = client.post(
        "/v1/governance/profiles/default_it/terms",
        json={"canonical_value": "kubernetes", "slot": "TOOL"},
        headers=_auth(mod_token),
    )
    assert term_response.status_code == 201


def test_contributor_can_read_but_cannot_mutate_terms(tmp_path):
    client = _client(tmp_path)
    admin_token = _login(client)
    client.post(
        "/v1/auth/users",
        json={
            "username": "contrib",
            "password": "contrib-secret",
            "role": "contributor",
        },
        headers=_auth(admin_token),
    )
    contributor_token = _login(client, "contrib", "contrib-secret")
    client.post(
        "/v1/governance/profiles",
        json={"name": "default_it"},
        headers=_auth(admin_token),
    )

    read_response = client.get(
        "/v1/governance/profiles/default_it/terms",
        headers=_auth(contributor_token),
    )
    assert read_response.status_code == 200

    write_response = client.post(
        "/v1/governance/profiles/default_it/terms",
        json={"canonical_value": "kubernetes", "slot": "TOOL"},
        headers=_auth(contributor_token),
    )
    assert write_response.status_code == 403


def test_auth_disabled_returns_local_dev_me(tmp_path):
    client = _client(tmp_path, auth_enabled=False)

    response = client.get("/v1/auth/me")

    assert response.status_code == 200
    assert response.json()["username"] == "local_dev"
    assert response.json()["role"] == "admin"


def test_contributor_can_create_suggestion_but_not_approve(tmp_path):
    client = _client(tmp_path)
    admin_token = _login(client)
    client.post(
        "/v1/auth/users",
        json={"username": "mod", "password": "mod-secret", "role": "moderator"},
        headers=_auth(admin_token),
    )
    client.post(
        "/v1/auth/users",
        json={
            "username": "contrib",
            "password": "contrib-secret",
            "role": "contributor",
        },
        headers=_auth(admin_token),
    )
    mod_token = _login(client, "mod", "mod-secret")
    contributor_token = _login(client, "contrib", "contrib-secret")

    client.post(
        "/v1/governance/profiles",
        json={"name": "default_it"},
        headers=_auth(admin_token),
    )
    client.post(
        "/v1/governance/profiles/default_it/terms",
        json={"canonical_value": "kubernetes", "slot": "TOOL"},
        headers=_auth(mod_token),
    )

    suggestion_response = client.post(
        "/v1/governance/profiles/default_it/suggestions",
        json={
            "canonical_value": "kubernetes",
            "alias_value": "kube",
            "slot": "TOOL",
            "context": "Contributor saw this query in support tickets.",
        },
        headers=_auth(contributor_token),
    )
    assert suggestion_response.status_code == 201
    assert suggestion_response.json()["created_by"] == "contrib"

    suggestion_id = suggestion_response.json()["id"]
    approve_path = (
        f"/v1/governance/profiles/default_it/suggestions/{suggestion_id}/approve"
    )
    forbidden = client.post(
        approve_path,
        headers=_auth(contributor_token),
    )
    assert forbidden.status_code == 403

    approved = client.post(
        approve_path,
        json={"review_comment": "Approved by moderator."},
        headers=_auth(mod_token),
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"
    assert approved.json()["reviewed_by"] == "mod"


def test_contributor_can_create_canonical_term_suggestion_but_not_approve(tmp_path):
    client = _client(tmp_path)
    admin_token = _login(client)
    client.post(
        "/v1/auth/users",
        json={"username": "mod", "password": "mod-secret", "role": "moderator"},
        headers=_auth(admin_token),
    )
    client.post(
        "/v1/auth/users",
        json={
            "username": "contrib",
            "password": "contrib-secret",
            "role": "contributor",
        },
        headers=_auth(admin_token),
    )
    mod_token = _login(client, "mod", "mod-secret")
    contributor_token = _login(client, "contrib", "contrib-secret")

    client.post(
        "/v1/governance/profiles",
        json={"name": "default_it"},
        headers=_auth(admin_token),
    )

    suggestion_response = client.post(
        "/v1/governance/profiles/default_it/suggestions",
        json={
            "suggestion_type": "canonical_term",
            "canonical_value": "vector database",
            "slot": "TOOL",
            "description": "Storage system optimized for vector search.",
            "context": "Contributor could not find an existing canonical term.",
        },
        headers=_auth(contributor_token),
    )
    assert suggestion_response.status_code == 201
    assert suggestion_response.json()["suggestion_type"] == "canonical_term"
    assert suggestion_response.json()["created_by"] == "contrib"

    suggestion_id = suggestion_response.json()["id"]
    approve_path = (
        f"/v1/governance/profiles/default_it/suggestions/{suggestion_id}/approve"
    )
    forbidden = client.post(approve_path, headers=_auth(contributor_token))
    assert forbidden.status_code == 403

    approved = client.post(
        approve_path,
        json={"review_comment": "Approved by moderator."},
        headers=_auth(mod_token),
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"
    assert approved.json()["term_id"] is not None
    assert approved.json()["reviewed_by"] == "mod"


def test_stop_list_permissions_with_roles(tmp_path):
    client = _client(tmp_path)
    admin_token = _login(client)
    client.post(
        "/v1/auth/users",
        json={"username": "mod", "password": "mod-secret", "role": "moderator"},
        headers=_auth(admin_token),
    )
    client.post(
        "/v1/auth/users",
        json={
            "username": "contrib",
            "password": "contrib-secret",
            "role": "contributor",
        },
        headers=_auth(admin_token),
    )
    mod_token = _login(client, "mod", "mod-secret")
    contributor_token = _login(client, "contrib", "contrib-secret")

    client.post(
        "/v1/governance/profiles",
        json={"name": "default_it"},
        headers=_auth(admin_token),
    )

    create_response = client.post(
        "/v1/governance/profiles/default_it/stop-list",
        json={"value": "service", "target": "alias"},
        headers=_auth(mod_token),
    )
    assert create_response.status_code == 201

    read_response = client.get(
        "/v1/governance/profiles/default_it/stop-list",
        headers=_auth(contributor_token),
    )
    assert read_response.status_code == 200
    assert read_response.json()[0]["normalized_value"] == "service"

    forbidden_create = client.post(
        "/v1/governance/profiles/default_it/stop-list",
        json={"value": "app", "target": "alias"},
        headers=_auth(contributor_token),
    )
    assert forbidden_create.status_code == 403
