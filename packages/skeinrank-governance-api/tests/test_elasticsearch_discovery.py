from __future__ import annotations

from fastapi.testclient import TestClient
from skeinrank_governance_api import GovernanceApiConfig, create_app
from skeinrank_governance_api.elasticsearch import extract_mapping_fields


def _client(tmp_path, *, elasticsearch_url: str | None = None) -> TestClient:
    app = create_app(
        GovernanceApiConfig(
            database_url=f"sqlite:///{tmp_path / 'governance.db'}",
            create_tables_on_startup=True,
            service_version="test",
            elasticsearch_url=elasticsearch_url,
        )
    )
    return TestClient(app)


class FakeElasticsearchClient:
    def __init__(self, config):
        self.url = (config.elasticsearch_url or "").rstrip("/")

    @property
    def is_configured(self):
        return bool(self.url)

    def cluster_info(self):
        return {"cluster_name": "skeinrank-dev", "version": {"number": "8.13.4"}}

    def list_indices(self):
        return [
            {"name": "docs", "health": "green", "status": "open", "docs_count": 12},
            {"name": "runbooks", "health": "yellow", "status": "open", "docs_count": 3},
        ]

    def index_fields(self, index_name: str):
        fields = extract_mapping_fields(
            {
                index_name: {
                    "mappings": {
                        "properties": {
                            "title": {
                                "type": "text",
                                "fields": {"keyword": {"type": "keyword"}},
                            },
                            "body": {"type": "match_only_text"},
                            "team": {"type": "keyword"},
                            "metadata": {
                                "properties": {"service": {"type": "keyword"}}
                            },
                        }
                    }
                }
            },
            index_name=index_name,
        )
        return fields

    def search_documents(
        self, *, index_name, text_fields, limit, filter_field=None, filter_value=None
    ):
        del filter_field, filter_value
        assert index_name == "docs"
        assert text_fields == ["title", "body"]
        assert limit == 2
        from skeinrank_governance_api.elasticsearch import ElasticsearchSearchHit

        return [
            ElasticsearchSearchHit(
                id="1",
                index="docs",
                source={
                    "title": "K8s outage",
                    "body": "Kube rollout failed",
                    "team": "infra",
                },
            ),
            ElasticsearchSearchHit(
                id="2",
                index="docs",
                source={"title": "Postgres note", "body": "No match"},
            ),
        ]


def test_elasticsearch_status_reports_unconfigured(tmp_path):
    client = _client(tmp_path)

    response = client.get("/v1/governance/elasticsearch/connection/status")

    assert response.status_code == 200
    assert response.json() == {
        "configured": False,
        "ok": False,
        "url": None,
        "cluster_name": None,
        "cluster_version": None,
        "error": "Elasticsearch URL is not configured.",
    }


def test_elasticsearch_discovery_routes(monkeypatch, tmp_path):
    from skeinrank_governance_api.routes import governance

    monkeypatch.setattr(
        governance, "ElasticsearchDiscoveryClient", FakeElasticsearchClient
    )
    client = _client(tmp_path, elasticsearch_url="http://es:9200")

    status_response = client.get("/v1/governance/elasticsearch/connection/status")
    assert status_response.status_code == 200
    assert status_response.json()["ok"] is True
    assert status_response.json()["cluster_name"] == "skeinrank-dev"

    indices_response = client.get("/v1/governance/elasticsearch/indices")
    assert indices_response.status_code == 200
    assert [item["name"] for item in indices_response.json()] == ["docs", "runbooks"]

    mapping_response = client.get("/v1/governance/elasticsearch/indices/docs/mapping")
    assert mapping_response.status_code == 200
    fields = {item["name"]: item for item in mapping_response.json()["fields"]}
    assert fields["title"]["is_text_candidate"] is True
    assert fields["title.keyword"]["is_discriminator_candidate"] is True
    assert fields["metadata.service"]["is_discriminator_candidate"] is True


def test_extract_mapping_fields_handles_nested_properties():
    fields = extract_mapping_fields(
        {
            "docs": {
                "mappings": {
                    "properties": {
                        "content": {"type": "text"},
                        "source": {"properties": {"team": {"type": "keyword"}}},
                    }
                }
            }
        },
        index_name="docs",
    )

    assert [field.name for field in fields] == ["content", "source.team"]


def test_elasticsearch_binding_dry_run_previews_matches(monkeypatch, tmp_path):
    from skeinrank_governance_api.routes import governance

    monkeypatch.setattr(
        governance, "ElasticsearchDiscoveryClient", FakeElasticsearchClient
    )
    client = _client(tmp_path, elasticsearch_url="http://es:9200")

    assert (
        client.post("/v1/governance/profiles", json={"name": "default_it"}).status_code
        == 201
    )
    assert (
        client.post(
            "/v1/governance/profiles/default_it/terms",
            json={"canonical_value": "kubernetes", "slot": "TOOL"},
        ).status_code
        == 201
    )
    assert (
        client.post(
            "/v1/governance/profiles/default_it/terms/kubernetes/aliases",
            json={"alias_value": "k8s", "confidence": 0.97},
        ).status_code
        == 201
    )
    binding_response = client.post(
        "/v1/governance/elasticsearch/bindings",
        json={
            "name": "infra docs",
            "profile_name": "default_it",
            "index_name": "docs",
            "text_fields": ["title", "body"],
            "target_field": "skeinrank",
            "filter_field": "team",
            "filter_value": "infra",
        },
    )
    assert binding_response.status_code == 201

    response = client.post(
        f"/v1/governance/elasticsearch/bindings/{binding_response.json()['id']}/dry-run",
        json={"limit": 2},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["binding"]["name"] == "infra docs"
    assert payload["documents"][0]["document_id"] == "1"
    assert payload["documents"][0]["matched_aliases"][0]["alias_value"] == "k8s"
    assert payload["documents"][0]["would_write"]["skeinrank"]["canonical_values"] == [
        "kubernetes"
    ]
    assert payload["documents"][1]["matched_aliases"] == []


def test_elasticsearch_binding_dry_run_requires_connection(tmp_path):
    client = _client(tmp_path)
    client.post("/v1/governance/profiles", json={"name": "default_it"})
    binding_response = client.post(
        "/v1/governance/elasticsearch/bindings",
        json={
            "name": "docs",
            "profile_name": "default_it",
            "index_name": "docs",
            "text_fields": ["body"],
            "target_field": "skeinrank",
        },
    )

    response = client.post(
        f"/v1/governance/elasticsearch/bindings/{binding_response.json()['id']}/dry-run",
        json={"limit": 1},
    )

    assert response.status_code == 503
    assert "not configured" in response.json()["detail"]
