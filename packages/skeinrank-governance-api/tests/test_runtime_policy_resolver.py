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


def _seed_policy_fixture(client: TestClient) -> tuple[int, int, int]:
    assert (
        client.post("/v1/governance/profiles", json={"name": "default_it"}).status_code
        == 201
    )
    page = client.post(
        "/v1/governance/profiles/default_it/terms",
        json={
            "canonical_value": "page",
            "slot": "document_component",
            "tags": ["docs"],
        },
    )
    assert page.status_code == 201, page.text
    postgres = client.post(
        "/v1/governance/profiles/default_it/terms",
        json={
            "canonical_value": "postgresql",
            "slot": "database",
            "tags": ["backend", "storage"],
        },
    )
    assert postgres.status_code == 201, postgres.text
    alias = client.post(
        "/v1/governance/profiles/default_it/terms/page/aliases",
        json={"alias_value": "pg"},
    )
    assert alias.status_code == 201, alias.text
    binding = client.post(
        "/v1/governance/elasticsearch/bindings",
        json={
            "name": "Docs runtime",
            "profile_name": "default_it",
            "index_name": "docs",
            "text_fields": ["title", "body"],
            "target_field": "skeinrank",
        },
    )
    assert binding.status_code == 201, binding.text
    return int(binding.json()["id"]), int(page.json()["id"]), int(postgres.json()["id"])


def test_binding_policy_context_rule_resolves_ambiguous_candidate(tmp_path):
    client = _client(tmp_path)
    binding_id, page_id, postgres_id = _seed_policy_fixture(client)

    ambiguous = client.post(
        "/v1/governance/profiles/default_it/ambiguous-aliases",
        json={
            "surface_value": "PG",
            "candidates": [
                {
                    "term_id": page_id,
                    "canonical_value": "page",
                    "slot": "document_component",
                    "source": "active_alias",
                    "status": "preferred",
                },
                {
                    "term_id": postgres_id,
                    "canonical_value": "postgresql",
                    "slot": "database",
                    "source": "manual",
                    "status": "candidate",
                },
            ],
        },
    )
    assert ambiguous.status_code == 201, ambiguous.text

    policy = client.put(
        f"/v1/governance/elasticsearch/bindings/{binding_id}/policy",
        json={
            "allowed_tags": ["backend"],
            "deny_slots": ["document_component"],
            "context_rules": [
                {
                    "surface": "pg",
                    "prefer": "postgresql",
                    "slot": "database",
                    "reason": "Infra runtime resolves pg as PostgreSQL.",
                }
            ],
        },
    )
    assert policy.status_code == 201, policy.text

    response = client.post(
        "/v1/text/canonicalize",
        json={
            "binding_id": binding_id,
            "text": "pg timeout after migration",
            "mode": "replace",
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["canonical_text"] == "postgresql timeout after migration"
    assert payload["canonical_values"] == ["postgresql"]
    assert payload["slots"] == {"DATABASE": ["postgresql"]}
    assert payload["tags"] == {"postgresql": ["backend", "storage"]}
    assert payload["policy_decisions"][0]["reason"] == "binding_policy.context_rule"
    assert payload["policy_decisions"][0]["selected_canonical"] == "postgresql"
    candidate_canonicals = {
        item["normalized_canonical"]
        for item in payload["policy_decisions"][0]["candidates"]
    }
    assert candidate_canonicals == {"page", "postgresql"}


def test_query_plan_includes_binding_policy_decisions(tmp_path):
    client = _client(tmp_path)
    binding_id, page_id, postgres_id = _seed_policy_fixture(client)
    assert (
        client.post(
            "/v1/governance/profiles/default_it/ambiguous-aliases",
            json={
                "surface_value": "pg",
                "candidates": [
                    {
                        "term_id": page_id,
                        "canonical_value": "page",
                        "slot": "document_component",
                        "source": "active_alias",
                    },
                    {
                        "term_id": postgres_id,
                        "canonical_value": "postgresql",
                        "slot": "database",
                        "source": "manual",
                    },
                ],
            },
        ).status_code
        == 201
    )
    assert (
        client.put(
            f"/v1/governance/elasticsearch/bindings/{binding_id}/policy",
            json={
                "preferred_slots": ["database"],
                "deny_slots": ["document_component"],
            },
        ).status_code
        == 201
    )

    response = client.post(
        "/v1/query/plan",
        json={"binding_id": binding_id, "query": "pg errors"},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["canonical_query"] == "postgresql errors"
    assert payload["canonical_values"] == ["postgresql"]
    assert payload["policy_decisions"][0]["reason"] == "binding_policy.preferred_slots"
    assert payload["policy_decisions"][0]["selected_slot"] == "DATABASE"


def test_binding_policy_denies_noisy_active_slot(tmp_path):
    client = _client(tmp_path)
    binding_id, _page_id, _postgres_id = _seed_policy_fixture(client)
    assert (
        client.put(
            f"/v1/governance/elasticsearch/bindings/{binding_id}/policy",
            json={"deny_slots": ["document_component"]},
        ).status_code
        == 201
    )

    response = client.post(
        "/v1/text/canonicalize",
        json={"binding_id": binding_id, "text": "pg", "mode": "replace"},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["canonical_text"] == "pg"
    assert payload["canonical_values"] == []
    assert any(
        "excluded all runtime candidates" in item for item in payload["warnings"]
    )
