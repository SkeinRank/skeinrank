from __future__ import annotations

from dataclasses import dataclass

from skeinrank import Candidate, RerankEngine, RerankRequest, rerank_many


@dataclass
class _DummyScorer:
    resolved_device: str = "cpu"
    provider: str = "dummy"
    resolved_variant: str = "dummy"
    effective_batch_size: int = 123
    last_warnings: list[str] = None

    def __post_init__(self):
        if self.last_warnings is None:
            self.last_warnings = []
        self.calls_score_many = 0
        self.calls_score = 0

    def score_many(self, queries, candidates_list, *, batch_size=None):
        self.calls_score_many += 1
        out = []
        for qi, cands in enumerate(candidates_list):
            # Deterministic: longer text => higher score, plus query index tie-breaker.
            scores = {c.id: float(len(c.text) + qi) for c in cands}
            out.append(scores)
        return out

    def score(self, query, candidates, *, batch_size=None):
        self.calls_score += 1
        return {c.id: float(len(c.text)) for c in candidates}


def test_rerank_many_uses_score_many_once():
    eng = RerankEngine(profile="rerank_auto")
    dummy = _DummyScorer()
    eng._scorer = dummy  # type: ignore[attr-defined]

    reqs = [
        RerankRequest(
            query="q1",
            candidates=[
                Candidate(id="a", text="aaa"),
                Candidate(id="b", text="bb"),
                Candidate(id="c", text="c"),
            ],
        ),
        {
            "query": "q2",
            "candidates": [{"id": "x", "text": "xxxx"}, {"id": "y", "text": "y"}],
            "top_k": 1,
        },
    ]

    out = eng.rerank_many(reqs, top_k=2, warmup=False, passport="debug")
    assert len(out) == 2
    assert dummy.calls_score_many == 1
    assert dummy.calls_score == 0

    # Per-request top_k override
    assert len(out[0].ranked) == 2
    assert len(out[1].ranked) == 1

    # Passport debug contains microbatch details
    p0 = out[0].passport
    assert p0 is not None
    assert p0.passport_level == "debug"
    assert "explicit" in (p0.passport_upgraded_by or [])
    assert [s.name for s in p0.stages] == ["score", "sort"]
    assert p0.stages[0].details.get("microbatch") is True
    assert p0.stages[0].details.get("microbatch_size") == 2


def test_rerank_many_function_smoke():
    reqs = [
        {
            "query": "hello",
            "candidates": [
                {"id": "1", "text": "hello world"},
                {"id": "2", "text": "hi"},
            ],
        },
        {"query": "bye", "candidates": [{"id": "3", "text": "bye bye"}], "top_k": 1},
    ]
    out = rerank_many(reqs, profile="rerank_auto", warmup=False, passport="summary")
    assert len(out) == 2
    assert out[0].passport is not None
    assert out[0].passport.passport_level == "summary"
    # Summary strips stage details
    assert out[0].passport.stages[0].details == {}
