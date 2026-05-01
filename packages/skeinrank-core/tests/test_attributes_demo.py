import json

from skeinrank import (
    enrich_documents,
    enrich_jsonl,
    evaluate_demo_queries,
    load_jsonl,
    write_jsonl,
)


def test_enrich_documents_produces_expected_fields():
    docs = [
        {
            "id": "doc_001",
            "title": "Kubernetes api-server timeout after upgrade",
            "text": "After upgrading the production cluster to Kubernetes 1.28, the api-server started returning timeout errors.",
        }
    ]

    enriched = enrich_documents(docs, debug=True)
    assert len(enriched) == 1
    doc = enriched[0]
    assert doc["original_text"] == docs[0]["text"]
    assert "extracted_attributes" in doc
    assert "canonical_values" in doc
    assert "passport" in doc
    assert doc["snapshot"]["version"] == "default_it@2026-04-29-v1"
    assert doc["alias_matcher_backend"] == "aho_corasick"
    assert "api-server" in doc["canonical_values"]
    assert "timeout" in doc["canonical_values"]


def test_jsonl_roundtrip_and_eval_report(tmp_path):
    docs_path = tmp_path / "demo_documents.jsonl"
    enriched_path = tmp_path / "demo_enriched_documents.jsonl"

    queries = [
        {
            "id": "q_001",
            "text": "k8s api timeout after 1.28 upgrade",
            "relevant": ["doc_001"],
        },
        {
            "id": "q_002",
            "text": "asp.net nullreferenceexception in prod",
            "relevant": ["doc_002"],
        },
    ]
    docs = [
        {
            "id": "doc_001",
            "title": "Kubernetes api-server timeout after upgrade",
            "text": "After upgrading the production cluster to Kubernetes 1.28, the api-server started returning timeout errors.",
        },
        {
            "id": "doc_002",
            "title": "Dotnet service fails with NullReferenceException",
            "text": "A dotnet 8 service in prod failed with NullReferenceException after a configuration rollout.",
        },
    ]

    write_jsonl(docs_path, docs)
    assert docs_path.exists()
    assert enrich_jsonl(docs_path, enriched_path, debug=True) == 2

    loaded_docs = load_jsonl(enriched_path)
    report = evaluate_demo_queries(queries, loaded_docs, top_k=2)

    assert report["summary"]["total_queries"] == 2
    assert (
        report["summary"]["normalized_top1_hits"]
        >= report["summary"]["baseline_top1_hits"]
    )
    assert len(report["rows"]) == 2
    assert report["rows"][0]["baseline_topk"]
    assert report["rows"][0]["normalized_topk"]

    # The report should stay JSON-serializable for CLI usage.
    json.dumps(report, ensure_ascii=False)


def test_normalized_scoring_can_beat_plain_lexical_baseline_on_alias_heavy_query():
    docs = [
        {
            "id": "doc_001",
            "title": "Payment service rollout in prod",
            "text": "The service in prod failed after rollout because of a bad flag.",
        },
        {
            "id": "doc_002",
            "title": "Dotnet service fails with NullReferenceException",
            "text": "A dotnet 8 service in prod failed with NullReferenceException after a configuration rollout.",
        },
    ]

    enriched = enrich_documents(docs, debug=True)
    report = evaluate_demo_queries(
        [
            {
                "id": "q_alias",
                "text": "asp.net null ref in prod",
                "relevant": ["doc_002"],
            }
        ],
        enriched,
        top_k=2,
    )

    row = report["rows"][0]
    assert row["baseline_top1"] == "doc_001"
    assert row["normalized_top1"] == "doc_002"
    assert row["baseline_hit"] is False
    assert row["normalized_hit"] is True
