from __future__ import annotations

from fastapi.testclient import TestClient
from skeinrank_governance_api import GovernanceApiConfig, create_app
from skeinrank_governance_api.elasticsearch import extract_mapping_fields


def _client(
    tmp_path,
    *,
    elasticsearch_url: str | None = None,
    enrichment_jobs_backend: str = "sync",
) -> TestClient:
    app = create_app(
        GovernanceApiConfig(
            database_url=f"sqlite:///{tmp_path / 'governance.db'}",
            create_tables_on_startup=True,
            service_version="test",
            elasticsearch_url=elasticsearch_url,
            enrichment_jobs_backend=enrichment_jobs_backend,
            celery_task_queue="test.enrichment",
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
        offset=0,
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
            "offset": offset,
            "limit": limit,
        }
        assert (
            index_name == "docs"
            or index_name.startswith("docs__skeinrank_job_")
            or index_name == "docs_v2"
        )
        assert text_fields == ["title", "body"]
        assert limit in {1, 2}
        from skeinrank_governance_api.elasticsearch import ElasticsearchSearchHit

        hits = [
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
            ElasticsearchSearchHit(
                id="3",
                index="docs",
                source={"title": "K8s runbook", "body": "k8s recovery steps"},
            ),
        ]
        return hits[offset : offset + limit]

    last_evidence_args = None

    def search_evidence_documents(
        self,
        *,
        index_name,
        text_fields,
        query_text,
        limit,
        filter_field=None,
        filter_value=None,
        timestamp_field=None,
        time_window_days=None,
    ):
        type(self).last_evidence_args = {
            "index_name": index_name,
            "text_fields": text_fields,
            "query_text": query_text,
            "limit": limit,
            "filter_field": filter_field,
            "filter_value": filter_value,
            "timestamp_field": timestamp_field,
            "time_window_days": time_window_days,
        }
        from skeinrank_governance_api.elasticsearch import ElasticsearchSearchHit

        return [
            ElasticsearchSearchHit(
                id="evidence-1",
                index="docs",
                source={
                    "title": "Cluster runbook",
                    "body": "This instruction helps run 500 k8s servers safely.",
                    "team": "infra",
                    "created_at": "2026-05-08T00:00:00Z",
                },
            ),
            ElasticsearchSearchHit(
                id="evidence-2",
                index="docs",
                source={
                    "title": "Postgres note",
                    "body": "No literal evidence here.",
                    "team": "infra",
                    "created_at": "2026-05-08T00:00:00Z",
                },
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
    assert FakeElasticsearchClient.last_search_args["offset"] == 0
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


def test_elasticsearch_evidence_finds_bounded_highlighted_snippets(
    monkeypatch, tmp_path
):
    from skeinrank_governance_api.routes import governance

    monkeypatch.setattr(
        governance, "ElasticsearchDiscoveryClient", FakeElasticsearchClient
    )
    client = _client(tmp_path, elasticsearch_url="http://es:9200")

    client.post("/v1/governance/profiles", json={"name": "default_it"})
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
            "time_window_days": 30,
        },
    )
    assert binding_response.status_code == 201

    response = client.post(
        f"/v1/governance/elasticsearch/bindings/{binding_response.json()['id']}/evidence",
        json={
            "query": "k8s",
            "canonical_value": "kubernetes",
            "max_documents": 2,
            "context_chars": 40,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["binding"]["name"] == "infra docs"
    assert payload["query"] == "k8s"
    assert payload["normalized_query"] == "k8s"
    assert payload["canonical_value"] == "kubernetes"
    assert len(payload["documents"]) == 1
    document = payload["documents"][0]
    assert document["document_id"] == "evidence-1"
    assert document["field"] == "body"
    assert document["matched_text"] == "k8s"
    assert "<mark>k8s</mark>" in document["highlighted_fragment"]
    assert (
        document["fragment"][document["match_start"] : document["match_end"]] == "k8s"
    )
    assert FakeElasticsearchClient.last_evidence_args == {
        "index_name": "docs",
        "text_fields": ["title", "body"],
        "query_text": "k8s",
        "limit": 2,
        "filter_field": "team",
        "filter_value": "infra",
        "timestamp_field": "created_at",
        "time_window_days": 30,
    }


def test_suggestion_evidence_refresh_saves_snapshot(monkeypatch, tmp_path):
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
    suggestion_response = client.post(
        "/v1/governance/profiles/default_it/suggestions",
        json={
            "canonical_value": "kubernetes",
            "alias_value": "k8s",
            "slot": "TOOL",
        },
    )
    assert suggestion_response.status_code == 201
    assert suggestion_response.json()["evidence_snapshot"] is None

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
        "/v1/governance/profiles/default_it/"
        f"suggestions/{suggestion_response.json()['id']}/evidence/refresh",
        json={"binding_id": binding_response.json()["id"], "max_documents": 2},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["evidence_checked_by"] == "local_dev"
    assert payload["evidence_checked_at"] is not None
    snapshot = payload["evidence_snapshot"]
    assert snapshot["binding_id"] == binding_response.json()["id"]
    assert snapshot["binding_name"] == "infra docs"
    assert snapshot["profile_name"] == "default_it"
    assert snapshot["index_name"] == "docs"
    assert snapshot["query"] == "k8s"
    assert snapshot["canonical_value"] == "kubernetes"
    assert len(snapshot["documents"]) == 1
    assert snapshot["documents"][0]["document_id"] == "evidence-1"
    assert "<mark>k8s</mark>" in snapshot["documents"][0]["highlighted_fragment"]

    list_response = client.get("/v1/governance/profiles/default_it/suggestions")
    assert list_response.status_code == 200
    assert list_response.json()[0]["evidence_snapshot"]["query"] == "k8s"


def test_suggestion_evidence_refresh_requires_same_profile_binding(
    monkeypatch, tmp_path
):
    from skeinrank_governance_api.routes import governance

    monkeypatch.setattr(
        governance, "ElasticsearchDiscoveryClient", FakeElasticsearchClient
    )
    client = _client(tmp_path, elasticsearch_url="http://es:9200")

    client.post("/v1/governance/profiles", json={"name": "default_it"})
    client.post("/v1/governance/profiles", json={"name": "other"})
    client.post(
        "/v1/governance/profiles/default_it/terms",
        json={"canonical_value": "kubernetes", "slot": "TOOL"},
    )
    suggestion_response = client.post(
        "/v1/governance/profiles/default_it/suggestions",
        json={"canonical_value": "kubernetes", "alias_value": "k8s", "slot": "TOOL"},
    )
    binding_response = client.post(
        "/v1/governance/elasticsearch/bindings",
        json={
            "name": "other docs",
            "profile_name": "other",
            "index_name": "docs",
            "text_fields": ["title", "body"],
            "target_field": "skeinrank",
        },
    )

    response = client.post(
        "/v1/governance/profiles/default_it/"
        f"suggestions/{suggestion_response.json()['id']}/evidence/refresh",
        json={"binding_id": binding_response.json()["id"]},
    )

    assert response.status_code == 422
    assert "must belong to the suggestion profile" in response.json()["detail"]


def test_suggestion_evidence_refresh_only_updates_pending_suggestions(
    monkeypatch, tmp_path
):
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
    suggestion_response = client.post(
        "/v1/governance/profiles/default_it/suggestions",
        json={"canonical_value": "kubernetes", "alias_value": "k8s", "slot": "TOOL"},
    )
    binding_response = client.post(
        "/v1/governance/elasticsearch/bindings",
        json={
            "name": "infra docs",
            "profile_name": "default_it",
            "index_name": "docs",
            "text_fields": ["title", "body"],
            "target_field": "skeinrank",
        },
    )
    reject_response = client.post(
        "/v1/governance/profiles/default_it/"
        f"suggestions/{suggestion_response.json()['id']}/reject"
    )
    assert reject_response.status_code == 200

    response = client.post(
        "/v1/governance/profiles/default_it/"
        f"suggestions/{suggestion_response.json()['id']}/evidence/refresh",
        json={"binding_id": binding_response.json()["id"]},
    )

    assert response.status_code == 409
    assert "Suggestion is not pending" in response.json()["detail"]


def test_elasticsearch_evidence_warns_for_stop_listed_query(monkeypatch, tmp_path):
    from skeinrank_governance_api.routes import governance

    monkeypatch.setattr(
        governance, "ElasticsearchDiscoveryClient", FakeElasticsearchClient
    )
    client = _client(tmp_path, elasticsearch_url="http://es:9200")

    client.post("/v1/governance/profiles", json={"name": "default_it"})
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
        },
    )

    response = client.post(
        f"/v1/governance/elasticsearch/bindings/{binding_response.json()['id']}/evidence",
        json={"query": "k8s", "max_documents": 2},
    )

    assert response.status_code == 200
    assert "blocked as an alias" in " ".join(response.json()["warnings"])


def test_elasticsearch_evidence_requires_connection(tmp_path):
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
        f"/v1/governance/elasticsearch/bindings/{binding_response.json()['id']}/evidence",
        json={"query": "k8s", "max_documents": 1},
    )

    assert response.status_code == 503
    assert "not configured" in response.json()["detail"]


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


