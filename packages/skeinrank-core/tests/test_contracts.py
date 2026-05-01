from skeinrank import Candidate, RerankEngine


def test_contract_keys_are_stable():
    engine = RerankEngine(profile="rerank_auto")
    out = engine.rerank("q", [Candidate(id="doc", text="q")], debug=True)
    dumped = out.model_dump()
    # Top-level keys
    assert set(dumped.keys()) == {"query", "ranked", "passport"}
    # Ranked item keys
    assert set(dumped["ranked"][0].keys()) == {"id", "score", "rank"}
    # Passport keys (schema versioned)
    passport_keys = set(dumped["passport"].keys())
    assert {
        "schema_version",
        "request_id",
        "runtime",
        "total_ms",
        "profile_id",
        "profile_hash",
        "device",
        "backend",
        "provider",
        "variant",
        "model_id",
        "model_revision",
        "stages",
        "warnings",
    }.issubset(passport_keys)
