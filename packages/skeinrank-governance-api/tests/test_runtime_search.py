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
            json={
                "canonical_value": "kubernetes",
                "slot": "TOOL",
                "tags": ["infra", "orchestration"],
            },
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
            json={
                "canonical_value": "postgresql",
                "slot": "DATABASE",
                "tags": ["backend", "storage"],
            },
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
    assert payload["tags"] == {
        "kubernetes": ["infra", "orchestration"],
        "postgresql": ["backend", "storage"],
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


def test_query_plan_can_use_binding_runtime_snapshot_after_alias_is_disabled(tmp_path):
    from skeinrank_governance.models import (
        ElasticsearchBinding,
        TermAlias,
        TerminologyProfile,
    )
    from skeinrank_governance_api.runtime_snapshots import (
        build_runtime_snapshot_payload,
    )

    client = _client(tmp_path)
    _seed_dictionary(client)
    binding_response = client.post(
        "/v1/governance/elasticsearch/bindings",
        json={
            "name": "infra docs",
            "profile_name": "infra_incidents",
            "index_name": "kb",
            "text_fields": ["title", "text"],
            "target_field": "skeinrank",
            "mode": "write",
            "write_strategy": "in_place",
        },
    )
    assert binding_response.status_code == 201
    binding_id = binding_response.json()["id"]

    session_factory = client.app.state.governance_session_factory
    with session_factory() as session:
        profile = (
            session.query(TerminologyProfile)
            .filter_by(normalized_name="infra_incidents")
            .one()
        )
        binding = session.get(ElasticsearchBinding, binding_id)
        snapshot = build_runtime_snapshot_payload(session, profile)
        binding.last_successful_snapshot_version = snapshot["version"]
        binding.runtime_snapshot_json = snapshot
        alias = session.query(TermAlias).filter_by(normalized_alias="k8s").one()
        alias.status = "disabled"
        session.commit()

    latest_response = client.post(
        "/v1/query/plan",
        json={"profile_name": "infra_incidents", "query": "k8s rollout"},
    )
    assert latest_response.status_code == 200
    assert latest_response.json()["canonical_values"] == []
    assert latest_response.json()["snapshot_source"] == "latest_profile"

    binding_response = client.post(
        "/v1/query/plan",
        json={
            "profile_name": "infra_incidents",
            "binding_id": binding_id,
            "query": "k8s rollout",
        },
    )
    assert binding_response.status_code == 200
    payload = binding_response.json()
    assert payload["binding_id"] == binding_id
    assert payload["snapshot_source"] == "binding_runtime_snapshot"
    assert payload["snapshot_version"] == snapshot["version"]
    assert payload["canonical_values"] == ["kubernetes"]
    assert payload["canonical_query"] == "kubernetes rollout"


def test_query_plan_accepts_binding_id_only_and_uses_binding_config(tmp_path):
    from skeinrank_governance.models import ElasticsearchBinding, TerminologyProfile
    from skeinrank_governance_api.runtime_snapshots import (
        build_runtime_snapshot_payload,
    )

    client = _client(tmp_path)
    _seed_dictionary(client)
    binding_response = client.post(
        "/v1/governance/elasticsearch/bindings",
        json={
            "name": "infra custom docs",
            "profile_name": "infra_incidents",
            "index_name": "kb_custom",
            "text_fields": ["body", "summary^2"],
            "target_field": "sr",
            "mode": "write",
            "write_strategy": "in_place",
        },
    )
    assert binding_response.status_code == 201
    binding_id = binding_response.json()["id"]

    session_factory = client.app.state.governance_session_factory
    with session_factory() as session:
        profile = (
            session.query(TerminologyProfile)
            .filter_by(normalized_name="infra_incidents")
            .one()
        )
        binding = session.get(ElasticsearchBinding, binding_id)
        snapshot = build_runtime_snapshot_payload(session, profile)
        binding.last_successful_snapshot_version = snapshot["version"]
        binding.runtime_snapshot_json = snapshot
        session.commit()

    response = client.post(
        "/v1/query/plan",
        json={"binding_id": binding_id, "query": "k8s pg"},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["profile_name"] == "infra_incidents"
    assert payload["binding_id"] == binding_id
    assert payload["snapshot_source"] == "binding_runtime_snapshot"
    assert payload["text_fields"] == ["body", "summary^2"]
    assert payload["target_field"] == "sr"
    assert payload["elasticsearch"]["query"]["bool"]["should"][1]["terms"] == {
        "sr.canonical_values": ["kubernetes", "postgresql"],
        "boost": 3.0,
    }


def test_search_accepts_binding_id_only_and_uses_binding_index(tmp_path, monkeypatch):
    from skeinrank_governance.models import ElasticsearchBinding, TerminologyProfile
    from skeinrank_governance_api.runtime_snapshots import (
        build_runtime_snapshot_payload,
    )

    client = _client(tmp_path)
    _seed_dictionary(client)
    binding_response = client.post(
        "/v1/governance/elasticsearch/bindings",
        json={
            "name": "infra docs",
            "profile_name": "infra_incidents",
            "index_name": "kb",
            "text_fields": ["title", "text"],
            "target_field": "skeinrank",
            "mode": "write",
            "write_strategy": "in_place",
        },
    )
    assert binding_response.status_code == 201
    binding_id = binding_response.json()["id"]

    session_factory = client.app.state.governance_session_factory
    with session_factory() as session:
        profile = (
            session.query(TerminologyProfile)
            .filter_by(normalized_name="infra_incidents")
            .one()
        )
        binding = session.get(ElasticsearchBinding, binding_id)
        snapshot = build_runtime_snapshot_payload(session, profile)
        binding.last_successful_snapshot_version = snapshot["version"]
        binding.runtime_snapshot_json = snapshot
        session.commit()

    monkeypatch.setattr(
        "skeinrank_governance_api.routes.search.ElasticsearchDiscoveryClient",
        _FakeElasticsearchClient,
    )

    response = client.post(
        "/v1/search",
        json={"binding_id": binding_id, "query": "k8s pg timeout"},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["profile_name"] == "infra_incidents"
    assert payload["index_name"] == "kb"
    assert payload["binding_id"] == binding_id
    assert payload["snapshot_source"] == "binding_runtime_snapshot"
    assert payload["canonical_values"] == ["kubernetes", "postgresql"]
    assert not any(
        "binding_id was not provided" in item for item in payload["warnings"]
    )


def test_search_without_binding_id_returns_preview_warning(tmp_path, monkeypatch):
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
        },
    )

    assert response.status_code == 200, response.text
    assert any(
        "binding_id was not provided" in item for item in response.json()["warnings"]
    )


class _MultiBindingFakeElasticsearchClient:
    def __init__(self, _config):
        self.is_configured = True

    def execute_search(self, *, index_name: str, body: dict):
        assert body["query"]["bool"]["should"][1]["terms"] == {
            "skeinrank.canonical_values": ["kubernetes", "postgresql"],
            "boost": 3.0,
        }
        if index_name == "kb_a":
            return {
                "hits": {
                    "total": {"value": 1, "relation": "eq"},
                    "hits": [
                        {
                            "_index": "kb_a",
                            "_id": "doc_a",
                            "_score": 1.0,
                            "_source": {
                                "title": "A incident",
                                "skeinrank": {
                                    "canonical_values": ["kubernetes"],
                                },
                            },
                        }
                    ],
                }
            }
        if index_name == "kb_b":
            return {
                "hits": {
                    "total": {"value": 1, "relation": "eq"},
                    "hits": [
                        {
                            "_index": "kb_b",
                            "_id": "doc_b",
                            "_score": 4.0,
                            "_source": {
                                "title": "B runbook",
                                "skeinrank": {
                                    "canonical_values": ["postgresql"],
                                },
                            },
                        }
                    ],
                }
            }
        raise AssertionError(f"unexpected index: {index_name}")


def _create_binding(client: TestClient, *, name: str, index_name: str) -> int:
    response = client.post(
        "/v1/governance/elasticsearch/bindings",
        json={
            "name": name,
            "profile_name": "infra_incidents",
            "index_name": index_name,
            "text_fields": ["title", "text"],
            "target_field": "skeinrank",
            "mode": "write",
            "write_strategy": "in_place",
        },
    )
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


def _pin_binding_snapshot(client: TestClient, binding_id: int) -> str:
    from skeinrank_governance.models import ElasticsearchBinding, TerminologyProfile
    from skeinrank_governance_api.runtime_snapshots import (
        build_runtime_snapshot_payload,
    )

    session_factory = client.app.state.governance_session_factory
    with session_factory() as session:
        profile = (
            session.query(TerminologyProfile)
            .filter_by(normalized_name="infra_incidents")
            .one()
        )
        binding = session.get(ElasticsearchBinding, binding_id)
        snapshot = build_runtime_snapshot_payload(session, profile)
        binding.last_successful_snapshot_version = snapshot["version"]
        binding.runtime_snapshot_json = snapshot
        session.commit()
    return str(snapshot["version"])


def test_multi_search_executes_each_binding_and_merges_hits(tmp_path, monkeypatch):
    client = _client(tmp_path)
    _seed_dictionary(client)
    binding_a = _create_binding(client, name="binding a", index_name="kb_a")
    binding_b = _create_binding(client, name="binding b", index_name="kb_b")
    snapshot_a = _pin_binding_snapshot(client, binding_a)
    snapshot_b = _pin_binding_snapshot(client, binding_b)
    monkeypatch.setattr(
        "skeinrank_governance_api.routes.search.ElasticsearchDiscoveryClient",
        _MultiBindingFakeElasticsearchClient,
    )

    response = client.post(
        "/v1/search/multi",
        json={"binding_ids": [binding_a, binding_b], "query": "k8s pg", "size": 10},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["binding_ids"] == [binding_a, binding_b]
    assert payload["total_bindings"] == 2
    assert payload["succeeded_bindings"] == 2
    assert payload["failed_bindings"] == 0
    assert [item["status"] for item in payload["results"]] == [
        "succeeded",
        "succeeded",
    ]
    assert payload["results"][0]["snapshot_source"] == "binding_runtime_snapshot"
    assert payload["results"][0]["snapshot_version"] == snapshot_a
    assert payload["results"][1]["snapshot_version"] == snapshot_b
    assert [hit["id"] for hit in payload["hits"]] == ["doc_b", "doc_a"]
    assert payload["hits"][0]["binding_id"] == binding_b
    assert payload["hits"][1]["binding_id"] == binding_a


def test_multi_search_deduplicates_binding_ids_and_reports_partial_failures(
    tmp_path, monkeypatch
):
    client = _client(tmp_path)
    _seed_dictionary(client)
    binding_id = _create_binding(client, name="binding a", index_name="kb_a")
    _pin_binding_snapshot(client, binding_id)
    monkeypatch.setattr(
        "skeinrank_governance_api.routes.search.ElasticsearchDiscoveryClient",
        _MultiBindingFakeElasticsearchClient,
    )

    response = client.post(
        "/v1/search/multi",
        json={"binding_ids": [binding_id, binding_id, 999], "query": "k8s pg"},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["binding_ids"] == [binding_id, 999]
    assert payload["succeeded_bindings"] == 1
    assert payload["failed_bindings"] == 1
    assert payload["results"][0]["status"] == "succeeded"
    assert payload["results"][1]["status"] == "failed"
    assert "binding not found" in payload["results"][1]["error"]
    assert any("Duplicate binding_id" in item for item in payload["warnings"])
