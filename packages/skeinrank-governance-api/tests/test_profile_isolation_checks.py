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


def _seed_profile(client: TestClient, name: str) -> None:
    response = client.post("/v1/governance/profiles", json={"name": name})
    assert response.status_code == 201, response.text
    response = client.post(
        f"/v1/governance/profiles/{name}/terms",
        json={"canonical_value": "kubernetes", "slot": "technology"},
    )
    assert response.status_code == 201, response.text
    response = client.post(
        f"/v1/governance/profiles/{name}/terms/kubernetes/aliases",
        json={"alias_value": "k8s", "confidence": 0.97},
    )
    assert response.status_code == 201, response.text


def _create_binding(
    client: TestClient, *, profile_name: str, name: str, index_name: str
) -> int:
    response = client.post(
        "/v1/governance/elasticsearch/bindings",
        json={
            "name": name,
            "profile_name": profile_name,
            "index_name": index_name,
            "text_fields": ["title", "body"],
            "target_field": "skeinrank",
            "mode": "dry_run",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_profile_isolation_endpoint_reports_clean_profile_boundaries(tmp_path):
    client = _client(tmp_path)
    _seed_profile(client, "infra")
    binding_id = _create_binding(
        client,
        profile_name="infra",
        name="Infra docs",
        index_name="infra-docs",
    )

    suggestion = client.post(
        "/v1/governance/profiles/infra/suggestions",
        json={
            "binding_id": binding_id,
            "canonical_value": "kubernetes",
            "alias_value": "kube",
            "slot": "technology",
            "confidence": 0.9,
            "idempotency_key": "isolation:kube",
        },
    )
    assert suggestion.status_code == 201, suggestion.text

    run = client.post(
        "/v1/agents/runs",
        json={"run_id": "isolation-run-001", "binding_id": binding_id},
    )
    assert run.status_code == 201, run.text
    visit = client.post(
        "/v1/agents/runs/isolation-run-001/document-visits",
        json={"source_id": "doc-001", "content": "k8s rollout failed"},
    )
    assert visit.status_code == 201, visit.text

    response = client.get("/v1/governance/isolation-checks")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["schema_version"] == "skeinrank.profile_isolation.v1"
    assert payload["status"] == "ok"
    assert payload["summary"]["bindings_total"] == 1
    assert payload["summary"]["suggestions_total"] == 1
    assert payload["summary"]["agent_runs_total"] == 1
    assert payload["summary"]["issues_total"] == 0
    checks = {check["name"]: check for check in payload["checks"]}
    assert checks["proposal_binding_profile_alignment"]["status"] == "ok"
    assert checks["agent_run_profile_binding_alignment"]["status"] == "ok"
    assert checks["agent_document_visit_alignment"]["status"] == "ok"
    assert payload["safety"]["read_only"] is True
    assert payload["safety"]["multi_tenant_claim"] is False


def test_governance_suggestions_reject_cross_profile_binding(tmp_path):
    client = _client(tmp_path)
    _seed_profile(client, "infra")
    _seed_profile(client, "product")
    product_binding_id = _create_binding(
        client,
        profile_name="product",
        name="Product docs",
        index_name="product-docs",
    )

    response = client.post(
        "/v1/governance/profiles/infra/suggestions",
        json={
            "binding_id": product_binding_id,
            "canonical_value": "kubernetes",
            "alias_value": "kube",
            "slot": "technology",
            "idempotency_key": "isolation:wrong-binding",
        },
    )

    assert response.status_code == 422
    assert "binding must belong" in response.json()["detail"]


def test_agent_tool_rejects_cross_profile_binding(tmp_path):
    client = _client(tmp_path)
    _seed_profile(client, "infra")
    _seed_profile(client, "product")
    product_binding_id = _create_binding(
        client,
        profile_name="product",
        name="Product docs",
        index_name="product-docs",
    )

    response = client.post(
        "/v1/tools/validate-alias",
        json={
            "profile_name": "infra",
            "binding_id": product_binding_id,
            "canonical_value": "kubernetes",
            "alias_value": "kube",
            "slot": "technology",
            "idempotency_key": "isolation:tool-mismatch",
        },
    )

    assert response.status_code == 409
    assert "Binding does not belong" in response.json()["detail"]


def test_runtime_query_plan_rejects_cross_profile_binding(tmp_path):
    client = _client(tmp_path)
    _seed_profile(client, "infra")
    _seed_profile(client, "product")
    product_binding_id = _create_binding(
        client,
        profile_name="product",
        name="Product docs",
        index_name="product-docs",
    )

    response = client.post(
        "/v1/query/plan",
        json={
            "profile_name": "infra",
            "binding_id": product_binding_id,
            "query": "k8s rollout",
        },
    )

    assert response.status_code == 409
    assert "Binding does not belong" in response.json()["detail"]


def test_agent_run_registry_rejects_cross_profile_binding(tmp_path):
    client = _client(tmp_path)
    _seed_profile(client, "infra")
    _seed_profile(client, "product")
    product_binding_id = _create_binding(
        client,
        profile_name="product",
        name="Product docs",
        index_name="product-docs",
    )

    response = client.post(
        "/v1/agents/runs",
        json={
            "run_id": "isolation-run-mismatch",
            "profile_name": "infra",
            "binding_id": product_binding_id,
        },
    )

    assert response.status_code == 400
    assert "different profile" in response.json()["detail"]
