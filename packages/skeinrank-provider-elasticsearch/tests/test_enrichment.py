from __future__ import annotations

from skeinrank_provider_elasticsearch.enrichment import (
    ElasticsearchEnrichmentConfig,
    build_enrichment_payload,
    compose_hit_text,
    preview_enrichment,
    write_enrichment,
)


class FakeElasticsearchClient:
    def __init__(self, hits):
        self.hits = list(hits)
        self.search_calls = []
        self.bulk_calls = []

    def search(self, *, index, body):
        self.search_calls.append({"index": index, "body": body})
        offset = int(body.get("from", 0))
        size = int(body.get("size", 10))
        return {"hits": {"hits": self.hits[offset : offset + size]}}

    def bulk(self, *, operations=None, body=None):
        payload = operations if operations is not None else body
        self.bulk_calls.append(payload)
        item_count = len(payload or []) // 2
        return {
            "errors": False,
            "items": [
                {"update": {"_id": payload[i * 2]["update"]["_id"], "status": 200}}
                for i in range(item_count)
            ],
        }


class FakeBulkErrorElasticsearchClient(FakeElasticsearchClient):
    def bulk(self, *, operations=None, body=None):
        payload = operations if operations is not None else body
        self.bulk_calls.append(payload)
        return {
            "errors": True,
            "items": [
                {
                    "update": {
                        "_id": payload[0]["update"]["_id"],
                        "status": 409,
                        "error": {"type": "version_conflict_engine_exception"},
                    }
                }
            ],
        }


def test_compose_hit_text_reads_multiple_and_dotted_fields():
    hit = {
        "_source": {
            "title": "Kubernetes incident",
            "body": "k8s timeout",
            "metadata": {"summary": "api-server 1.28"},
        }
    }

    text = compose_hit_text(hit, ["title", "body", "metadata.summary"])

    assert text == "Kubernetes incident\nk8s timeout\napi-server 1.28"


def test_build_enrichment_payload_is_compact_by_default():
    payload = build_enrichment_payload(
        "k8s timeout on api-server 1.28", profile="default_it"
    )

    assert payload["profile_id"] == "default_it"
    assert payload["snapshot_version"] == "default_it@2026-04-29-v1"
    assert payload["alias_matcher_backend"] == "aho_corasick"
    assert "kubernetes" in payload["canonical_values"]
    assert "timeout" in payload["canonical_values"]
    assert payload["slots"]["TOOL"] == ["kubernetes"]
    assert payload["slots"]["ERROR"] == ["timeout"]
    assert "attributes" not in payload
    assert "snapshot" not in payload
    assert "passport" not in payload


def test_build_enrichment_payload_can_include_full_evidence():
    payload = build_enrichment_payload(
        "k8s timeout on api-server 1.28",
        profile="default_it",
        include_evidence=True,
    )

    assert payload["snapshot"]["version"] == "default_it@2026-04-29-v1"
    assert payload["attributes"]
    assert any(item["evidences"] for item in payload["attributes"])


def test_preview_enrichment_dry_run_builds_compact_target_field_payload():
    client = FakeElasticsearchClient(
        [
            {
                "_id": "1",
                "_index": "docs",
                "_source": {
                    "title": "Kube issue",
                    "body": "kube timeout after k8s upgrade",
                },
            }
        ]
    )
    config = ElasticsearchEnrichmentConfig(
        index="docs",
        text_fields=("title", "body"),
        target_field="skeinrank",
        limit=10,
        batch_size=5,
    )

    report = preview_enrichment(client, config)

    assert report["summary"]["dry_run"] is True
    assert report["summary"]["previewed"] == 1
    assert report["summary"]["include_evidence"] is False
    assert client.bulk_calls == []
    preview = report["previews"][0]
    assert preview["_id"] == "1"
    payload = preview["doc"]["skeinrank"]
    assert payload["snapshot_version"] == "default_it@2026-04-29-v1"
    assert "kubernetes" in payload["canonical_values"]
    assert payload["slots"]["TOOL"] == ["kubernetes"]
    assert "attributes" not in payload


def test_preview_enrichment_can_include_evidence_when_requested():
    client = FakeElasticsearchClient(
        [
            {
                "_id": "1",
                "_index": "docs",
                "_source": {"body": "k8s timeout"},
            }
        ]
    )
    config = ElasticsearchEnrichmentConfig(
        index="docs",
        text_fields=("body",),
        target_field="skeinrank",
        limit=1,
        batch_size=1,
        include_evidence=True,
    )

    report = preview_enrichment(client, config)

    payload = report["previews"][0]["doc"]["skeinrank"]
    assert report["summary"]["include_evidence"] is True
    assert "attributes" in payload
    assert "snapshot" in payload