def test_elasticsearch_enrichment_job_can_be_queued_for_celery(monkeypatch, tmp_path):
    from skeinrank_governance_api.routes import governance
    from skeinrank_governance_api.worker_queue import EnqueuedTask

    monkeypatch.setattr(
        governance, "ElasticsearchDiscoveryClient", FakeElasticsearchClient
    )
    enqueued: dict[str, int] = {}

    def fake_enqueue_elasticsearch_enrichment_job(*, config, job_id):
        enqueued["job_id"] = job_id
        assert config.enrichment_jobs_backend == "celery"
        return EnqueuedTask(task_id="task-123", queue=config.celery_task_queue)

    monkeypatch.setattr(
        governance,
        "enqueue_elasticsearch_enrichment_job",
        fake_enqueue_elasticsearch_enrichment_job,
    )
    client = _client(
        tmp_path,
        elasticsearch_url="http://es:9200",
        enrichment_jobs_backend="celery",
    )

    client.post("/v1/governance/profiles", json={"name": "default_it"})
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
        },
    )
    assert binding_response.status_code == 201

    response = client.post(
        f"/v1/governance/elasticsearch/bindings/{binding_response.json()['id']}/jobs",
        json={"max_documents": 2},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["status"] == "queued"
    assert payload["started_at"] is None
    assert payload["finished_at"] is None
    assert payload["documents_seen"] == 0
    assert payload["result_json"] == {
        "job_backend": "celery",
        "max_documents": 2,
        "chunk_size": 2,
        "celery_task_id": "task-123",
        "celery_queue": "test.enrichment",
    }
    assert enqueued["job_id"] == payload["id"]


def test_elasticsearch_enrichment_job_queue_failure_marks_job_failed(
    monkeypatch, tmp_path
):
    from skeinrank_governance_api.routes import governance
    from skeinrank_governance_api.worker_queue import EnrichmentJobQueueError

    monkeypatch.setattr(
        governance, "ElasticsearchDiscoveryClient", FakeElasticsearchClient
    )

    def fake_enqueue_elasticsearch_enrichment_job(*, config, job_id):
        raise EnrichmentJobQueueError("RabbitMQ is unavailable")

    monkeypatch.setattr(
        governance,
        "enqueue_elasticsearch_enrichment_job",
        fake_enqueue_elasticsearch_enrichment_job,
    )
    client = _client(
        tmp_path,
        elasticsearch_url="http://es:9200",
        enrichment_jobs_backend="celery",
    )

    client.post("/v1/governance/profiles", json={"name": "default_it"})
    binding_response = client.post(
        "/v1/governance/elasticsearch/bindings",
        json={
            "name": "infra docs",
            "profile_name": "default_it",
            "index_name": "docs",
            "text_fields": ["title", "body"],
            "target_field": "skeinrank",
            "mode": "write",
        },
    )

    response = client.post(
        f"/v1/governance/elasticsearch/bindings/{binding_response.json()['id']}/jobs",
        json={"max_documents": 2},
    )

    assert response.status_code == 503
    assert "RabbitMQ is unavailable" in response.json()["detail"]
    jobs_response = client.get("/v1/governance/elasticsearch/jobs")
    assert jobs_response.status_code == 200
    assert jobs_response.json()[0]["status"] == "failed"
    assert jobs_response.json()[0]["error_message"] == "RabbitMQ is unavailable"


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


def test_celery_enrichment_job_is_split_into_parallel_chunks(monkeypatch, tmp_path):
    from skeinrank_governance_api import job_runner
    from skeinrank_governance_api.routes import governance
    from skeinrank_governance_api.worker_queue import EnqueuedTask

    monkeypatch.setattr(
        governance, "ElasticsearchDiscoveryClient", FakeElasticsearchClient
    )
    monkeypatch.setattr(
        job_runner, "ElasticsearchDiscoveryClient", FakeElasticsearchClient
    )

    enqueued_job: dict[str, int] = {}

    def fake_enqueue_elasticsearch_enrichment_job(*, config, job_id):
        enqueued_job["job_id"] = job_id
        return EnqueuedTask(task_id="coordinator-task", queue=config.celery_task_queue)

    monkeypatch.setattr(
        governance,
        "enqueue_elasticsearch_enrichment_job",
        fake_enqueue_elasticsearch_enrichment_job,
    )

    enqueued_chunks: list[dict[str, int | str | None]] = []

    def fake_enqueue_elasticsearch_enrichment_chunk(
        *, config, job_id, chunk_index, offset, limit
    ):
        enqueued_chunks.append(
            {
                "job_id": job_id,
                "chunk_index": chunk_index,
                "offset": offset,
                "limit": limit,
            }
        )
        return EnqueuedTask(
            task_id=f"chunk-task-{chunk_index}", queue=config.celery_task_queue
        )

    import skeinrank_governance_api.worker_queue as worker_queue

    monkeypatch.setattr(
        worker_queue,
        "enqueue_elasticsearch_enrichment_chunk",
        fake_enqueue_elasticsearch_enrichment_chunk,
    )

    client = _client(
        tmp_path,
        elasticsearch_url="http://es:9200",
        enrichment_jobs_backend="celery",
    )

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
        },
    )
    assert binding_response.status_code == 201

    response = client.post(
        f"/v1/governance/elasticsearch/bindings/{binding_response.json()['id']}/jobs",
        json={"max_documents": 3, "chunk_size": 2},
    )
    assert response.status_code == 201
    job_id = response.json()["id"]
    assert enqueued_job["job_id"] == job_id

    coordinator_result = job_runner.run_elasticsearch_enrichment_job(
        job_id=job_id,
        config=client.app.state.config,
    )
    assert coordinator_result == {
        "job_id": job_id,
        "status": "running",
        "chunks_queued": 2,
    }
    assert enqueued_chunks == [
        {"job_id": job_id, "chunk_index": 0, "offset": 0, "limit": 2},
        {"job_id": job_id, "chunk_index": 1, "offset": 2, "limit": 1},
    ]

    first_chunk = job_runner.run_elasticsearch_enrichment_chunk(
        job_id=job_id,
        chunk_index=0,
        offset=0,
        limit=2,
        config=client.app.state.config,
    )
    assert first_chunk["status"] == "running"
    assert first_chunk["chunk"]["documents_seen"] == 2
    assert first_chunk["chunk"]["documents_enriched"] == 1

    second_chunk = job_runner.run_elasticsearch_enrichment_chunk(
        job_id=job_id,
        chunk_index=1,
        offset=2,
        limit=1,
        config=client.app.state.config,
    )
    assert second_chunk["status"] == "succeeded"
    assert second_chunk["chunk"]["documents_seen"] == 1
    assert second_chunk["chunk"]["documents_enriched"] == 1

    detail_response = client.get(f"/v1/governance/elasticsearch/jobs/{job_id}")
    assert detail_response.status_code == 200
    payload = detail_response.json()
    assert payload["status"] == "succeeded"
    assert payload["documents_seen"] == 3
    assert payload["documents_enriched"] == 2
    assert payload["result_json"]["execution_mode"] == "chunked"
    assert payload["result_json"]["chunk_size"] == 2
    chunked = payload["result_json"]["chunked_enrichment"]
    assert chunked["chunks_total"] == 2
    assert chunked["chunks_completed"] == 2
    assert chunked["chunks_failed"] == 0
    assert [chunk["offset"] for chunk in chunked["chunks"]] == [0, 2]
    assert payload["result_json"]["updated_document_ids"] == ["1", "3"]
    assert payload["result_json"]["alias_result"] == {"acknowledged": True}


