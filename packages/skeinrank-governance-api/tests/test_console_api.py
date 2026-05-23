from __future__ import annotations

from fastapi.testclient import TestClient
from skeinrank_governance_api import GovernanceApiConfig, create_app


def _client(tmp_path, *, auth_enabled: bool = False) -> TestClient:
    app = create_app(
        GovernanceApiConfig(
            database_url=f"sqlite:///{tmp_path / 'governance.db'}",
            create_tables_on_startup=True,
            auth_enabled=auth_enabled,
            bootstrap_admin=auth_enabled,
            admin_username="admin",
            admin_password="admin-secret",
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


def _dictionary_payload() -> dict:
    return {
        "profile_name": "infra_incidents",
        "profile_description": "Infra incident dictionary",
        "terms": [
            {
                "canonical_value": "kubernetes",
                "slot": "TOOL",
                "description": "Container orchestration platform",
                "aliases": [
                    "k8s",
                    {"value": "kube", "confidence": 0.95, "notes": "short form"},
                ],
            },
            {
                "canonical_value": "postgresql",
                "slot": "DATABASE",
                "aliases": ["postgres", "pg"],
            },
        ],
        "profile_stop_list": [
            {"value": "tmp", "target": "alias", "reason": "too generic"}
        ],
        "global_stop_list": [
            {"value": "unknown", "target": "both", "reason": "global noise"}
        ],
    }


def test_console_dictionary_validate_reports_import_plan(tmp_path):
    client = _client(tmp_path)

    response = client.post(
        "/v1/console/dictionary/validate", json=_dictionary_payload()
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "valid"
    assert payload["profile_name"] == "infra_incidents"
    assert payload["normalized_profile_name"] == "infra_incidents"
    assert payload["profile_exists"] is False
    assert payload["summary"]["terms_total"] == 2
    assert payload["summary"]["aliases_total"] == 4
    assert payload["summary"]["would_create_terms"] == 2
    assert payload["summary"]["would_create_aliases"] == 4
    assert payload["summary"]["would_create_profile_stop_list_entries"] == 1
    assert payload["summary"]["would_create_global_stop_list_entries"] == 1
    assert payload["errors"] == []


def test_console_dictionary_import_and_export_round_trip(tmp_path):
    client = _client(tmp_path)

    import_response = client.post(
        "/v1/console/dictionary/import", json=_dictionary_payload()
    )

    assert import_response.status_code == 200, import_response.text
    imported = import_response.json()
    assert imported["status"] == "applied"
    assert imported["summary"]["created_terms"] == 2
    assert imported["summary"]["created_aliases"] == 4
    assert imported["summary"]["created_profile_stop_list_entries"] == 1
    assert imported["summary"]["created_global_stop_list_entries"] == 1

    terms_response = client.get("/v1/governance/profiles/infra_incidents/terms")
    assert terms_response.status_code == 200
    terms = terms_response.json()
    assert [term["canonical_value"] for term in terms] == [
        "postgresql",
        "kubernetes",
    ]

    export_response = client.get(
        "/v1/console/dictionary/export",
        params={"profile_name": "infra_incidents"},
    )

    assert export_response.status_code == 200
    exported = export_response.json()
    assert exported["schema_version"] == "skeinrank.dictionary.v1"
    assert exported["profile_name"] == "infra_incidents"
    assert exported["profile_description"] == "Infra incident dictionary"
    exported_terms = {term["canonical_value"]: term for term in exported["terms"]}
    assert exported_terms["kubernetes"]["aliases"] == [
        {"value": "k8s", "confidence": 1.0, "status": "active", "notes": None},
        {
            "value": "kube",
            "confidence": 0.95,
            "status": "active",
            "notes": "short form",
        },
    ]
    assert exported["profile_stop_list"] == [
        {
            "value": "tmp",
            "target": "alias",
            "reason": "too generic",
            "is_active": True,
        }
    ]
    assert exported["global_stop_list"] == [
        {
            "value": "unknown",
            "target": "both",
            "reason": "global noise",
            "is_active": True,
        }
    ]


def test_console_dictionary_import_updates_existing_values(tmp_path):
    client = _client(tmp_path)
    first = client.post("/v1/console/dictionary/import", json=_dictionary_payload())
    assert first.status_code == 200

    update_payload = _dictionary_payload()
    update_payload["terms"][0]["description"] = "Updated description"
    update_payload["terms"][0]["aliases"] = [
        {"value": "k8s", "confidence": 0.9},
        {"value": "kubernetes cluster", "confidence": 0.8},
    ]

    response = client.post("/v1/console/dictionary/import", json=update_payload)

    assert response.status_code == 200
    summary = response.json()["summary"]
    assert summary["updated_terms"] == 2
    assert summary["updated_aliases"] >= 1
    assert summary["created_aliases"] == 1

    term_response = client.get(
        "/v1/governance/profiles/infra_incidents/terms/kubernetes"
    )
    assert term_response.status_code == 200
    payload = term_response.json()
    assert payload["description"] == "Updated description"
    aliases = {alias["alias_value"]: alias for alias in payload["aliases"]}
    assert aliases["k8s"]["confidence"] == 0.9
    assert aliases["kubernetes cluster"]["confidence"] == 0.8


def test_console_dictionary_validate_reports_stop_list_block(tmp_path):
    client = _client(tmp_path)
    payload = _dictionary_payload()
    payload["global_stop_list"] = [{"value": "k8s", "target": "alias"}]

    response = client.post("/v1/console/dictionary/validate", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "invalid"
    assert body["summary"]["blocked_by_stop_list"] == 1
    assert body["errors"][0]["code"] == "alias_stoplisted"

    import_response = client.post("/v1/console/dictionary/import", json=payload)
    assert import_response.status_code == 422
    assert import_response.json()["detail"]["report"]["status"] == "invalid"


def test_console_dictionary_validate_reports_alias_collision(tmp_path):
    client = _client(tmp_path)
    payload = _dictionary_payload()
    payload["terms"] = [
        {"canonical_value": "postgresql", "slot": "DATABASE", "aliases": ["pg"]},
        {"canonical_value": "payment-gateway", "slot": "SERVICE", "aliases": ["pg"]},
    ]

    response = client.post("/v1/console/dictionary/validate", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "invalid"
    assert body["summary"]["conflicts"] == 1
    assert body["errors"][0]["code"] == "alias_payload_collision"


def test_console_dictionary_strict_mode_rejects_existing_values(tmp_path):
    client = _client(tmp_path)
    first = client.post("/v1/console/dictionary/import", json=_dictionary_payload())
    assert first.status_code == 200
    payload = _dictionary_payload()
    payload["mode"] = "strict"

    response = client.post("/v1/console/dictionary/validate", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "invalid"
    assert any(error["code"] == "canonical_exists" for error in body["errors"])
    assert any(error["code"] == "alias_exists" for error in body["errors"])


def test_console_dictionary_export_missing_profile_returns_404(tmp_path):
    client = _client(tmp_path)

    response = client.get(
        "/v1/console/dictionary/export",
        params={"profile_name": "missing"},
    )

    assert response.status_code == 404
    assert "Profile not found" in response.json()["detail"]


def test_contributor_can_validate_and_export_but_not_import(tmp_path):
    client = _client(tmp_path, auth_enabled=True)
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

    validate_response = client.post(
        "/v1/console/dictionary/validate",
        json=_dictionary_payload(),
        headers=_auth(contributor_token),
    )
    assert validate_response.status_code == 200

    import_response = client.post(
        "/v1/console/dictionary/import",
        json=_dictionary_payload(),
        headers=_auth(contributor_token),
    )
    assert import_response.status_code == 403


def test_console_dictionary_schema_version_is_reported(tmp_path):
    client = _client(tmp_path)
    payload = _dictionary_payload()
    payload["schema_version"] = "skeinrank.dictionary.v1"

    response = client.post("/v1/console/dictionary/validate", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "valid"
    assert body["schema_version"] == "skeinrank.dictionary.v1"


def test_console_dictionary_rejects_unsupported_schema_version(tmp_path):
    client = _client(tmp_path)
    payload = _dictionary_payload()
    payload["schema_version"] = "skeinrank.dictionary.v999"

    validate_response = client.post("/v1/console/dictionary/validate", json=payload)

    assert validate_response.status_code == 200
    body = validate_response.json()
    assert body["status"] == "invalid"
    assert body["errors"][0]["code"] == "unsupported_schema_version"
    assert body["errors"][0]["path"] == "schema_version"

    import_response = client.post("/v1/console/dictionary/import", json=payload)
    assert import_response.status_code == 422
    detail = import_response.json()["detail"]
    assert detail["report"]["errors"][0]["code"] == "unsupported_schema_version"
