from skeinrank import Candidate, RerankEngine


def test_rerank_accepts_batch_size_and_warmup_overrides():
    engine = RerankEngine(profile="rerank_auto")  # builtin lexical scorer
    out = engine.rerank(
        "q",
        [Candidate(id="1", text="doc")],
        debug=True,
        batch_size=16,
        warmup=False,
    )
    assert out.ranked[0].id == "1"
    assert out.passport is not None