def test_elasticsearch_enrichment_job_can_be_cancelled_while_queued(
    monkeypatch, tmp_path
):
    from skeinrank_governance_api import job_runner
    from skeinrank_governance_api.routes import governance
    from skeinrank_governance_api.worker_queue import EnqueuedTask

    monkeypatch.setattr(
        governance, "ElasticsearchDiscoveryClient", FakeElasticsearchClient
    )

    def fake_enqueue_elasticsearch_enrichment_job(*, config, job_id):
        return EnqueuedTask(task_id="coordinator-task", queue=config.celery_task_queue)

    monkeypatch.setattr(
        governance,
        "enqueue_elasticsearch_enrichment_job",
        fake_enqueue_elasticsearch_enrichment_job,
    )

    client = _client(
        tmp_path,
        elasticsearch_url="http://es:9200",
        enrichment_jobs_backend="celery",
    )
    client.post("/v1/governance/profiles", json={"name": "default_it"})
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
        },
    )
    job_response = client.post(
        f"/v1/governance/elasticsearch/bindings/{binding_response.json()['id']}/jobs",
        json={"max_documents": 2},
    )
    assert job_response.status_code == 201
    job_id = job_response.json()["id"]

    cancel_response = client.post(
        f"/v1/governance/elasticsearch/jobs/{job_id}/cancel",
        json={"reason": "wrong binding"},
    )
    assert cancel_response.status_code == 200
    payload = cancel_response.json()
    assert payload["status"] == "cancelled"
    assert payload["finished_at"] is not None
    assert payload["result_json"]["cancellation"]["reason"] == "wrong binding"

    coordinator_result = job_runner.run_elasticsearch_enrichment_job(
        job_id=job_id,
        config=client.app.state.config,
    )
    assert coordinator_result["status"] == "cancelled"
    assert coordinator_result["skipped"] is True


