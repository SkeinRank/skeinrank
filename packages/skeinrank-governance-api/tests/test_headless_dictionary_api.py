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
        "schema_version": "skeinrank.dictionary.v1",
        "profile_name": "platform_ops",
        "profile_description": "Platform operations terminology",
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


def test_headless_dictionary_validate_reports_spec_v1(tmp_path):
    client = _client(tmp_path)

    response = client.post(
        "/v1/headless/dictionaries/validate",
        json=_dictionary_payload(),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "valid"
    assert body["schema_version"] == "skeinrank.dictionary.v1"
    assert body["profile_name"] == "platform_ops"
    assert body["summary"]["terms_total"] == 2
    assert body["summary"]["aliases_total"] == 4


def test_headless_dictionary_apply_and_export_round_trip(tmp_path):
    client = _client(tmp_path)

    apply_response = client.post(
        "/v1/headless/dictionaries/apply",
        json=_dictionary_payload(),
    )

    assert apply_response.status_code == 200, apply_response.text
    applied = apply_response.json()
    assert applied["status"] == "applied"
    assert applied["schema_version"] == "skeinrank.dictionary.v1"
    assert applied["summary"]["created_terms"] == 2
    assert applied["summary"]["created_aliases"] == 4

    export_response = client.get(
        "/v1/headless/dictionaries/export",
        params={"profile_name": "platform_ops"},
    )

    assert export_response.status_code == 200, export_response.text
    exported = export_response.json()
    assert exported["schema_version"] == "skeinrank.dictionary.v1"
    assert exported["profile_name"] == "platform_ops"
    terms = {term["canonical_value"]: term for term in exported["terms"]}
    assert terms["kubernetes"]["aliases"] == [
        {"value": "k8s", "confidence": 1.0, "status": "active", "notes": None},
        {
            "value": "kube",
            "confidence": 0.95,
            "status": "active",
            "notes": "short form",
        },
    ]


def test_headless_dictionary_rejects_invalid_payload_on_apply(tmp_path):
    client = _client(tmp_path)
    payload = _dictionary_payload()
    payload["terms"] = [
        {"canonical_value": "postgresql", "slot": "DATABASE", "aliases": ["pg"]},
        {"canonical_value": "payment-gateway", "slot": "SERVICE", "aliases": ["pg"]},
    ]

    response = client.post("/v1/headless/dictionaries/apply", json=payload)

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["message"] == "Dictionary apply validation failed."
    assert detail["report"]["status"] == "invalid"
    assert detail["report"]["errors"][0]["code"] == "alias_payload_collision"


def test_contributor_can_validate_and_export_but_not_apply_headless_dictionary(
    tmp_path,
):
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
        "/v1/headless/dictionaries/validate",
        json=_dictionary_payload(),
        headers=_auth(contributor_token),
    )
    assert validate_response.status_code == 200

    apply_response = client.post(
        "/v1/headless/dictionaries/apply",
        json=_dictionary_payload(),
        headers=_auth(contributor_token),
    )
    assert apply_response.status_code == 403

    apply_as_admin = client.post(
        "/v1/headless/dictionaries/apply",
        json=_dictionary_payload(),
        headers=_auth(admin_token),
    )
    assert apply_as_admin.status_code == 200

    export_response = client.get(
        "/v1/headless/dictionaries/export",
        params={"profile_name": "platform_ops"},
        headers=_auth(contributor_token),
    )
    assert export_response.status_code == 200
