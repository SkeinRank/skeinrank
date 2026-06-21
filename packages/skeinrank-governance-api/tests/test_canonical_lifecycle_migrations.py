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


def _seed_checkout_profile(client: TestClient) -> None:
    response = client.post("/v1/governance/profiles", json={"name": "payments"})
    assert response.status_code == 201, response.text
    response = client.post(
        "/v1/governance/profiles/payments/terms",
        json={"canonical_value": "checkout", "slot": "service"},
    )
    assert response.status_code == 201, response.text
    response = client.post(
        "/v1/governance/profiles/payments/terms/checkout/aliases",
        json={"alias_value": "checkout-v2", "confidence": 0.91},
    )
    assert response.status_code == 201, response.text


def test_canonical_migration_preview_preserves_old_surfaces(tmp_path):
    client = _client(tmp_path)
    _seed_checkout_profile(client)

    response = client.post(
        "/v1/governance/profiles/payments/canonical-migrations/preview",
        json={
            "old_canonical_value": "checkout",
            "new_canonical_value": "payments-core",
            "evidence": {"docs_recent": 42},
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["action"] == "canonical_migration"
    assert payload["old_canonical_value"] == "checkout"
    assert payload["new_canonical_value"] == "payments-core"
    assert payload["slot"] == "SERVICE"
    assert payload["aliases_to_preserve"] == ["checkout", "checkout-v2"]
    assert payload["is_blocked"] is False


def test_canonical_migration_approval_demotes_old_canonical_and_preserves_aliases(
    tmp_path,
):
    client = _client(tmp_path)
    _seed_checkout_profile(client)

    created = client.post(
        "/v1/governance/profiles/payments/canonical-migrations",
        json={
            "old_canonical_value": "checkout",
            "new_canonical_value": "payments-core",
            "proposal_source_name": "drift-scout",
            "idempotency_key": "drift-scout:payments:checkout-to-payments-core",
            "evidence": {"new_docs_count": 40, "old_docs_count": 3},
        },
    )
    assert created.status_code == 201, created.text
    suggestion = created.json()
    assert suggestion["suggestion_type"] == "canonical_term"
    assert suggestion["validation_status"] == "warning"
    assert suggestion["can_approve"] is False
    lifecycle = suggestion["source_payload"]
    assert lifecycle["action"] == "canonical_migration"
    assert lifecycle["demote_old_canonical_to_alias"] is True

    blocked_without_override = client.post(
        f"/v1/governance/profiles/payments/suggestions/{suggestion['id']}/approve",
        json={"review_comment": "Needs explicit migration review."},
    )
    assert blocked_without_override.status_code == 409

    approved = client.post(
        f"/v1/governance/profiles/payments/suggestions/{suggestion['id']}/approve",
        json={
            "review_comment": "Docs now use payments-core.",
            "allow_warnings": True,
        },
    )
    assert approved.status_code == 200, approved.text
    approved_payload = approved.json()
    assert approved_payload["status"] == "approved"
    applied_payload = approved_payload["source_payload"]["applied_payload"]
    assert applied_payload["created_new_term"] is True

    terms = client.get("/v1/governance/profiles/payments/terms")
    assert terms.status_code == 200, terms.text
    by_value = {term["canonical_value"]: term for term in terms.json()}
    assert by_value["checkout"]["status"] == "deprecated"
    assert by_value["payments-core"]["status"] == "active"

    new_term = client.get("/v1/governance/profiles/payments/terms/payments-core")
    assert new_term.status_code == 200, new_term.text
    alias_values = {alias["alias_value"] for alias in new_term.json()["aliases"]}
    assert {"checkout", "checkout-v2"}.issubset(alias_values)


def test_canonical_migration_batch_apply_reports_migrated_canonical(tmp_path):
    client = _client(tmp_path)
    _seed_checkout_profile(client)

    created = client.post(
        "/v1/governance/profiles/payments/canonical-migrations",
        json={
            "old_canonical_value": "checkout",
            "new_canonical_value": "payments-core",
            "proposal_source_type": "agent",
        },
    )
    assert created.status_code == 201, created.text
    suggestion_id = created.json()["id"]

    preview = client.post(
        "/v1/governance/profiles/payments/suggestions/apply-batch/preview",
        json={"suggestion_ids": [suggestion_id], "allow_warnings": True},
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["items"][0]["apply_action"] == "migrate_canonical"

    applied = client.post(
        "/v1/governance/profiles/payments/suggestions/apply-batch",
        json={"suggestion_ids": [suggestion_id], "allow_warnings": True},
    )
    assert applied.status_code == 200, applied.text
    payload = applied.json()
    assert payload["migrated_canonicals"] == 1
    assert payload["suggestions"][0]["status"] == "approved"
