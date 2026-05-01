import pytest
from skeinrank import Candidate, ContractError, RerankEngine


def test_rerank_orders_by_relevance():
    engine = RerankEngine(profile="rerank_auto")
    cands = [
        Candidate(id="doc-1", text="How to reset a password in Okta"),
        Candidate(id="doc-2", text="Kubernetes ingress troubleshooting guide"),
    ]
    out = engine.rerank("okta password reset", cands, top_k=2)
    assert out.ranked[0].id == "doc-1"
    assert out.ranked[0].rank == 1
    assert len(out.ranked) == 2


def test_score_returns_all_candidate_ids():
    engine = RerankEngine()
    cands = [
        Candidate(id="a", text="alpha"),
        Candidate(id="b", text="beta"),
    ]
    out = engine.score("alpha", cands)
    assert set(out.scores.keys()) == {"a", "b"}


def test_contracts_query_and_candidates():
    engine = RerankEngine()
    with pytest.raises(ContractError):
        engine.rerank("", [Candidate(id="x", text="t")])
    with pytest.raises(ContractError):
        engine.rerank("q", [])
    with pytest.raises(ContractError):
        engine.rerank("q", [Candidate(id="x", text="")])


def test_passport_debug_contains_stages():
    engine = RerankEngine(profile="rerank_auto")
    out = engine.rerank(
        "okta password reset",
        [Candidate(id="doc", text="Okta password reset steps")],
        debug=True,
    )
    assert out.passport is not None
    assert out.passport.schema_version == "1"
    assert out.passport.profile_id == "rerank_auto"
    stage_names = [s.name for s in out.passport.stages]
    assert "score" in stage_names
    assert "sort" in stage_names


def test_gpu_profile_sets_device_and_warning():
    engine = RerankEngine(profile="rerank_gpu")
    out = engine.rerank("q", [Candidate(id="doc", text="q")], debug=True)
    assert out.passport is not None
    # Builtin scorer is CPU-only; GPU request must fall back.
    assert out.passport.device == "cpu"
    assert any("device_fallback: cuda -> cpu" in w for w in out.passport.warnings)


def test_truncation_emits_warning():
    base = RerankEngine(profile="rerank_auto").profile
    profile = base.model_copy(update={"max_text_chars": 5})
    engine = RerankEngine(profile=profile)
    out = engine.rerank("q", [Candidate(id="doc", text="0123456789")], debug=True)
    assert out.passport is not None
    assert any("truncated" in w for w in out.passport.warnings)


def test_passport_has_request_id_and_runtime():
    engine = RerankEngine(profile="rerank_cpu")
    out = engine.rerank("q", [Candidate(id="1", text="doc")], debug=True)
    p = out.passport
    assert isinstance(p.request_id, str) and len(p.request_id) >= 10
    assert p.runtime.python_version
    assert p.runtime.platform
    assert abs(p.total_ms - sum(s.elapsed_ms for s in p.stages)) < 1e-6
