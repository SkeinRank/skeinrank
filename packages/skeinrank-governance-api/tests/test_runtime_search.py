from __future__ import annotations

from fastapi.testclient import TestClient
from skeinrank_governance_api import GovernanceApiConfig, create_app


class _FakeElasticsearchClient:
    def __init__(self, _config):
        self.is_configured = True
        self.last_request = None

    def execute_search(self, *, index_name: str, body: dict):
        self.last_request = {"index_name": index_name, "body": body}
        assert index_name == "kb"
        assert body["query"]["bool"]["minimum_should_match"] == 1
        assert body["query"]["bool"]["should"][1]["terms"] == {
            "skeinrank.canonical_values": ["kubernetes", "postgresql"],
            "boost": 3.0,
        }
        return {
            "hits": {
                "total": {"value": 2, "relation": "eq"},
                "hits": [
                    {
                        "_index": "kb",
                        "_id": "doc_001",
                        "_score": 3.5,
                        "_source": {
                            "title": "K8s rollout incident",
                            "skeinrank": {
                                "canonical_values": ["kubernetes", "postgresql"],
                                "matched_aliases": ["k8s", "pg"],
                            },
                        },
                    },
                    {
                        "_index": "kb",
                        "_id": "doc_002",
                        "_score": 2.1,
                        "_source": {
                            "title": "Database latency",
                            "skeinrank": {
                                "canonical_values": ["postgresql"],
                                "matched_aliases": ["postgres"],
                            },
                        },
                    },
                ],
            }
        }


class _UnconfiguredElasticsearchClient:
    def __init__(self, _config):
        self.is_configured = False


class _FailingElasticsearchClient:
    def __init__(self, _config):
        self.is_configured = True

    def execute_search(
        self, *, index_name: str, body: dict
    ):  # pragma: no cover - defensive
        from skeinrank_governance_api.elasticsearch import ElasticsearchDiscoveryError

        raise ElasticsearchDiscoveryError("search failed")


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
            elasticsearch_url="http://es.local:9200",
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


def _seed_dictionary(client: TestClient, headers: dict[str, str] | None = None) -> None:
    headers = headers or {}
    assert (
        client.post(
            "/v1/governance/profiles",
            json={"name": "infra_incidents"},
            headers=headers,
        ).status_code
        == 201
    )
    assert (
        client.post(
            "/v1/governance/profiles/infra_incidents/terms",
            json={"canonical_value": "kubernetes", "slot": "TOOL"},
            headers=headers,
        ).status_code
        == 201
    )
    assert (
        client.post(
            "/v1/governance/profiles/infra_incidents/terms/kubernetes/aliases",
            json={"alias_value": "k8s"},
            headers=headers,
        ).status_code
        == 201
    )
    assert (
        client.post(
            "/v1/governance/profiles/infra_incidents/terms",
            json={"canonical_value": "postgresql", "slot": "DATABASE"},
            headers=headers,
        ).status_code
        == 201
    )
    assert (
        client.post(
            "/v1/governance/profiles/infra_incidents/terms/postgresql/aliases",
            json={"alias_value": "pg"},
            headers=headers,
        ).status_code
        == 201
    )


