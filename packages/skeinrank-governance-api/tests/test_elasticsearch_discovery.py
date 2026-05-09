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
                            "created_at": {"type": "date"},
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

    last_search_args = None
    last_reindex_args = None

    def search_documents(
        self,
        *,
        index_name,
        text_fields,
        limit,
        filter_field=None,
        filter_value=None,
        timestamp_field=None,
        time_window_days=None,
    ):
        type(self).last_search_args = {
            "filter_field": filter_field,
            "filter_value": filter_value,
            "timestamp_field": timestamp_field,
            "time_window_days": time_window_days,
        }
        assert (
            index_name == "docs"
            or index_name.startswith("docs__skeinrank_job_")
            or index_name == "docs_v2"
        )
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
                    "created_at": "2026-05-08T00:00:00Z",
                },
            ),
            ElasticsearchSearchHit(
                id="2",
                index="docs",
                source={"title": "Postgres note", "body": "No match"},
            ),
        ]

    def create_reindex_target_index(self, *, source_index, target_index):
        assert source_index == "docs"
        assert (
            target_index.startswith("docs__skeinrank_job_") or target_index == "docs_v2"
        )
        self.created_target_index = target_index
        return {"acknowledged": True, "index": target_index}

    def reindex_documents(
        self,
        *,
        source_index,
        target_index,
        filter_field=None,
        filter_value=None,
        timestamp_field=None,
        time_window_days=None,
    ):
        assert source_index == "docs"
        assert filter_field == "team"
        assert filter_value == "infra"
        type(self).last_reindex_args = {
            "filter_field": filter_field,
            "filter_value": filter_value,
            "timestamp_field": timestamp_field,
            "time_window_days": time_window_days,
        }
        self.reindexed_target_index = target_index
        return {"created": 2, "updated": 0, "failures": []}

    def bulk_update_documents(self, *, index_name, updates):
        self.bulk_index_name = index_name
        self.bulk_updates = updates
        return {"errors": False, "items": []}

    def swap_alias(self, *, alias_name, target_index):
        self.swapped_alias = alias_name
        self.swapped_target_index = target_index
        return {"acknowledged": True}


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
    assert fields["created_at"]["type"] == "date"


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
            "timestamp_field": "created_at",
            "time_window_days": 1825,
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
    assert payload["binding"]["timestamp_field"] == "created_at"
    assert payload["binding"]["time_window_days"] == 1825
    assert FakeElasticsearchClient.last_search_args["timestamp_field"] == "created_at"
    assert FakeElasticsearchClient.last_search_args["time_window_days"] == 1825
    assert payload["documents"][0]["document_id"] == "1"
    assert payload["documents"][0]["matched_aliases"][0]["alias_value"] == "k8s"
    assert payload["documents"][0]["would_write"]["skeinrank"]["canonical_values"] == [
        "kubernetes"
    ]
    assert payload["documents"][1]["matched_aliases"] == []


def test_elasticsearch_dry_run_respects_global_stop_list(monkeypatch, tmp_path):
    from skeinrank_governance_api.routes import governance

    monkeypatch.setattr(
        governance, "ElasticsearchDiscoveryClient", FakeElasticsearchClient
    )
    client = _client(tmp_path, elasticsearch_url="http://es:9200")

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
        "/v1/governance/global-stop-list",
        json={"value": "k8s", "target": "alias"},
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
    assert payload["documents"][0]["matched_aliases"] == []
    assert payload["documents"][0]["would_write"]["skeinrank"]["canonical_values"] == []


def test_elasticsearch_binding_time_window_requires_timestamp_field(tmp_path):
    client = _client(tmp_path)
    client.post("/v1/governance/profiles", json={"name": "default_it"})

    response = client.post(
        "/v1/governance/elasticsearch/bindings",
        json={
            "name": "docs",
            "profile_name": "default_it",
            "index_name": "docs",
            "text_fields": ["body"],
            "target_field": "skeinrank",
            "time_window_days": 30,
        },
    )

    assert response.status_code == 422
    assert "timestamp_field" in response.json()["detail"]


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


def test_elasticsearch_reindex_alias_swap_job(monkeypatch, tmp_path):
    from skeinrank_governance_api.routes import governance

    monkeypatch.setattr(
        governance, "ElasticsearchDiscoveryClient", FakeElasticsearchClient
    )
    client = _client(tmp_path, elasticsearch_url="http://es:9200")

    client.post("/v1/governance/profiles", json={"name": "default_it"})
    client.post(
        "/v1/governance/profiles/default_it/terms",
        json={"canonical_value": "kubernetes", "slot": "TOOL"},
    )
    client.post(
        "/v1/governance/profiles/default_it/terms/kubernetes/aliases",
        json={"alias_value": "k8s", "confidence": 0.97},
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
            "mode": "write",
            "write_strategy": "reindex_alias_swap",
            "timestamp_field": "created_at",
            "time_window_days": 30,
        },
    )
    assert binding_response.status_code == 201

    response = client.post(
        f"/v1/governance/elasticsearch/bindings/{binding_response.json()['id']}/jobs",
        json={"max_documents": 2},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["status"] == "succeeded"
    assert payload["write_strategy"] == "reindex_alias_swap"
    assert payload["source_index"] == "docs"
    assert payload["target_index"].startswith("docs__skeinrank_job_")
    assert payload["alias_name"] == "docs"
    assert payload["documents_seen"] == 2
    assert payload["documents_enriched"] == 1
    assert payload["result_json"]["updated_document_ids"] == ["1"]
    assert payload["result_json"]["timestamp_field"] == "created_at"
    assert payload["result_json"]["time_window_days"] == 30
    assert FakeElasticsearchClient.last_reindex_args["timestamp_field"] == "created_at"
    assert FakeElasticsearchClient.last_reindex_args["time_window_days"] == 30

    list_response = client.get("/v1/governance/elasticsearch/jobs")
    assert list_response.status_code == 200
    assert [item["id"] for item in list_response.json()] == [payload["id"]]

    detail_response = client.get(f"/v1/governance/elasticsearch/jobs/{payload['id']}")
    assert detail_response.status_code == 200
    assert detail_response.json()["status"] == "succeeded"


def test_elasticsearch_enrichment_job_requires_write_mode(monkeypatch, tmp_path):
    from skeinrank_governance_api.routes import governance

    monkeypatch.setattr(
        governance, "ElasticsearchDiscoveryClient", FakeElasticsearchClient
    )
    client = _client(tmp_path, elasticsearch_url="http://es:9200")
    client.post("/v1/governance/profiles", json={"name": "default_it"})
    binding_response = client.post(
        "/v1/governance/elasticsearch/bindings",
        json={
            "name": "docs",
            "profile_name": "default_it",
            "index_name": "docs",
            "text_fields": ["body"],
            "target_field": "skeinrank",
            "mode": "dry_run",
        },
    )

    response = client.post(
        f"/v1/governance/elasticsearch/bindings/{binding_response.json()['id']}/jobs"
    )

    assert response.status_code == 409
    assert "write mode" in response.json()["detail"]
