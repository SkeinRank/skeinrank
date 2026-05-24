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
        "/v1/governance/profiles/default_it/terms/kubernetes/aliases",
        json={"alias_value": "k8s", "confidence": 0.97},
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


def test_proposal_batch_apply_publishes_binding_snapshot(tmp_path):
    client = _client(tmp_path)
    _seed_profile(client)
    binding_id = _create_binding(client)

    canonical_response = client.post(
        "/v1/governance/profiles/default_it/suggestions",
        json={
            "suggestion_type": "canonical_term",
            "canonical_value": "postgresql",
            "slot": "database",
            "description": "Relational database.",
            "proposal_source_type": "agent",
            "proposal_source_name": "search-log-scout",
        },
    )
    assert canonical_response.status_code == 201, canonical_response.text
    alias_response = client.post(
        "/v1/governance/profiles/default_it/suggestions",
        json={
            "canonical_value": "postgresql",
            "alias_value": "pg",
            "slot": "database",
            "binding_id": binding_id,
            "confidence": 0.91,
            "proposal_source_type": "agent",
            "proposal_source_name": "search-log-scout",
        },
    )
    assert alias_response.status_code == 201, alias_response.text

    response = client.post(
        "/v1/governance/profiles/default_it/suggestions/apply-batch",
        json={
            "suggestion_ids": [
                canonical_response.json()["id"],
                alias_response.json()["id"],
            ],
            "review_comment": "Apply agent batch.",
            "publish_snapshot": True,
            "binding_id": binding_id,
            "snapshot_version": "default_it@agent-batch-1",
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "applied"
    assert payload["created_terms"] == 1
    assert payload["created_aliases"] == 1
    assert payload["applied_suggestion_ids"] == [
        canonical_response.json()["id"],
        alias_response.json()["id"],
    ]
    assert payload["snapshot"] == {
        "published": True,
        "binding_id": binding_id,
        "snapshot_version": "default_it@agent-batch-1",
        "snapshot_status": "ready",
        "checksum": payload["snapshot"]["checksum"],
        "alias_entries_total": 2,
    }
    assert payload["snapshot"]["checksum"]
    assert {item["status"] for item in payload["suggestions"]} == {"approved"}
    assert {item["review_comment"] for item in payload["suggestions"]} == {
        "Apply agent batch."
    }

    binding_response = client.get("/v1/governance/elasticsearch/bindings")
    assert binding_response.status_code == 200
    binding = binding_response.json()[0]
    assert binding["last_successful_snapshot_version"] == "default_it@agent-batch-1"
    assert binding["snapshot_status"] == "ready"

    terms_response = client.get("/v1/governance/profiles/default_it/terms")
    assert terms_response.status_code == 200
    terms = {item["canonical_value"]: item for item in terms_response.json()}
    assert terms["postgresql"]["aliases"][0]["alias_value"] == "pg"


def test_proposal_batch_apply_without_ids_applies_all_pending(tmp_path):
    client = _client(tmp_path)
    _seed_profile(client)

    first = client.post(
        "/v1/governance/profiles/default_it/suggestions",
        json={"canonical_value": "kubernetes", "alias_value": "kube", "slot": "tool"},
    )
    second = client.post(
        "/v1/governance/profiles/default_it/suggestions",
        json={
            "canonical_value": "kubernetes",
            "alias_value": "kubectl",
            "slot": "tool",
        },
    )
    assert first.status_code == 201
    assert second.status_code == 201

    response = client.post("/v1/governance/profiles/default_it/suggestions/apply-batch")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["created_aliases"] == 2
    assert payload["snapshot"]["published"] is False
    assert payload["applied_suggestion_ids"] == [
        first.json()["id"],
        second.json()["id"],
    ]


def test_proposal_batch_apply_rejects_blocked_validation_summary(tmp_path):
    client = _client(tmp_path)
    _seed_profile(client)
    term_response = client.post(
        "/v1/governance/profiles/default_it/terms",
        json={"canonical_value": "postgresql", "slot": "database"},
    )
    assert term_response.status_code == 201, term_response.text

    suggestion = client.post(
        "/v1/governance/profiles/default_it/suggestions",
        json={
            "canonical_value": "postgresql",
            "alias_value": "k8s",
            "slot": "database",
        },
    )
    assert suggestion.status_code == 201
    assert suggestion.json()["validation_summary"]["status"] == "blocked"

    response = client.post(
        "/v1/governance/profiles/default_it/suggestions/apply-batch",
        json={"suggestion_ids": [suggestion.json()["id"]]},
    )

    assert response.status_code == 409
    assert "blocked suggestions" in response.json()["detail"]


def test_proposal_batch_publish_requires_matching_binding(tmp_path):
    client = _client(tmp_path)
    _seed_profile(client)
    binding_id = _create_binding(client)
    client.post("/v1/governance/profiles", json={"name": "security_docs"})
    suggestion = client.post(
        "/v1/governance/profiles/security_docs/suggestions",
        json={
            "suggestion_type": "canonical_term",
            "canonical_value": "falco",
            "slot": "tool",
        },
    )
    assert suggestion.status_code == 201

    response = client.post(
        "/v1/governance/profiles/security_docs/suggestions/apply-batch",
        json={
            "suggestion_ids": [suggestion.json()["id"]],
            "publish_snapshot": True,
            "binding_id": binding_id,
        },
    )

    assert response.status_code == 422
    assert "binding must belong" in response.json()["detail"]


def test_proposal_batch_apply_preview_reports_warnings_without_mutation(tmp_path):
    client = _client(tmp_path)
    _seed_profile(client)
    suggestion = client.post(
        "/v1/governance/profiles/default_it/suggestions",
        json={
            "canonical_value": "kubernetes",
            "alias_value": "kube",
            "slot": "tool",
            "validation_summary": {
                "schema_version": "skeinrank.proposal_validation.v1",
                "status": "warning",
                "counts": {"passed": 1, "warning": 1, "blocked": 0, "skipped": 0},
                "checks": {
                    "manual_review": {
                        "status": "warning",
                        "severity": "warning",
                        "message": "Synthetic warning for preview.",
                    }
                },
            },
        },
    )
    assert suggestion.status_code == 201, suggestion.text

    response = client.post(
        "/v1/governance/profiles/default_it/suggestions/apply-batch/preview",
        json={"suggestion_ids": [suggestion.json()["id"]]},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "needs_review"
    assert payload["suggestions_total"] == 1
    assert payload["applyable_suggestions"] == 0
    assert payload["warning_suggestions"] == 1
    assert payload["items"][0]["validation_status"] == "warning"
    assert payload["items"][0]["applyable"] is False
    assert payload["items"][0]["warning_reasons"] == [
        "manual_review: Synthetic warning for preview."
    ]

    listed = client.get("/v1/governance/profiles/default_it/suggestions?status=pending")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [suggestion.json()["id"]]


def test_proposal_batch_apply_rejects_warnings_by_default(tmp_path):
    client = _client(tmp_path)
    _seed_profile(client)
    suggestion = client.post(
        "/v1/governance/profiles/default_it/suggestions",
        json={
            "canonical_value": "kubernetes",
            "alias_value": "kube",
            "slot": "tool",
            "validation_summary": {
                "schema_version": "skeinrank.proposal_validation.v1",
                "status": "warning",
                "counts": {"passed": 1, "warning": 1, "blocked": 0, "skipped": 0},
                "checks": {
                    "manual_review": {
                        "status": "warning",
                        "severity": "warning",
                        "message": "Synthetic warning for apply hardening.",
                    }
                },
            },
        },
    )
    assert suggestion.status_code == 201, suggestion.text

    response = client.post(
        "/v1/governance/profiles/default_it/suggestions/apply-batch",
        json={"suggestion_ids": [suggestion.json()["id"]]},
    )

    assert response.status_code == 409
    assert "validation warnings" in response.json()["detail"]


def test_proposal_batch_apply_allows_warnings_when_explicit(tmp_path):
    client = _client(tmp_path)
    _seed_profile(client)
    suggestion = client.post(
        "/v1/governance/profiles/default_it/suggestions",
        json={
            "canonical_value": "kubernetes",
            "alias_value": "kube",
            "slot": "tool",
            "validation_summary": {
                "schema_version": "skeinrank.proposal_validation.v1",
                "status": "warning",
                "counts": {"passed": 1, "warning": 1, "blocked": 0, "skipped": 0},
                "checks": {
                    "manual_review": {
                        "status": "warning",
                        "severity": "warning",
                        "message": "Synthetic warning for explicit apply.",
                    }
                },
            },
        },
    )
    assert suggestion.status_code == 201, suggestion.text

    response = client.post(
        "/v1/governance/profiles/default_it/suggestions/apply-batch",
        json={"suggestion_ids": [suggestion.json()["id"]], "allow_warnings": True},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["created_aliases"] == 1
    assert payload["suggestions"][0]["status"] == "approved"
