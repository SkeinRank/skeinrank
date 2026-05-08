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


def test_profile_term_alias_workflow(tmp_path):
    client = _client(tmp_path)

    profile_response = client.post(
        "/v1/governance/profiles",
        json={"name": "default_it", "description": "Default IT terms"},
    )
    assert profile_response.status_code == 201
    assert profile_response.json()["name"] == "default_it"
    assert profile_response.json()["normalized_name"] == "default_it"

    profiles_response = client.get("/v1/governance/profiles")
    assert profiles_response.status_code == 200
    assert [item["name"] for item in profiles_response.json()] == ["default_it"]

    term_response = client.post(
        "/v1/governance/profiles/default_it/terms",
        json={"canonical_value": "kubernetes", "slot": "tool"},
    )
    assert term_response.status_code == 201
    assert term_response.json()["canonical_value"] == "kubernetes"
    assert term_response.json()["slot"] == "TOOL"
    assert term_response.json()["aliases"] == []

    alias_response = client.post(
        "/v1/governance/profiles/default_it/terms/kubernetes/aliases",
        json={"alias_value": "k8s", "confidence": 0.97},
    )
    assert alias_response.status_code == 201
    assert alias_response.json()["alias_value"] == "k8s"
    assert alias_response.json()["normalized_alias"] == "k8s"
    assert alias_response.json()["confidence"] == 0.97

    terms_response = client.get("/v1/governance/profiles/default_it/terms")
    assert terms_response.status_code == 200
    terms = terms_response.json()
    assert len(terms) == 1
    assert terms[0]["canonical_value"] == "kubernetes"
    assert terms[0]["aliases"][0]["alias_value"] == "k8s"

    term_detail_response = client.get(
        "/v1/governance/profiles/default_it/terms/kubernetes"
    )
    assert term_detail_response.status_code == 200
    assert term_detail_response.json()["aliases"][0]["alias_value"] == "k8s"


def test_duplicate_profile_returns_conflict(tmp_path):
    client = _client(tmp_path)

    assert (
        client.post("/v1/governance/profiles", json={"name": "default_it"}).status_code
        == 201
    )

    response = client.post("/v1/governance/profiles", json={"name": "Default IT"})

    assert response.status_code == 409
    assert "Profile already exists" in response.json()["detail"]


def test_missing_profile_returns_404_for_term_create(tmp_path):
    client = _client(tmp_path)

    response = client.post(
        "/v1/governance/profiles/missing/terms",
        json={"canonical_value": "kubernetes", "slot": "TOOL"},
    )

    assert response.status_code == 404
    assert "Profile not found" in response.json()["detail"]


def test_alias_collision_returns_conflict(tmp_path):
    client = _client(tmp_path)
    client.post("/v1/governance/profiles", json={"name": "default_it"})
    client.post(
        "/v1/governance/profiles/default_it/terms",
        json={"canonical_value": "postgresql", "slot": "DB"},
    )
    client.post(
        "/v1/governance/profiles/default_it/terms",
        json={"canonical_value": "payment-gateway", "slot": "SERVICE"},
    )
    first = client.post(
        "/v1/governance/profiles/default_it/terms/postgresql/aliases",
        json={"alias_value": "pg"},
    )
    assert first.status_code == 201

    response = client.post(
        "/v1/governance/profiles/default_it/terms/payment-gateway/aliases",
        json={"alias_value": "pg"},
    )

    assert response.status_code == 409
    assert "Alias already exists" in response.json()["detail"]


def test_missing_term_returns_404_for_alias_create(tmp_path):
    client = _client(tmp_path)
    client.post("/v1/governance/profiles", json={"name": "default_it"})

    response = client.post(
        "/v1/governance/profiles/default_it/terms/kubernetes/aliases",
        json={"alias_value": "k8s"},
    )

    assert response.status_code == 404
    assert "Canonical term not found" in response.json()["detail"]


