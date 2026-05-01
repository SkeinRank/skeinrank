import pytest
from skeinrank import Candidate, RerankEngine


def _clear_passport_env(monkeypatch):
    for k in [
        "SKEINRANK_DEBUG_SAMPLE",
        "SKEINRANK_DEBUG_ON_WARNINGS",
        "SKEINRANK_DEBUG_LATENCY_MS",
        "SKEINRANK_DEBUG_LATENCY_P95_MS",
    ]:
        monkeypatch.delenv(k, raising=False)


def test_default_passport_is_summary_and_prunes_details(monkeypatch):
    _clear_passport_env(monkeypatch)
    engine = RerankEngine(profile="rerank_auto")
    out = engine.rerank("q", [Candidate(id="1", text="doc")], warmup=False)
    assert out.passport is not None
    assert out.passport.passport_level == "summary"
    assert out.passport.reason_details is None
    assert out.passport.passport_upgraded_by == []
    assert [s.name for s in out.passport.stages] == ["score", "sort"]
    assert all(s.details == {} for s in out.passport.stages)


def test_passport_off_disables_passport(monkeypatch):
    _clear_passport_env(monkeypatch)
    engine = RerankEngine(profile="rerank_auto")
    out = engine.rerank(
        "q", [Candidate(id="1", text="doc")], warmup=False, passport="off"
    )
    assert out.passport is None


def test_debug_true_is_alias_for_debug_level(monkeypatch):
    _clear_passport_env(monkeypatch)
    engine = RerankEngine(profile="rerank_auto")
    out = engine.rerank("q", [Candidate(id="1", text="doc")], warmup=False, debug=True)
    assert out.passport is not None
    assert out.passport.passport_level == "debug"
    # Explicit debug has no extra upgrade params
    assert out.passport.reason_details is None
    assert out.passport.passport_upgraded_by == ["explicit"]
    # score stage contains some details in debug level
    score_stage = next(s for s in out.passport.stages if s.name == "score")
    assert isinstance(score_stage.details, dict) and len(score_stage.details) > 0


def test_debug_sampling_upgrades_summary_to_debug(monkeypatch):
    _clear_passport_env(monkeypatch)
    monkeypatch.setenv("SKEINRANK_DEBUG_SAMPLE", "1.0")
    engine = RerankEngine(profile="rerank_auto")
    out = engine.rerank("q", [Candidate(id="1", text="doc")], warmup=False)
    assert out.passport is not None
    assert out.passport.passport_level == "debug"
    assert out.passport.passport_upgraded_by == ["sample"]
    assert out.passport.reason_details == {"p": 1.0}


def test_debug_on_warnings_upgrades_to_debug(monkeypatch):
    _clear_passport_env(monkeypatch)
    monkeypatch.setenv("SKEINRANK_DEBUG_ON_WARNINGS", "1")
    base = RerankEngine(profile="rerank_auto").profile
    profile = base.model_copy(update={"max_text_chars": 4})
    engine = RerankEngine(profile=profile)
    out = engine.rerank("q", [Candidate(id="1", text="0123456789")], warmup=False)
    assert out.passport is not None
    assert out.passport.passport_level == "debug"
    assert out.passport.passport_upgraded_by == ["fallback", "warnings"]
    assert out.passport.reason_details is not None
    assert out.passport.reason_details.get("warnings_count") == 1
    assert isinstance(out.passport.reason_details.get("fallback_warnings"), list)
    assert any("truncated" in w for w in out.passport.warnings)


def test_latency_trigger_upgrades_to_debug(monkeypatch):
    from skeinrank.app.passport_policy import decide_effective_passport_level

    _clear_passport_env(monkeypatch)
    monkeypatch.setenv("SKEINRANK_DEBUG_LATENCY_MS", "1")

    d = decide_effective_passport_level(
        requested="summary",
        warnings=[],
        total_ms=2.0,
    )
    assert d.effective == "debug"
    assert d.passport_upgraded_by == ["latency"]
    assert d.reason_details == {"threshold_ms": 1.0, "total_ms": 2.0}


def test_unknown_passport_level_raises_valueerror(monkeypatch):
    _clear_passport_env(monkeypatch)
    engine = RerankEngine(profile="rerank_auto")
    with pytest.raises(ValueError):
        engine.rerank(
            "q", [Candidate(id="1", text="doc")], warmup=False, passport="nope"
        )