def test_preview_enrichment_respects_limit_and_skips_missing_text():
    client = FakeElasticsearchClient(
        [
            {"_id": "1", "_source": {"body": "k8s timeout"}},
            {"_id": "2", "_source": {}},
            {"_id": "3", "_source": {"body": "redis latency"}},
        ]
    )
    config = ElasticsearchEnrichmentConfig(
        index="docs",
        text_fields=("body",),
        target_field="skeinrank",
        limit=2,
        batch_size=1,
    )

    report = preview_enrichment(client, config)

    assert report["summary"]["processed"] == 2
    assert report["summary"]["previewed"] == 1
    assert report["summary"]["skipped"] == 1
    assert report["skipped"] == [{"_id": "2", "reason": "missing_text_fields"}]
    assert len(client.search_calls) == 2


def test_write_enrichment_sends_bulk_update_operations():
    client = FakeElasticsearchClient(
        [
            {
                "_id": "1",
                "_index": "docs",
                "_source": {"title": "Kube issue", "body": "kube timeout"},
            },
            {
                "_id": "2",
                "_index": "docs",
                "_source": {"title": "Redis issue", "body": "redis latency spike"},
            },
        ]
    )
    config = ElasticsearchEnrichmentConfig(
        index="docs",
        text_fields=("title", "body"),
        target_field="skeinrank",
        limit=10,
        batch_size=1,
    )

    report = write_enrichment(client, config)

    assert report["summary"]["dry_run"] is False
    assert report["summary"]["write_mode"] == "bulk_update"
    assert report["summary"]["enriched"] == 2
    assert report["summary"]["updated"] == 2
    assert report["summary"]["failed"] == 0
    assert report["summary"]["bulk_batches"] == 2
    assert report["summary"]["include_evidence"] is False
    assert len(client.bulk_calls) == 2
    first_bulk = client.bulk_calls[0]
    assert first_bulk[0] == {"update": {"_index": "docs", "_id": "1"}}
    assert "skeinrank" in first_bulk[1]["doc"]
    payload = first_bulk[1]["doc"]["skeinrank"]
    assert "kubernetes" in payload["canonical_values"]
    assert "attributes" not in payload


def test_write_enrichment_reports_bulk_errors():
    client = FakeBulkErrorElasticsearchClient(
        [
            {
                "_id": "1",
                "_index": "docs",
                "_source": {"body": "k8s timeout"},
            }
        ]
    )
    config = ElasticsearchEnrichmentConfig(
        index="docs",
        text_fields=("body",),
        target_field="skeinrank",
        limit=1,
        batch_size=10,
    )

    report = write_enrichment(client, config)

    assert report["summary"]["updated"] == 0
    assert report["summary"]["failed"] == 1
    assert report["errors"][0]["_id"] == "1"


def test_build_enrichment_payload_can_include_matched_aliases_without_evidence():
    payload = build_enrichment_payload(
        "k8s timeout on pg",
        profile="default_it",
        include_matched_aliases=True,
    )

    assert "k8s" in payload["matched_aliases"]
    assert "pg" in payload["matched_aliases"]
    assert payload["matched_aliases_by_value"]["kubernetes"] == ["k8s"]
    assert payload["matched_aliases_by_value"]["postgresql"] == ["pg"]
    assert "attributes" not in payload
    assert "snapshot" not in payload
    assert "passport" not in payload


def test_build_enrichment_payload_deduplicates_matched_aliases():
    payload = build_enrichment_payload(
        "k8s and k8s timeout",
        profile="default_it",
        include_matched_aliases=True,
    )

    assert payload["matched_aliases"].count("k8s") == 1
    assert payload["matched_aliases_by_value"]["kubernetes"] == ["k8s"]


def test_build_enrichment_payload_can_include_fuzzy_matched_aliases():
    profile = {
        "profile_id": "company_terms",
        "snapshot": {"version": "company_terms@v1", "source": "test"},
        "aliases": [
            {
                "slot": "TOOL",
                "canonical": "kubernetes",
                "aliases": ["kubernetes", "kuber"],
            }
        ],
        "rules": [],
    }

    payload = build_enrichment_payload(
        "kubernets issue",
        profile=profile,
        include_matched_aliases=True,
        enable_fuzzy=True,
        fuzzy_threshold=0.88,
    )

    assert payload["matched_aliases"] == ["kubernets"]
    assert payload["matched_aliases_by_value"] == {"kubernetes": ["kubernets"]}


def test_write_enrichment_can_report_matched_aliases_when_requested():
    client = FakeElasticsearchClient(
        [
            {
                "_id": "1",
                "_index": "docs",
                "_source": {"body": "k8s timeout"},
            }
        ]
    )
    config = ElasticsearchEnrichmentConfig(
        index="docs",
        text_fields=("body",),
        target_field="skeinrank",
        limit=1,
        batch_size=1,
        include_matched_aliases=True,
    )

    report = write_enrichment(client, config)

    assert report["summary"]["include_matched_aliases"] is True
    assert report["updates"][0]["matched_aliases"] == ["k8s"]
    payload = client.bulk_calls[0][1]["doc"]["skeinrank"]
    assert payload["matched_aliases_by_value"] == {"kubernetes": ["k8s"]}
