def test_rerank_es_contract_summary(client):
    payload = {
        "query": "okta password reset",
        "index": "kb",
        "bm25_k": 2,
        "top_k": 1,
        "profile": "rerank_auto",
        "passport": "summary",
    }
    r = client.post("/v1/rerank/es", json=payload)
    assert r.status_code == 200
    data = r.json()
    assert "request_id" in data
    assert data["profile"] == "rerank_auto"
    assert data["index"] == "kb"
    assert data["bm25_k"] == 2
    assert data["top_k"] == 1
    assert isinstance(data["results"], list) and len(data["results"]) == 1
    assert data["passport"] is not None
    assert data["passport"]["passport_level"] == "summary"


def test_rerank_es_contract_off(client):
    payload = {
        "query": "okta password reset",
        "bm25_k": 2,
        "top_k": 1,
        "passport": "off",
    }
    r = client.post("/v1/rerank/es", json=payload)
    assert r.status_code == 200
    data = r.json()
    assert data["passport"] is None