def test_snapshot_export_returns_runtime_compatible_profile(tmp_path):
    client = _client(tmp_path)
    client.post("/v1/governance/profiles", json={"name": "default_it"})
    client.post(
        "/v1/governance/profiles/default_it/terms",
        json={"canonical_value": "kubernetes", "slot": "TOOL"},
    )
    client.post(
        "/v1/governance/profiles/default_it/terms/kubernetes/aliases",
        json={"alias_value": "k8s", "confidence": 0.97},
    )
    client.post(
        "/v1/governance/profiles/default_it/terms/kubernetes/aliases",
        json={"alias_value": "kube"},
    )

    response = client.post(
        "/v1/governance/profiles/default_it/snapshot/export",
        json={
            "snapshot_version": "default_it@v1",
            "description": "API exported snapshot",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["profile_id"] == "default_it"
    assert payload["snapshot"]["version"] == "default_it@v1"
    assert payload["snapshot"]["source"] == "postgres"
    assert payload["snapshot"]["description"] == "API exported snapshot"
    assert payload["alias_matcher"] == {"backend": "aho_corasick"}
    assert payload["rules"] == []
    assert payload["aliases"] == [
        {
            "slot": "TOOL",
            "canonical": "kubernetes",
            "aliases": [{"value": "k8s", "confidence": 0.97}, "kube"],
        }
    ]


def test_snapshot_export_accepts_empty_request_body(tmp_path):
    client = _client(tmp_path)
    client.post("/v1/governance/profiles", json={"name": "default_it"})

    response = client.post("/v1/governance/profiles/default_it/snapshot/export")

    assert response.status_code == 200
    payload = response.json()
    assert payload["profile_id"] == "default_it"
    assert payload["snapshot"]["version"] == "default_it@v1"
    assert payload["aliases"] == []


def test_snapshot_export_missing_profile_returns_404(tmp_path):
    client = _client(tmp_path)

    response = client.post(
        "/v1/governance/profiles/missing/snapshot/export",
        json={"snapshot_version": "missing@v1"},
    )

    assert response.status_code == 404
    assert "Profile not found" in response.json()["detail"]


def test_cors_preflight_allows_local_ui_origin(tmp_path):
    client = _client(tmp_path)

    response = client.options(
        "/v1/governance/profiles",
        headers={
            "Origin": "http://127.0.0.1:5173",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"


def test_update_profile_allows_rename_and_description_clear(tmp_path):
    client = _client(tmp_path)
    client.post(
        "/v1/governance/profiles",
        json={"name": "default_it", "description": "Default IT terms"},
    )

    response = client.patch(
        "/v1/governance/profiles/default_it",
        json={"name": "Infra Incidents", "description": None},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["name"] == "Infra Incidents"
    assert payload["normalized_name"] == "infra_incidents"
    assert payload["description"] is None

    old_response = client.get("/v1/governance/profiles/default_it/terms")
    assert old_response.status_code == 404


def test_update_profile_rename_collision_returns_conflict(tmp_path):
    client = _client(tmp_path)
    client.post("/v1/governance/profiles", json={"name": "default_it"})
    client.post("/v1/governance/profiles", json={"name": "security_docs"})

    response = client.patch(
        "/v1/governance/profiles/security_docs",
        json={"name": "Default IT"},
    )

    assert response.status_code == 409
    assert "Profile already exists" in response.json()["detail"]


def test_delete_profile_removes_profile_and_children(tmp_path):
    client = _client(tmp_path)
    client.post("/v1/governance/profiles", json={"name": "default_it"})
    client.post(
        "/v1/governance/profiles/default_it/terms",
        json={"canonical_value": "kubernetes", "slot": "TOOL"},
    )

    response = client.delete("/v1/governance/profiles/default_it")

    assert response.status_code == 204
    profiles_response = client.get("/v1/governance/profiles")
    assert profiles_response.status_code == 200
    assert profiles_response.json() == []
    terms_response = client.get("/v1/governance/profiles/default_it/terms")
    assert terms_response.status_code == 404


def test_update_term_allows_rename_slot_status_and_description_clear(tmp_path):
    client = _client(tmp_path)
    client.post("/v1/governance/profiles", json={"name": "default_it"})
    client.post(
        "/v1/governance/profiles/default_it/terms",
        json={
            "canonical_value": "kubernetes",
            "slot": "tool",
            "description": "Container platform",
        },
    )
    client.post(
        "/v1/governance/profiles/default_it/terms/kubernetes/aliases",
        json={"alias_value": "k8s"},
    )

    response = client.patch(
        "/v1/governance/profiles/default_it/terms/kubernetes",
        json={
            "canonical_value": "Kubernetes Platform",
            "slot": "platform",
            "status": "deprecated",
            "description": None,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["canonical_value"] == "Kubernetes Platform"
    assert payload["normalized_value"] == "kubernetes platform"
    assert payload["slot"] == "PLATFORM"
    assert payload["status"] == "deprecated"
    assert payload["description"] is None
    assert payload["aliases"][0]["alias_value"] == "k8s"

    old_response = client.get("/v1/governance/profiles/default_it/terms/kubernetes")
    assert old_response.status_code == 404


def test_update_term_collision_returns_conflict(tmp_path):
    client = _client(tmp_path)
    client.post("/v1/governance/profiles", json={"name": "default_it"})
    client.post(
        "/v1/governance/profiles/default_it/terms",
        json={"canonical_value": "postgresql", "slot": "DB"},
    )
    client.post(
        "/v1/governance/profiles/default_it/terms",
        json={"canonical_value": "kubernetes", "slot": "TOOL"},
    )

    response = client.patch(
        "/v1/governance/profiles/default_it/terms/kubernetes",
        json={"canonical_value": "PostgreSQL"},
    )

    assert response.status_code == 409
    assert "Canonical term already exists" in response.json()["detail"]


def test_update_term_rejects_invalid_status(tmp_path):
    client = _client(tmp_path)
    client.post("/v1/governance/profiles", json={"name": "default_it"})
    client.post(
        "/v1/governance/profiles/default_it/terms",
        json={"canonical_value": "kubernetes", "slot": "TOOL"},
    )

    response = client.patch(
        "/v1/governance/profiles/default_it/terms/kubernetes",
        json={"status": "pending"},
    )

    assert response.status_code == 422
    assert "Invalid term status" in response.json()["detail"]


def test_delete_term_removes_term_and_aliases(tmp_path):
    client = _client(tmp_path)
    client.post("/v1/governance/profiles", json={"name": "default_it"})
    client.post(
        "/v1/governance/profiles/default_it/terms",
        json={"canonical_value": "kubernetes", "slot": "TOOL"},
    )
    client.post(
        "/v1/governance/profiles/default_it/terms/kubernetes/aliases",
        json={"alias_value": "k8s"},
    )

    response = client.delete("/v1/governance/profiles/default_it/terms/kubernetes")

    assert response.status_code == 204
    terms_response = client.get("/v1/governance/profiles/default_it/terms")
    assert terms_response.status_code == 200
    assert terms_response.json() == []


def test_update_alias_allows_value_status_confidence_and_notes_clear(tmp_path):
    client = _client(tmp_path)
    client.post("/v1/governance/profiles", json={"name": "default_it"})
    client.post(
        "/v1/governance/profiles/default_it/terms",
        json={"canonical_value": "kubernetes", "slot": "TOOL"},
    )
    created = client.post(
        "/v1/governance/profiles/default_it/terms/kubernetes/aliases",
        json={"alias_value": "k8s", "confidence": 1.0, "notes": "Manual alias"},
    )
    alias_id = created.json()["id"]

    response = client.patch(
        f"/v1/governance/profiles/default_it/terms/kubernetes/aliases/{alias_id}",
        json={
            "alias_value": "kube",
            "confidence": 0.84,
            "status": "ambiguous",
            "notes": None,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["alias_value"] == "kube"
    assert payload["normalized_alias"] == "kube"
    assert payload["confidence"] == 0.84
    assert payload["status"] == "ambiguous"
    assert payload["notes"] is None


def test_update_alias_collision_returns_conflict(tmp_path):
    client = _client(tmp_path)
    client.post("/v1/governance/profiles", json={"name": "default_it"})
    client.post(
        "/v1/governance/profiles/default_it/terms",
        json={"canonical_value": "kubernetes", "slot": "TOOL"},
    )
    first = client.post(
        "/v1/governance/profiles/default_it/terms/kubernetes/aliases",
        json={"alias_value": "k8s"},
    )
    second = client.post(
        "/v1/governance/profiles/default_it/terms/kubernetes/aliases",
        json={"alias_value": "kube"},
    )
    assert first.status_code == 201
    assert second.status_code == 201

    response = client.patch(
        f"/v1/governance/profiles/default_it/terms/kubernetes/aliases/{second.json()['id']}",
        json={"alias_value": "K8S"},
    )

    assert response.status_code == 409
    assert "Alias already exists" in response.json()["detail"]


def test_update_alias_rejects_invalid_status(tmp_path):
    client = _client(tmp_path)
    client.post("/v1/governance/profiles", json={"name": "default_it"})
    client.post(
        "/v1/governance/profiles/default_it/terms",
        json={"canonical_value": "kubernetes", "slot": "TOOL"},
    )
    created = client.post(
        "/v1/governance/profiles/default_it/terms/kubernetes/aliases",
        json={"alias_value": "k8s"},
    )

    response = client.patch(
        f"/v1/governance/profiles/default_it/terms/kubernetes/aliases/{created.json()['id']}",
        json={"status": "unknown"},
    )

    assert response.status_code == 422
    assert "Invalid alias status" in response.json()["detail"]


def test_delete_alias_removes_alias_from_term(tmp_path):
    client = _client(tmp_path)
    client.post("/v1/governance/profiles", json={"name": "default_it"})
    client.post(
        "/v1/governance/profiles/default_it/terms",
        json={"canonical_value": "kubernetes", "slot": "TOOL"},
    )
    created = client.post(
        "/v1/governance/profiles/default_it/terms/kubernetes/aliases",
        json={"alias_value": "k8s"},
    )

    response = client.delete(
        f"/v1/governance/profiles/default_it/terms/kubernetes/aliases/{created.json()['id']}"
    )

    assert response.status_code == 204
    terms_response = client.get("/v1/governance/profiles/default_it/terms")
    assert terms_response.status_code == 200
    assert terms_response.json()[0]["aliases"] == []


def test_delete_alias_missing_alias_returns_404(tmp_path):
    client = _client(tmp_path)
    client.post("/v1/governance/profiles", json={"name": "default_it"})
    client.post(
        "/v1/governance/profiles/default_it/terms",
        json={"canonical_value": "kubernetes", "slot": "TOOL"},
    )

    response = client.delete(
        "/v1/governance/profiles/default_it/terms/kubernetes/aliases/999"
    )

    assert response.status_code == 404
    assert "Alias not found" in response.json()["detail"]


def test_suggestion_lifecycle_approves_into_active_alias(tmp_path):
    client = _client(tmp_path)
    client.post("/v1/governance/profiles", json={"name": "default_it"})
    client.post(
        "/v1/governance/profiles/default_it/terms",
        json={"canonical_value": "kubernetes", "slot": "tool"},
    )

    suggestion_response = client.post(
        "/v1/governance/profiles/default_it/suggestions",
        json={
            "canonical_value": "kubernetes",
            "alias_value": "kube",
            "slot": "tool",
            "confidence": 0.82,
            "source": "manual",
            "context": "People search for kube in incident runbooks.",
        },
    )
    assert suggestion_response.status_code == 201
    suggestion = suggestion_response.json()
    assert suggestion["status"] == "pending"
    assert suggestion["normalized_canonical"] == "kubernetes"
    assert suggestion["normalized_alias"] == "kube"
    assert suggestion["slot"] == "TOOL"
    assert suggestion["created_by"] == "local_dev"

    list_response = client.get(
        "/v1/governance/profiles/default_it/suggestions?status=pending"
    )
    assert list_response.status_code == 200
    assert [item["alias_value"] for item in list_response.json()] == ["kube"]

    approve_response = client.post(
        f"/v1/governance/profiles/default_it/suggestions/{suggestion['id']}/approve",
        json={"review_comment": "Looks good."},
    )
    assert approve_response.status_code == 200
    approved = approve_response.json()
    assert approved["status"] == "approved"
    assert approved["alias_id"] is not None
    assert approved["reviewed_by"] == "local_dev"
    assert approved["review_comment"] == "Looks good."

    terms_response = client.get("/v1/governance/profiles/default_it/terms")
    assert terms_response.status_code == 200
    aliases = terms_response.json()[0]["aliases"]
    assert aliases[0]["alias_value"] == "kube"
    assert aliases[0]["confidence"] == 0.82
    assert aliases[0]["status"] == "active"
    assert aliases[0]["notes"] == "People search for kube in incident runbooks."


def test_suggestion_reject_does_not_create_alias(tmp_path):
    client = _client(tmp_path)
    client.post("/v1/governance/profiles", json={"name": "default_it"})
    client.post(
        "/v1/governance/profiles/default_it/terms",
        json={"canonical_value": "kubernetes", "slot": "TOOL"},
    )
    suggestion_response = client.post(
        "/v1/governance/profiles/default_it/suggestions",
        json={
            "canonical_value": "kubernetes",
            "alias_value": "bad-kube",
            "slot": "TOOL",
        },
    )
    suggestion_id = suggestion_response.json()["id"]

    reject_response = client.post(
        f"/v1/governance/profiles/default_it/suggestions/{suggestion_id}/reject",
        json={"review_comment": "Not used by this corpus."},
    )

    assert reject_response.status_code == 200
    rejected = reject_response.json()
    assert rejected["status"] == "rejected"
    assert rejected["review_comment"] == "Not used by this corpus."

    terms_response = client.get("/v1/governance/profiles/default_it/terms")
    assert terms_response.status_code == 200
    assert terms_response.json()[0]["aliases"] == []


def test_approving_suggestion_requires_existing_canonical_term(tmp_path):
    client = _client(tmp_path)
    client.post("/v1/governance/profiles", json={"name": "default_it"})
    suggestion_response = client.post(
        "/v1/governance/profiles/default_it/suggestions",
        json={
            "canonical_value": "kubernetes",
            "alias_value": "kube",
            "slot": "TOOL",
        },
    )

    response = client.post(
        f"/v1/governance/profiles/default_it/suggestions/{suggestion_response.json()['id']}/approve"
    )

    assert response.status_code == 404
    assert "Canonical term not found" in response.json()["detail"]


def test_approving_suggestion_rejects_duplicate_alias(tmp_path):
    client = _client(tmp_path)
    client.post("/v1/governance/profiles", json={"name": "default_it"})
    client.post(
        "/v1/governance/profiles/default_it/terms",
        json={"canonical_value": "kubernetes", "slot": "TOOL"},
    )
    client.post(
        "/v1/governance/profiles/default_it/terms/kubernetes/aliases",
        json={"alias_value": "kube"},
    )
    suggestion_response = client.post(
        "/v1/governance/profiles/default_it/suggestions",
        json={
            "canonical_value": "kubernetes",
            "alias_value": "Kube",
            "slot": "TOOL",
        },
    )

    response = client.post(
        f"/v1/governance/profiles/default_it/suggestions/{suggestion_response.json()['id']}/approve"
    )

    assert response.status_code == 409
    assert "Alias already exists" in response.json()["detail"]


def test_suggestion_cannot_be_reviewed_twice(tmp_path):
    client = _client(tmp_path)
    client.post("/v1/governance/profiles", json={"name": "default_it"})
    client.post(
        "/v1/governance/profiles/default_it/terms",
        json={"canonical_value": "kubernetes", "slot": "TOOL"},
    )
    suggestion_response = client.post(
        "/v1/governance/profiles/default_it/suggestions",
        json={
            "canonical_value": "kubernetes",
            "alias_value": "kube",
            "slot": "TOOL",
        },
    )
    suggestion_id = suggestion_response.json()["id"]

    first = client.post(
        f"/v1/governance/profiles/default_it/suggestions/{suggestion_id}/reject"
    )
    assert first.status_code == 200

    second = client.post(
        f"/v1/governance/profiles/default_it/suggestions/{suggestion_id}/approve"
    )
    assert second.status_code == 409
    assert "Suggestion is not pending" in second.json()["detail"]


def test_suggestion_rejects_invalid_source_and_status_filter(tmp_path):
    client = _client(tmp_path)
    client.post("/v1/governance/profiles", json={"name": "default_it"})

    invalid_source = client.post(
        "/v1/governance/profiles/default_it/suggestions",
        json={
            "canonical_value": "kubernetes",
            "alias_value": "kube",
            "slot": "TOOL",
            "source": "crawler",
        },
    )
    assert invalid_source.status_code == 422
    assert "Invalid suggestion source status" in invalid_source.json()["detail"]

    invalid_status = client.get(
        "/v1/governance/profiles/default_it/suggestions?status=merged"
    )
    assert invalid_status.status_code == 422
    assert "Invalid suggestion status" in invalid_status.json()["detail"]


def test_canonical_term_suggestion_lifecycle_approves_into_active_term(tmp_path):
    client = _client(tmp_path)
    client.post("/v1/governance/profiles", json={"name": "default_it"})

    suggestion_response = client.post(
        "/v1/governance/profiles/default_it/suggestions",
        json={
            "suggestion_type": "canonical_term",
            "canonical_value": "vector database",
            "slot": "tool",
            "description": "Storage system optimized for vector search.",
            "context": "No canonical term exists for vector databases yet.",
        },
    )
    assert suggestion_response.status_code == 201
    suggestion = suggestion_response.json()
    assert suggestion["suggestion_type"] == "canonical_term"
    assert suggestion["alias_value"] is None
    assert suggestion["normalized_alias"] is None
    assert suggestion["term_id"] is None
    assert suggestion["description"] == "Storage system optimized for vector search."
    assert suggestion["slot"] == "TOOL"

    approve_response = client.post(
        f"/v1/governance/profiles/default_it/suggestions/{suggestion['id']}/approve",
        json={"review_comment": "Canonical term is useful."},
    )
    assert approve_response.status_code == 200
    approved = approve_response.json()
    assert approved["status"] == "approved"
    assert approved["term_id"] is not None
    assert approved["alias_id"] is None
    assert approved["review_comment"] == "Canonical term is useful."

    terms_response = client.get("/v1/governance/profiles/default_it/terms")
    assert terms_response.status_code == 200
    terms = terms_response.json()
    assert len(terms) == 1
    assert terms[0]["canonical_value"] == "vector database"
    assert terms[0]["normalized_value"] == "vector database"
    assert terms[0]["slot"] == "TOOL"
    assert terms[0]["description"] == "Storage system optimized for vector search."
    assert terms[0]["status"] == "active"
    assert terms[0]["aliases"] == []


def test_canonical_term_suggestion_create_rejects_existing_term(tmp_path):
    client = _client(tmp_path)
    client.post("/v1/governance/profiles", json={"name": "default_it"})
    client.post(
        "/v1/governance/profiles/default_it/terms",
        json={"canonical_value": "kubernetes", "slot": "TOOL"},
    )

    response = client.post(
        "/v1/governance/profiles/default_it/suggestions",
        json={
            "suggestion_type": "canonical_term",
            "canonical_value": "Kubernetes",
            "slot": "TOOL",
        },
    )

    assert response.status_code == 409
    assert "Canonical term already exists" in response.json()["detail"]


def test_canonical_term_suggestion_approve_rejects_existing_term(tmp_path):
    client = _client(tmp_path)
    client.post("/v1/governance/profiles", json={"name": "default_it"})
    suggestion_response = client.post(
        "/v1/governance/profiles/default_it/suggestions",
        json={
            "suggestion_type": "canonical_term",
            "canonical_value": "kubernetes",
            "slot": "TOOL",
        },
    )
    assert suggestion_response.status_code == 201
    client.post(
        "/v1/governance/profiles/default_it/terms",
        json={"canonical_value": "Kubernetes", "slot": "TOOL"},
    )

    response = client.post(
        f"/v1/governance/profiles/default_it/suggestions/{suggestion_response.json()['id']}/approve"
    )

    assert response.status_code == 409
    assert "Canonical term already exists" in response.json()["detail"]


def test_alias_suggestion_requires_alias_value(tmp_path):
    client = _client(tmp_path)
    client.post("/v1/governance/profiles", json={"name": "default_it"})

    response = client.post(
        "/v1/governance/profiles/default_it/suggestions",
        json={
            "suggestion_type": "alias",
            "canonical_value": "kubernetes",
            "slot": "TOOL",
        },
    )

    assert response.status_code == 422
    assert "Alias suggestions require alias_value" in response.json()["detail"]


def test_canonical_term_suggestion_rejects_alias_value(tmp_path):
    client = _client(tmp_path)
    client.post("/v1/governance/profiles", json={"name": "default_it"})

    response = client.post(
        "/v1/governance/profiles/default_it/suggestions",
        json={
            "suggestion_type": "canonical_term",
            "canonical_value": "vector database",
            "alias_value": "vectordb",
            "slot": "TOOL",
        },
    )

    assert response.status_code == 422
    assert "must not include alias_value" in response.json()["detail"]


def test_suggestion_rejects_invalid_type(tmp_path):
    client = _client(tmp_path)
    client.post("/v1/governance/profiles", json={"name": "default_it"})

    response = client.post(
        "/v1/governance/profiles/default_it/suggestions",
        json={
            "suggestion_type": "rename",
            "canonical_value": "kubernetes",
            "alias_value": "kube",
            "slot": "TOOL",
        },
    )

    assert response.status_code == 422
    assert "Invalid suggestion type status" in response.json()["detail"]


def test_stop_list_crud_workflow(tmp_path):
    client = _client(tmp_path)
    client.post("/v1/governance/profiles", json={"name": "default_it"})

    create_response = client.post(
        "/v1/governance/profiles/default_it/stop-list",
        json={
            "value": "Service",
            "target": "alias",
            "reason": "Too generic for this profile.",
        },
    )
    assert create_response.status_code == 201
    created = create_response.json()
    assert created["value"] == "Service"
    assert created["normalized_value"] == "service"
    assert created["target"] == "alias"
    assert created["is_active"] is True

    list_response = client.get("/v1/governance/profiles/default_it/stop-list")
    assert list_response.status_code == 200
    assert [entry["normalized_value"] for entry in list_response.json()] == ["service"]

    update_response = client.patch(
        f"/v1/governance/profiles/default_it/stop-list/{created['id']}",
        json={"value": "Application", "target": "both", "is_active": False},
    )
    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["normalized_value"] == "application"
    assert updated["target"] == "both"
    assert updated["is_active"] is False

    delete_response = client.delete(
        f"/v1/governance/profiles/default_it/stop-list/{created['id']}"
    )
    assert delete_response.status_code == 204
    assert client.get("/v1/governance/profiles/default_it/stop-list").json() == []


def test_stop_list_rejects_invalid_target_and_duplicate_overlap(tmp_path):
    client = _client(tmp_path)
    client.post("/v1/governance/profiles", json={"name": "default_it"})

    invalid = client.post(
        "/v1/governance/profiles/default_it/stop-list",
        json={"value": "service", "target": "unknown"},
    )
    assert invalid.status_code == 422
    assert "Invalid stop-list target" in invalid.json()["detail"]

    first = client.post(
        "/v1/governance/profiles/default_it/stop-list",
        json={"value": "service", "target": "both"},
    )
    assert first.status_code == 201

    overlap = client.post(
        "/v1/governance/profiles/default_it/stop-list",
        json={"value": " Service ", "target": "alias"},
    )
    assert overlap.status_code == 409
    assert "Stop-list entry already exists" in overlap.json()["detail"]


def test_stop_list_blocks_direct_alias_and_alias_suggestions(tmp_path):
    client = _client(tmp_path)
    client.post("/v1/governance/profiles", json={"name": "default_it"})
    client.post(
        "/v1/governance/profiles/default_it/terms",
        json={"canonical_value": "kubernetes", "slot": "TOOL"},
    )
    client.post(
        "/v1/governance/profiles/default_it/stop-list",
        json={
            "value": "kube",
            "target": "alias",
            "reason": "Use k8s for this profile.",
        },
    )

    direct_alias = client.post(
        "/v1/governance/profiles/default_it/terms/kubernetes/aliases",
        json={"alias_value": "kube"},
    )
    assert direct_alias.status_code == 409
    assert "Alias is blocked by stop list" in direct_alias.json()["detail"]
    assert "Use k8s" in direct_alias.json()["detail"]

    suggestion = client.post(
        "/v1/governance/profiles/default_it/suggestions",
        json={
            "canonical_value": "kubernetes",
            "alias_value": "kube",
            "slot": "TOOL",
        },
    )
    assert suggestion.status_code == 409
    assert "Alias suggestion is blocked by stop list" in suggestion.json()["detail"]


def test_stop_list_rechecks_alias_on_approve(tmp_path):
    client = _client(tmp_path)
    client.post("/v1/governance/profiles", json={"name": "default_it"})
    client.post(
        "/v1/governance/profiles/default_it/terms",
        json={"canonical_value": "kubernetes", "slot": "TOOL"},
    )
    suggestion_response = client.post(
        "/v1/governance/profiles/default_it/suggestions",
        json={
            "canonical_value": "kubernetes",
            "alias_value": "kube",
            "slot": "TOOL",
        },
    )
    assert suggestion_response.status_code == 201
    client.post(
        "/v1/governance/profiles/default_it/stop-list",
        json={"value": "kube", "target": "alias"},
    )

    approve_response = client.post(
        f"/v1/governance/profiles/default_it/suggestions/{suggestion_response.json()['id']}/approve"
    )
    assert approve_response.status_code == 409
    assert (
        "Alias suggestion is blocked by stop list" in approve_response.json()["detail"]
    )


def test_stop_list_blocks_canonical_terms_and_canonical_suggestions(tmp_path):
    client = _client(tmp_path)
    client.post("/v1/governance/profiles", json={"name": "default_it"})
    client.post(
        "/v1/governance/profiles/default_it/stop-list",
        json={"value": "service", "target": "canonical"},
    )

    direct_term = client.post(
        "/v1/governance/profiles/default_it/terms",
        json={"canonical_value": "service", "slot": "SERVICE"},
    )
    assert direct_term.status_code == 409
    assert "Canonical term is blocked by stop list" in direct_term.json()["detail"]

    suggestion = client.post(
        "/v1/governance/profiles/default_it/suggestions",
        json={
            "suggestion_type": "canonical_term",
            "canonical_value": "service",
            "slot": "SERVICE",
        },
    )
    assert suggestion.status_code == 409
    assert (
        "Canonical term suggestion is blocked by stop list"
        in suggestion.json()["detail"]
    )


def test_elasticsearch_binding_crud_workflow(tmp_path):
    client = _client(tmp_path)
    client.post(
        "/v1/governance/profiles",
        json={"name": "infra_incidents", "description": "Infra incidents"},
    )
    client.post("/v1/governance/profiles", json={"name": "security_docs"})

    create_response = client.post(
        "/v1/governance/elasticsearch/bindings",
        json={
            "name": "infra docs",
            "profile_name": "infra_incidents",
            "description": "Apply infra terminology to docs.",
            "index_name": "docs",
            "text_fields": ["title", "body", "body", ""],
            "target_field": "skeinrank",
            "filter_field": "team",
            "filter_value": "infra",
            "mode": "dry_run",
            "write_strategy": "reindex_alias_swap",
        },
    )
    assert create_response.status_code == 201
    created = create_response.json()
    assert created["name"] == "infra docs"
    assert created["normalized_name"] == "infra_docs"
    assert created["profile_name"] == "infra_incidents"
    assert created["provider"] == "elasticsearch"
    assert created["text_fields"] == ["title", "body"]
    assert created["target_field"] == "skeinrank"
    assert created["filter_field"] == "team"
    assert created["filter_value"] == "infra"
    assert created["mode"] == "dry_run"
    assert created["write_strategy"] == "reindex_alias_swap"
    assert created["is_enabled"] is True

    list_response = client.get("/v1/governance/elasticsearch/bindings")
    assert list_response.status_code == 200
    assert [item["name"] for item in list_response.json()] == ["infra docs"]

    profile_filtered = client.get(
        "/v1/governance/elasticsearch/bindings?profile_name=infra_incidents"
    )
    assert profile_filtered.status_code == 200
    assert [item["name"] for item in profile_filtered.json()] == ["infra docs"]

    update_response = client.patch(
        f"/v1/governance/elasticsearch/bindings/{created['id']}",
        json={
            "name": "security docs",
            "profile_name": "security_docs",
            "index_name": "docs-security",
            "text_fields": ["content"],
            "target_field": "skeinrank.security",
            "filter_field": None,
            "filter_value": None,
            "mode": "write",
            "write_strategy": "in_place",
            "is_enabled": False,
        },
    )
    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["name"] == "security docs"
    assert updated["profile_name"] == "security_docs"
    assert updated["index_name"] == "docs-security"
    assert updated["text_fields"] == ["content"]
    assert updated["target_field"] == "skeinrank.security"
    assert updated["filter_field"] is None
    assert updated["filter_value"] is None
    assert updated["mode"] == "write"
    assert updated["write_strategy"] == "in_place"
    assert updated["is_enabled"] is False

    delete_response = client.delete(
        f"/v1/governance/elasticsearch/bindings/{created['id']}"
    )
    assert delete_response.status_code == 204
    assert client.get("/v1/governance/elasticsearch/bindings").json() == []


def test_elasticsearch_binding_rejects_invalid_config_and_duplicates(tmp_path):
    client = _client(tmp_path)
    client.post("/v1/governance/profiles", json={"name": "default_it"})

    missing_text_fields = client.post(
        "/v1/governance/elasticsearch/bindings",
        json={
            "name": "docs",
            "profile_name": "default_it",
            "index_name": "docs",
            "text_fields": ["", "  "],
            "target_field": "skeinrank",
        },
    )
    assert missing_text_fields.status_code == 422
    assert "at least one text field" in missing_text_fields.json()["detail"]

    partial_filter = client.post(
        "/v1/governance/elasticsearch/bindings",
        json={
            "name": "docs",
            "profile_name": "default_it",
            "index_name": "docs",
            "text_fields": ["body"],
            "target_field": "skeinrank",
            "filter_field": "team",
        },
    )
    assert partial_filter.status_code == 422
    assert "both filter_field and filter_value" in partial_filter.json()["detail"]

    invalid_mode = client.post(
        "/v1/governance/elasticsearch/bindings",
        json={
            "name": "docs",
            "profile_name": "default_it",
            "index_name": "docs",
            "text_fields": ["body"],
            "target_field": "skeinrank",
            "mode": "unsafe",
        },
    )
    assert invalid_mode.status_code == 422
    assert "Invalid Elasticsearch binding mode" in invalid_mode.json()["detail"]

    invalid_write_strategy = client.post(
        "/v1/governance/elasticsearch/bindings",
        json={
            "name": "docs",
            "profile_name": "default_it",
            "index_name": "docs",
            "text_fields": ["body"],
            "target_field": "skeinrank",
            "write_strategy": "unsafe",
        },
    )
    assert invalid_write_strategy.status_code == 422
    assert (
        "Invalid Elasticsearch binding write strategy"
        in invalid_write_strategy.json()["detail"]
    )

    first = client.post(
        "/v1/governance/elasticsearch/bindings",
        json={
            "name": "docs",
            "profile_name": "default_it",
            "index_name": "docs",
            "text_fields": ["body"],
            "target_field": "skeinrank",
        },
    )
    assert first.status_code == 201

    duplicate = client.post(
        "/v1/governance/elasticsearch/bindings",
        json={
            "name": "Docs",
            "profile_name": "default_it",
            "index_name": "docs-2",
            "text_fields": ["body"],
            "target_field": "skeinrank",
        },
    )
    assert duplicate.status_code == 409
    assert "Elasticsearch binding already exists" in duplicate.json()["detail"]


def test_elasticsearch_binding_requires_existing_profile(tmp_path):
    client = _client(tmp_path)

    response = client.post(
        "/v1/governance/elasticsearch/bindings",
        json={
            "name": "docs",
            "profile_name": "missing",
            "index_name": "docs",
            "text_fields": ["body"],
            "target_field": "skeinrank",
        },
    )

    assert response.status_code == 404
    assert "Profile not found" in response.json()["detail"]
