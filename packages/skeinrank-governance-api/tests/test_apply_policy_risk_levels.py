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
    response = client.post(
        "/v1/governance/profiles/default_it/terms",
        json={"canonical_value": "postgresql", "slot": "database"},
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


def test_low_risk_proposal_exposes_apply_policy(tmp_path):
    client = _client(tmp_path)
    _seed_profile(client)

    response = client.post(
        "/v1/governance/profiles/default_it/suggestions",
        json={
            "canonical_value": "postgresql",
            "alias_value": "pgx",
            "slot": "database",
            "confidence": 0.91,
            "proposal_source_type": "agent",
            "proposal_source_name": "openrouter-alias-scout",
            "idempotency_key": "agent:pgx:postgresql",
            "source_payload": {"evidence_count": 3},
        },
    )

    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["risk_level"] == "low"
    assert payload["apply_policy"]["schema_version"] == "skeinrank.apply_policy.v1"
    assert payload["apply_policy"]["decision"] == "batch_approve_allowed"
    assert payload["apply_policy"]["can_batch_apply"] is True
    assert payload["apply_policy"]["auto_apply_allowed"] is False
    assert payload["validation_summary"]["risk_level"] == "low"
    assert payload["validation_summary"]["apply_policy"]["decision"] == (
        "batch_approve_allowed"
    )


def test_medium_risk_warning_requires_review_in_batch_preview(tmp_path):
    client = _client(tmp_path)
    _seed_profile(client)

    response = client.post(
        "/v1/governance/profiles/default_it/suggestions",
        json={
            "canonical_value": "postgresql",
            "alias_value": "pg",
            "slot": "database",
            "confidence": 0.74,
            "proposal_source_type": "agent",
            "proposal_source_name": "openrouter-alias-scout",
            "idempotency_key": "agent:pg:postgresql",
        },
    )
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["risk_level"] == "medium"
    assert payload["apply_policy"]["decision"] == "review_required"
    assert payload["apply_policy"]["can_batch_apply"] is False
    assert "confidence_below_low_risk_threshold" in payload["apply_policy"]["reasons"]

    preview = client.post(
        "/v1/governance/profiles/default_it/suggestions/apply-batch/preview",
        json={"suggestion_ids": [payload["id"]], "allow_warnings": True},
    )

    assert preview.status_code == 200, preview.text
    item = preview.json()["items"][0]
    assert item["risk_level"] == "medium"
    assert item["policy_can_batch_apply"] is False
    assert item["policy_requires_admin"] is False
    assert "confidence_below_low_risk_threshold" in item["policy_reasons"]


def test_high_risk_blocked_alias_requires_admin_or_reject(tmp_path):
    client = _client(tmp_path)
    _seed_profile(client)
    client.post(
        "/v1/governance/profiles/default_it/terms/kubernetes/aliases",
        json={"alias_value": "kube", "confidence": 0.97},
    )

    response = client.post(
        "/v1/governance/profiles/default_it/suggestions",
        json={
            "canonical_value": "postgresql",
            "alias_value": "kube",
            "slot": "database",
            "confidence": 0.9,
            "proposal_source_type": "agent",
            "source_payload": {"risk_flags": ["conflict"]},
        },
    )

    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["validation_status"] == "blocked"
    assert payload["risk_level"] == "high"
    assert payload["apply_policy"]["decision"] == "admin_or_reject"
    assert payload["apply_policy"]["requires_admin"] is True
    assert payload["can_apply"] is False


def test_agent_tool_validate_alias_returns_apply_policy(tmp_path):
    client = _client(tmp_path)
    _seed_profile(client)
    binding_id = _create_binding(client)

    response = client.post(
        "/v1/tools/validate-alias",
        json={
            "binding_id": binding_id,
            "canonical_value": "kubernetes",
            "alias_value": "k8s",
            "slot": "tool",
            "confidence": 0.9,
            "proposal_source_name": "openrouter-alias-scout",
            "idempotency_key": "agent:k8s:kubernetes",
            "source_payload": {"llm_judgment": {"risk_flags": []}},
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["risk_level"] == "low"
    assert payload["apply_policy"]["decision"] == "batch_approve_allowed"
    assert payload["validation_summary"]["apply_policy"]["can_batch_apply"] is True
