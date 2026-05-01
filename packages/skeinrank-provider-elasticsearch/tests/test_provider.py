from __future__ import annotations

from unittest.mock import Mock

from skeinrank_provider_elasticsearch import ElasticsearchProvider


def test_retrieve_converts_hits_to_candidates():
    client = Mock()
    client.search.return_value = {
        "hits": {
            "hits": [
                {
                    "_id": "1",
                    "_source": {"text": "Doc one"},
                },
                {
                    "_id": "2",
                    "_source": {"text": "Doc two"},
                },
            ]
        }
    }

    p = ElasticsearchProvider(
        client=client, index="docs", text_fields=["text"], size=10
    )
    cands, hits = p.retrieve("hello", size=2)

    assert len(hits) == 2
    assert [c.id for c in cands] == ["1", "2"]
    assert cands[0].text == "Doc one"


def test_skips_docs_without_text_fields():
    client = Mock()
    client.search.return_value = {
        "hits": {
            "hits": [
                {"_id": "1", "_source": {}},
                {"_id": "2", "_source": {"text": "ok"}},
            ]
        }
    }
    p = ElasticsearchProvider(client=client, index="docs", text_fields=["text"])
    cands, _ = p.retrieve("q")
    assert [c.id for c in cands] == ["2"]


def test_build_query_contains_multi_match_fields():
    client = Mock()
    p = ElasticsearchProvider(
        client=client, index="docs", text_fields=["title", "body"]
    )
    q = p.build_query("hello")
    mm = q["query"]["multi_match"]
    assert mm["query"] == "hello"
    assert mm["fields"] == ["title", "body"]