def test_query_plan_builds_canonical_terms_and_es_dsl(tmp_path):
    client = _client(tmp_path)
    _seed_dictionary(client)

    response = client.post(
        "/v1/query/plan",
        json={
            "profile_name": "infra_incidents",
            "query": "k8s pg timeout",
            "text_fields": ["title^2", "text"],
            "target_field": "skeinrank",
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["canonical_query"] == "kubernetes postgresql timeout"
    assert payload["changed"] is True
    assert payload["canonical_values"] == ["kubernetes", "postgresql"]
    assert payload["slots"] == {
        "DATABASE": ["postgresql"],
        "TOOL": ["kubernetes"],
    }
    assert payload["matched_aliases"] == ["k8s", "pg"]
    assert payload["replacements"][0]["start"] == 0
    assert payload["elasticsearch"]["query"]["bool"]["should"][0]["multi_match"] == {
        "query": "k8s pg timeout",
        "fields": ["title^2", "text"],
        "type": "best_fields",
    }
    assert payload["elasticsearch"]["query"]["bool"]["should"][1]["terms"] == {
        "skeinrank.canonical_values": ["kubernetes", "postgresql"],
        "boost": 3.0,
    }


def test_query_plan_without_matches_falls_back_to_text_query(tmp_path):
    client = _client(tmp_path)
    _seed_dictionary(client)

    response = client.post(
        "/v1/query/plan",
        json={"profile_name": "infra_incidents", "query": "redis failover"},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["canonical_values"] == []
    assert payload["elasticsearch"]["query"] == {
        "multi_match": {
            "query": "redis failover",
            "fields": ["title", "text"],
            "type": "best_fields",
        }
    }
    assert "No active aliases matched" in payload["warnings"][0]


def test_search_executes_runtime_query_and_returns_hits(tmp_path, monkeypatch):
    client = _client(tmp_path)
    _seed_dictionary(client)
    monkeypatch.setattr(
        "skeinrank_governance_api.routes.search.ElasticsearchDiscoveryClient",
        _FakeElasticsearchClient,
    )

    response = client.post(
        "/v1/search",
        json={
            "profile_name": "infra_incidents",
            "index_name": "kb",
            "query": "k8s pg timeout",
            "size": 5,
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["index_name"] == "kb"
    assert payload["canonical_values"] == ["kubernetes", "postgresql"]
    assert payload["total"] == {"value": 2, "relation": "eq"}
    assert [hit["id"] for hit in payload["hits"]] == ["doc_001", "doc_002"]
    assert payload["hits"][0]["skeinrank"]["canonical_values"] == [
        "kubernetes",
        "postgresql",
    ]
    assert payload["elasticsearch"]["size"] == 5


def test_search_can_disable_source(tmp_path, monkeypatch):
    client = _client(tmp_path)
    _seed_dictionary(client)
    seen_body: dict = {}

    class _SourceAwareClient(_FakeElasticsearchClient):
        def execute_search(self, *, index_name: str, body: dict):
            seen_body.update(body)
            return {"hits": {"total": {"value": 0, "relation": "eq"}, "hits": []}}

    monkeypatch.setattr(
        "skeinrank_governance_api.routes.search.ElasticsearchDiscoveryClient",
        _SourceAwareClient,
    )

    response = client.post(
        "/v1/search",
        json={
            "profile_name": "infra_incidents",
            "index_name": "kb",
            "query": "k8s pg timeout",
            "include_source": False,
        },
    )

    assert response.status_code == 200, response.text
    assert seen_body["_source"] is False


def test_search_requires_configured_elasticsearch(tmp_path, monkeypatch):
    client = _client(tmp_path)
    _seed_dictionary(client)
    monkeypatch.setattr(
        "skeinrank_governance_api.routes.search.ElasticsearchDiscoveryClient",
        _UnconfiguredElasticsearchClient,
    )

    response = client.post(
        "/v1/search",
        json={
            "profile_name": "infra_incidents",
            "index_name": "kb",
            "query": "k8s",
        },
    )

    assert response.status_code == 503
    assert "Elasticsearch URL is not configured" in response.json()["detail"]


def test_runtime_search_endpoints_are_protected_when_auth_enabled(tmp_path):
    client = _client(tmp_path, auth_enabled=True)
    token = _login(client)
    headers = _auth(token)
    _seed_dictionary(client, headers=headers)

    unauthorized_plan = client.post(
        "/v1/query/plan",
        json={"profile_name": "infra_incidents", "query": "k8s"},
    )
    assert unauthorized_plan.status_code == 401

    authorized_plan = client.post(
        "/v1/query/plan",
        json={"profile_name": "infra_incidents", "query": "k8s"},
        headers=headers,
    )
    assert authorized_plan.status_code == 200
    assert authorized_plan.json()["canonical_values"] == ["kubernetes"]
