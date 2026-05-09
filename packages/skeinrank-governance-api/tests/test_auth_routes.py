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


def test_elasticsearch_binding_permissions_with_roles(tmp_path):
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
        "/v1/governance/elasticsearch/bindings",
        json={
            "name": "docs",
            "profile_name": "default_it",
            "index_name": "docs",
            "text_fields": ["body"],
            "target_field": "skeinrank",
        },
        headers=_auth(mod_token),
    )
    assert create_response.status_code == 201

    read_response = client.get(
        "/v1/governance/elasticsearch/bindings",
        headers=_auth(contributor_token),
    )
    assert read_response.status_code == 200
    assert read_response.json()[0]["name"] == "docs"

    forbidden_create = client.post(
        "/v1/governance/elasticsearch/bindings",
        json={
            "name": "tickets",
            "profile_name": "default_it",
            "index_name": "tickets",
            "text_fields": ["body"],
            "target_field": "skeinrank",
        },
        headers=_auth(contributor_token),
    )
    assert forbidden_create.status_code == 403

    forbidden_delete = client.delete(
        f"/v1/governance/elasticsearch/bindings/{create_response.json()['id']}",
        headers=_auth(contributor_token),
    )
    assert forbidden_delete.status_code == 403


def test_personal_api_token_can_authenticate_and_be_revoked(tmp_path):
    client = _client(tmp_path)
    admin_token = _login(client)

    create_response = client.post(
        "/v1/auth/api-tokens",
        json={
            "name": "Jupyter migration token",
            "scopes": ["migration:validate", "migration:export"],
            "expires_in_days": 30,
        },
        headers=_auth(admin_token),
    )
    assert create_response.status_code == 201, create_response.text
    payload = create_response.json()
    assert payload["access_token"].startswith("sk_pat_")
    assert payload["owner_type"] == "personal"
    assert payload["owner_name"] == "admin"
    assert payload["scopes"] == ["migration:export", "migration:validate"]

    me_response = client.get("/v1/auth/me", headers=_auth(payload["access_token"]))
    assert me_response.status_code == 200
    assert me_response.json()["username"] == "admin"

    list_response = client.get("/v1/auth/api-tokens", headers=_auth(admin_token))
    assert list_response.status_code == 200
    assert list_response.json()[0]["token_prefix"].startswith("sk_pat_")
    assert "access_token" not in list_response.json()[0]

    revoke_response = client.delete(
        f"/v1/auth/api-tokens/{payload['id']}",
        headers=_auth(admin_token),
    )
    assert revoke_response.status_code == 204

    revoked_me = client.get("/v1/auth/me", headers=_auth(payload["access_token"]))
    assert revoked_me.status_code == 401


def test_service_account_token_can_use_console_api_with_scopes(tmp_path):
    client = _client(tmp_path)
    admin_token = _login(client)

    account_response = client.post(
        "/v1/auth/service-accounts",
        json={
            "name": "migration-bot",
            "display_name": "Migration Bot",
            "description": "Loads dictionary migrations from CI.",
            "role": "admin",
        },
        headers=_auth(admin_token),
    )
    assert account_response.status_code == 201, account_response.text
    assert account_response.json()["normalized_name"] == "migration_bot"

    token_response = client.post(
        "/v1/auth/service-accounts/migration-bot/tokens",
        json={
            "name": "CI import token",
            "scopes": ["migration:apply", "migration:export", "migration:validate"],
            "expires_in_days": 30,
        },
        headers=_auth(admin_token),
    )
    assert token_response.status_code == 201, token_response.text
    service_token = token_response.json()["access_token"]
    assert service_token.startswith("sk_sat_")
    assert token_response.json()["owner_type"] == "service_account"

    validate_response = client.post(
        "/v1/console/dictionary/validate",
        json={
            "profile_name": "infra_console_test",
            "create_profile": True,
            "mode": "upsert",
            "terms": [
                {
                    "canonical_value": "kubernetes",
                    "slot": "TOOL",
                    "aliases": ["k8s"],
                }
            ],
        },
        headers=_auth(service_token),
    )
    assert validate_response.status_code == 200, validate_response.text

    import_response = client.post(
        "/v1/console/dictionary/import",
        json={
            "profile_name": "infra_console_test",
            "create_profile": True,
            "mode": "upsert",
            "terms": [
                {
                    "canonical_value": "kubernetes",
                    "slot": "TOOL",
                    "aliases": ["k8s"],
                }
            ],
        },
        headers=_auth(service_token),
    )
    assert import_response.status_code == 200, import_response.text
    assert import_response.json()["status"] == "applied"


def test_api_token_scope_is_enforced_for_console_import(tmp_path):
    client = _client(tmp_path)
    admin_token = _login(client)

    create_response = client.post(
        "/v1/auth/api-tokens",
        json={
            "name": "Validate only",
            "scopes": ["migration:validate"],
            "expires_in_days": 30,
        },
        headers=_auth(admin_token),
    )
    assert create_response.status_code == 201
    limited_token = create_response.json()["access_token"]

    validate_response = client.post(
        "/v1/console/dictionary/validate",
        json={"profile_name": "default_it", "terms": []},
        headers=_auth(limited_token),
    )
    assert validate_response.status_code == 200

    import_response = client.post(
        "/v1/console/dictionary/import",
        json={"profile_name": "default_it", "terms": []},
        headers=_auth(limited_token),
    )
    assert import_response.status_code == 403
    assert "migration:apply" in import_response.json()["detail"]