def test_running_chunked_enrichment_job_can_be_cancelled_safely(monkeypatch, tmp_path):
    from skeinrank_governance_api import job_runner
    from skeinrank_governance_api.routes import governance
    from skeinrank_governance_api.worker_queue import EnqueuedTask

    monkeypatch.setattr(
        governance, "ElasticsearchDiscoveryClient", FakeElasticsearchClient
    )
    monkeypatch.setattr(
        job_runner, "ElasticsearchDiscoveryClient", FakeElasticsearchClient
    )

    def fake_enqueue_elasticsearch_enrichment_job(*, config, job_id):
        return EnqueuedTask(task_id="coordinator-task", queue=config.celery_task_queue)

    monkeypatch.setattr(
        governance,
        "enqueue_elasticsearch_enrichment_job",
        fake_enqueue_elasticsearch_enrichment_job,
    )

    enqueued_chunks: list[dict[str, int]] = []

    def fake_enqueue_elasticsearch_enrichment_chunk(
        *, config, job_id, chunk_index, offset, limit
    ):
        enqueued_chunks.append(
            {
                "job_id": job_id,
                "chunk_index": chunk_index,
                "offset": offset,
                "limit": limit,
            }
        )
        return EnqueuedTask(
            task_id=f"chunk-task-{chunk_index}", queue=config.celery_task_queue
        )

    import skeinrank_governance_api.worker_queue as worker_queue

    monkeypatch.setattr(
        worker_queue,
        "enqueue_elasticsearch_enrichment_chunk",
        fake_enqueue_elasticsearch_enrichment_chunk,
    )

    client = _client(
        tmp_path,
        elasticsearch_url="http://es:9200",
        enrichment_jobs_backend="celery",
    )
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
        },
    )
    job_response = client.post(
        f"/v1/governance/elasticsearch/bindings/{binding_response.json()['id']}/jobs",
        json={"max_documents": 3, "chunk_size": 2},
    )
    job_id = job_response.json()["id"]

    coordinator_result = job_runner.run_elasticsearch_enrichment_job(
        job_id=job_id,
        config=client.app.state.config,
    )
    assert coordinator_result["chunks_queued"] == 2
    assert len(enqueued_chunks) == 2

    cancel_response = client.post(
        f"/v1/governance/elasticsearch/jobs/{job_id}/cancel",
        json={"reason": "operator requested stop"},
    )
    assert cancel_response.status_code == 200
    assert cancel_response.json()["status"] == "cancel_requested"

    chunk_result = job_runner.run_elasticsearch_enrichment_chunk(
        job_id=job_id,
        chunk_index=0,
        offset=0,
        limit=2,
        config=client.app.state.config,
    )
    assert chunk_result["status"] == "cancelled"
    assert chunk_result["chunk"]["status"] == "cancelled"

    detail_response = client.get(f"/v1/governance/elasticsearch/jobs/{job_id}")
    assert detail_response.status_code == 200
    payload = detail_response.json()
    assert payload["status"] == "cancelled"
    assert payload["finished_at"] is not None
    assert payload["result_json"]["cancellation"]["reason"] == (
        "operator requested stop"
    )
    assert "alias_result" not in payload["result_json"]
