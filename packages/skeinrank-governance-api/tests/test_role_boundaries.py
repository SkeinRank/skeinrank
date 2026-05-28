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


def _create_user(
    client: TestClient,
    admin_token: str,
    *,
    username: str,
    role: str,
) -> str:
    password = f"{username}-secret"
    response = client.post(
        "/v1/auth/users",
        json={"username": username, "password": password, "role": role},
        headers=_auth(admin_token),
    )
    assert response.status_code == 201, response.text
    return _login(client, username, password)


def _seed_profile_term(client: TestClient, admin_token: str) -> None:
    response = client.post(
        "/v1/governance/profiles",
        json={"name": "default_it"},
        headers=_auth(admin_token),
    )
    assert response.status_code == 201, response.text
    response = client.post(
        "/v1/governance/profiles/default_it/terms",
        json={"canonical_value": "kubernetes", "slot": "tool"},
        headers=_auth(admin_token),
    )
    assert response.status_code == 201, response.text


def test_role_boundaries_endpoint_maps_governance_roles(tmp_path):
    client = _client(tmp_path)
    admin_token = _login(client)
    moderator_token = _create_user(
        client, admin_token, username="reviewer", role="moderator"
    )
    contributor_token = _create_user(
        client, admin_token, username="agent", role="contributor"
    )

    admin_response = client.get(
        "/v1/governance/role-boundaries", headers=_auth(admin_token)
    )
    assert admin_response.status_code == 200, admin_response.text
    payload = admin_response.json()
    assert payload["schema_version"] == "skeinrank.role_boundaries.v1"
    boundaries = {item["boundary"]: item for item in payload["boundaries"]}
    assert boundaries["agent"]["governance_roles"] == ["contributor"]
    assert boundaries["agent"]["may_propose"] is True
    assert boundaries["agent"]["may_approve_reject"] is False
    assert boundaries["reviewer"]["governance_roles"] == ["moderator"]
    assert boundaries["reviewer"]["may_approve_reject"] is True
    assert boundaries["reviewer"]["may_batch_apply"] is False
    assert boundaries["admin"]["governance_roles"] == ["admin"]
    assert boundaries["admin"]["may_batch_apply"] is True
    assert boundaries["admin"]["may_publish_snapshot"] is True
    assert payload["current_user"]["boundary"] == "admin"

    reviewer_response = client.get(
        "/v1/governance/role-boundaries", headers=_auth(moderator_token)
    )
    assert reviewer_response.status_code == 200, reviewer_response.text
    assert reviewer_response.json()["current_user"]["boundary"] == "reviewer"

    agent_response = client.get(
        "/v1/governance/role-boundaries", headers=_auth(contributor_token)
    )
    assert agent_response.status_code == 200, agent_response.text
    assert agent_response.json()["current_user"]["boundary"] == "agent"


def test_reviewer_can_review_but_cannot_batch_apply_or_publish(tmp_path):
    client = _client(tmp_path)
    admin_token = _login(client)
    moderator_token = _create_user(
        client, admin_token, username="reviewer", role="moderator"
    )
    contributor_token = _create_user(
        client, admin_token, username="agent", role="contributor"
    )
    _seed_profile_term(client, admin_token)

    suggestion = client.post(
        "/v1/governance/profiles/default_it/suggestions",
        json={
            "canonical_value": "kubernetes",
            "alias_value": "kubectl",
            "slot": "tool",
            "context": "Agent saw this in failed search logs.",
            "idempotency_key": "role-boundary:kubectl",
        },
        headers=_auth(contributor_token),
    )
    assert suggestion.status_code == 201, suggestion.text
    suggestion_id = suggestion.json()["id"]

    preview = client.post(
        "/v1/governance/profiles/default_it/suggestions/apply-batch/preview",
        json={"suggestion_ids": [suggestion_id]},
        headers=_auth(moderator_token),
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["items"][0]["validation_status"] == "passed"
    assert preview.json()["items"][0]["applyable"] is True

    reviewer_forbidden_apply = client.post(
        "/v1/governance/profiles/default_it/suggestions/apply-batch",
        json={"suggestion_ids": [suggestion_id]},
        headers=_auth(moderator_token),
    )
    assert reviewer_forbidden_apply.status_code == 403
    assert "Insufficient role permissions" in reviewer_forbidden_apply.json()["detail"]

    approve = client.post(
        f"/v1/governance/profiles/default_it/suggestions/{suggestion_id}/approve",
        json={"review_comment": "Reviewed by moderator."},
        headers=_auth(moderator_token),
    )
    assert approve.status_code == 200, approve.text
    assert approve.json()["status"] == "approved"
    assert approve.json()["reviewed_by"] == "reviewer"

    admin_apply = client.post(
        "/v1/governance/profiles/default_it/suggestions/apply-batch",
        json={"suggestion_ids": [suggestion_id]},
        headers=_auth(admin_token),
    )
    assert admin_apply.status_code == 200, admin_apply.text
    assert admin_apply.json()["status"] == "idempotent"


def test_agent_service_token_can_validate_but_not_apply(tmp_path):
    client = _client(tmp_path)
    admin_token = _login(client)
    _seed_profile_term(client, admin_token)
    service_account = client.post(
        "/v1/auth/service-accounts",
        json={"name": "alias-scout", "role": "contributor"},
        headers=_auth(admin_token),
    )
    assert service_account.status_code == 201, service_account.text
    service_token_response = client.post(
        "/v1/auth/service-accounts/alias-scout/tokens",
        json={
            "name": "validate-only",
            "scopes": ["agent:tools:validate"],
        },
        headers=_auth(admin_token),
    )
    assert service_token_response.status_code == 201, service_token_response.text
    service_token = service_token_response.json()["access_token"]

    validate = client.post(
        "/v1/tools/validate-alias",
        json={
            "profile_name": "default_it",
            "canonical_value": "kubernetes",
            "alias_value": "kube",
            "slot": "tool",
            "proposal_source_type": "agent",
            "proposal_source_name": "openrouter-alias-scout",
            "idempotency_key": "role-boundary:kube",
        },
        headers=_auth(service_token),
    )
    assert validate.status_code == 200, validate.text

    forbidden_apply = client.post(
        "/v1/governance/profiles/default_it/suggestions/apply-batch",
        json={},
        headers=_auth(service_token),
    )
    assert forbidden_apply.status_code == 403