def test_admin_can_disable_service_account_and_revoke_tokens(tmp_path):
    client = _client(tmp_path)
    admin_token = _login(client)

    client.post(
        "/v1/auth/service-accounts",
        json={"name": "sync-bot", "role": "contributor"},
        headers=_auth(admin_token),
    )
    token_response = client.post(
        "/v1/auth/service-accounts/sync-bot/tokens",
        json={"name": "Sync token", "scopes": ["migration:validate"]},
        headers=_auth(admin_token),
    )
    assert token_response.status_code == 201
    service_token = token_response.json()["access_token"]

    before_disable = client.get("/v1/auth/me", headers=_auth(service_token))
    assert before_disable.status_code == 200
    assert before_disable.json()["username"] == "sync-bot"

    disable_response = client.patch(
        "/v1/auth/service-accounts/sync-bot",
        json={"is_active": False},
        headers=_auth(admin_token),
    )
    assert disable_response.status_code == 200
    assert disable_response.json()["is_active"] is False

    after_disable = client.get("/v1/auth/me", headers=_auth(service_token))
    assert after_disable.status_code == 401


def test_admin_can_suspend_and_reactivate_user_without_recreating_personal_tokens(
    tmp_path,
):
    client = _client(tmp_path)
    admin_token = _login(client)

    create_user_response = client.post(
        "/v1/auth/users",
        json={
            "username": "analyst",
            "password": "analyst-secret",
            "role": "contributor",
        },
        headers=_auth(admin_token),
    )
    assert create_user_response.status_code == 201
    assert create_user_response.json()["status"] == "active"

    analyst_token = _login(client, "analyst", "analyst-secret")
    create_token_response = client.post(
        "/v1/auth/api-tokens",
        json={"name": "Notebook token", "scopes": ["migration:validate"]},
        headers=_auth(analyst_token),
    )
    assert create_token_response.status_code == 201
    personal_token = create_token_response.json()["access_token"]

    suspend_response = client.patch(
        "/v1/auth/users/analyst/status",
        json={"status": "suspended"},
        headers=_auth(admin_token),
    )
    assert suspend_response.status_code == 200
    assert suspend_response.json()["status"] == "suspended"
    assert suspend_response.json()["is_active"] is False

    assert (
        client.post(
            "/v1/auth/login",
            json={"username": "analyst", "password": "analyst-secret"},
        ).status_code
        == 401
    )
    assert client.get("/v1/auth/me", headers=_auth(personal_token)).status_code == 401

    reactivate_response = client.patch(
        "/v1/auth/users/analyst/status",
        json={"status": "active"},
        headers=_auth(admin_token),
    )
    assert reactivate_response.status_code == 200
    assert reactivate_response.json()["status"] == "active"
    assert reactivate_response.json()["is_active"] is True

    assert (
        client.post(
            "/v1/auth/login",
            json={"username": "analyst", "password": "analyst-secret"},
        ).status_code
        == 200
    )
    assert client.get("/v1/auth/me", headers=_auth(personal_token)).status_code == 200


def test_admin_can_deactivate_user_and_revoke_all_personal_api_tokens(tmp_path):
    client = _client(tmp_path)
    admin_token = _login(client)

    client.post(
        "/v1/auth/users",
        json={"username": "ds", "password": "ds-secret", "role": "moderator"},
        headers=_auth(admin_token),
    )
    ds_token = _login(client, "ds", "ds-secret")
    first_token = client.post(
        "/v1/auth/api-tokens",
        json={"name": "First", "scopes": ["migration:validate"]},
        headers=_auth(ds_token),
    ).json()["access_token"]
    second_token = client.post(
        "/v1/auth/api-tokens",
        json={"name": "Second", "scopes": ["migration:validate"]},
        headers=_auth(ds_token),
    ).json()["access_token"]

    revoke_response = client.post(
        "/v1/auth/users/ds/revoke-api-tokens",
        headers=_auth(admin_token),
    )
    assert revoke_response.status_code == 200
    assert revoke_response.json() == {"username": "ds", "revoked_api_tokens": 2}
    assert client.get("/v1/auth/me", headers=_auth(first_token)).status_code == 401
    assert client.get("/v1/auth/me", headers=_auth(second_token)).status_code == 401

    deactivate_response = client.patch(
        "/v1/auth/users/ds/status",
        json={"status": "deactivated"},
        headers=_auth(admin_token),
    )
    assert deactivate_response.status_code == 200
    assert deactivate_response.json()["status"] == "deactivated"
    assert deactivate_response.json()["is_active"] is False
    assert (
        client.post(
            "/v1/auth/login",
            json={"username": "ds", "password": "ds-secret"},
        ).status_code
        == 401
    )


def test_user_status_update_rejects_invalid_status(tmp_path):
    client = _client(tmp_path)
    admin_token = _login(client)

    response = client.patch(
        "/v1/auth/users/admin/status",
        json={"status": "paused"},
        headers=_auth(admin_token),
    )

    assert response.status_code == 422
    assert "Invalid user status" in response.json()["detail"]
