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


def _service_token(
    client: TestClient,
    admin_token: str,
    *,
    name: str,
    scopes: list[str],
    role: str = "contributor",
) -> str:
    account = client.post(
        "/v1/auth/service-accounts",
        json={"name": name, "role": role},
        headers=_auth(admin_token),
    )
    assert account.status_code == 201, account.text
    token = client.post(
        f"/v1/auth/service-accounts/{name}/tokens",
        json={"name": f"{name} token", "scopes": scopes},
        headers=_auth(admin_token),
    )
    assert token.status_code == 201, token.text
    return token.json()["access_token"]


def _seed_profile_binding(client: TestClient, token: str) -> int:
    profile = client.post(
        "/v1/governance/profiles",
        json={"name": "default_it"},
        headers=_auth(token),
    )
    assert profile.status_code == 201, profile.text
    term = client.post(
        "/v1/governance/profiles/default_it/terms",
        json={"canonical_value": "kubernetes", "slot": "tool"},
        headers=_auth(token),
    )
    assert term.status_code == 201, term.text
    binding = client.post(
        "/v1/governance/elasticsearch/bindings",
        json={
            "name": "Default IT docs",
            "profile_name": "default_it",
            "index_name": "default-it-docs",
            "text_fields": ["title", "body"],
            "target_field": "skeinrank",
            "mode": "dry_run",
        },
        headers=_auth(token),
    )
    assert binding.status_code == 201, binding.text
    return binding.json()["id"]


def test_agent_run_api_tokens_require_run_scopes(tmp_path):
    client = _client(tmp_path)
    admin_token = _login(client)
    writer_token = _service_token(
        client,
        admin_token,
        name="agent-run-writer",
        scopes=["agent:runs:write", "agent:runs:read"],
    )
    read_only_token = _service_token(
        client,
        admin_token,
        name="agent-run-reader",
        scopes=["agent:runs:read"],
    )

    create_response = client.post(
        "/v1/agents/runs",
        json={"run_id": "run-scoped-001", "status": "queued"},
        headers=_auth(writer_token),
    )
    assert create_response.status_code == 201, create_response.text
    assert create_response.json()["requested_by"] == "agent-run-writer"

    forbidden_create = client.post(
        "/v1/agents/runs",
        json={"run_id": "run-scoped-002", "status": "queued"},
        headers=_auth(read_only_token),
    )
    assert forbidden_create.status_code == 403
    assert "agent:runs:write" in forbidden_create.json()["detail"]

    list_response = client.get(
        "/v1/agents/runs",
        headers=_auth(read_only_token),
    )
    assert list_response.status_code == 200, list_response.text
    assert [item["run_id"] for item in list_response.json()] == ["run-scoped-001"]


def test_agent_tracking_api_tokens_require_tracking_scopes(tmp_path):
    client = _client(tmp_path)
    admin_token = _login(client)
    binding_id = _seed_profile_binding(client, admin_token)
    client.post(
        "/v1/agents/runs",
        json={
            "run_id": "tracking-run-001",
            "profile_name": "default_it",
            "binding_id": binding_id,
        },
        headers=_auth(admin_token),
    )
    writer_token = _service_token(
        client,
        admin_token,
        name="tracking-writer",
        scopes=["agent:tracking:write", "agent:tracking:read"],
    )
    read_only_token = _service_token(
        client,
        admin_token,
        name="tracking-reader",
        scopes=["agent:tracking:read"],
    )

    forbidden_visit = client.post(
        "/v1/agents/runs/tracking-run-001/document-visits",
        json={"source_id": "doc-001", "content": "k8s rollout notes"},
        headers=_auth(read_only_token),
    )
    assert forbidden_visit.status_code == 403
    assert "agent:tracking:write" in forbidden_visit.json()["detail"]

    visit = client.post(
        "/v1/agents/runs/tracking-run-001/document-visits",
        json={"source_id": "doc-001", "content": "k8s rollout notes"},
        headers=_auth(writer_token),
    )
    assert visit.status_code == 201, visit.text

    list_visits = client.get(
        "/v1/agents/runs/tracking-run-001/document-visits",
        headers=_auth(read_only_token),
    )
    assert list_visits.status_code == 200, list_visits.text
    assert [item["source_id"] for item in list_visits.json()] == ["doc-001"]


def test_agent_tool_api_tokens_require_tool_scopes(tmp_path):
    client = _client(tmp_path)
    admin_token = _login(client)
    _seed_profile_binding(client, admin_token)
    validate_token = _service_token(
        client,
        admin_token,
        name="tool-validator",
        scopes=["agent:tools:validate"],
    )
    suggest_token = _service_token(
        client,
        admin_token,
        name="tool-suggester",
        scopes=["agent:tools:suggest"],
    )

    validate_response = client.post(
        "/v1/tools/validate-alias",
        json={
            "profile_name": "default_it",
            "canonical_value": "kubernetes",
            "alias_value": "k8s",
            "slot": "tool",
            "proposal_source_type": "agent",
            "proposal_source_name": "openrouter-alias-scout",
            "idempotency_key": "agent-tool-scope-test:k8s",
            "source_payload": {"test": "scoped-token"},
        },
        headers=_auth(validate_token),
    )
    assert validate_response.status_code == 200, validate_response.text

    forbidden_suggest = client.post(
        "/v1/tools/suggest-alias",
        json={
            "profile_name": "default_it",
            "canonical_value": "kubernetes",
            "alias_value": "kube",
            "slot": "tool",
            "proposal_source_type": "agent",
            "proposal_source_name": "openrouter-alias-scout",
            "idempotency_key": "agent-tool-scope-test:kube",
            "source_payload": {"test": "scoped-token"},
        },
        headers=_auth(validate_token),
    )
    assert forbidden_suggest.status_code == 403
    assert "agent:tools:suggest" in forbidden_suggest.json()["detail"]

    suggest_response = client.post(
        "/v1/tools/suggest-alias",
        json={
            "profile_name": "default_it",
            "canonical_value": "kubernetes",
            "alias_value": "kubectl",
            "slot": "tool",
            "proposal_source_type": "agent",
            "proposal_source_name": "openrouter-alias-scout",
            "idempotency_key": "agent-tool-scope-test:kubectl",
            "source_payload": {"test": "scoped-token"},
        },
        headers=_auth(suggest_token),
    )
    assert suggest_response.status_code == 201, suggest_response.text
    assert suggest_response.json()["created"] is True
