from skeinrank.app.passport_policy import decide_effective_passport_level


def _clear_passport_env(monkeypatch):
    for k in [
        "SKEINRANK_DEBUG_SAMPLE",
        "SKEINRANK_DEBUG_ON_WARNINGS",
        "SKEINRANK_DEBUG_LATENCY_MS",
        "SKEINRANK_DEBUG_LATENCY_P95_MS",
    ]:
        monkeypatch.delenv(k, raising=False)


def test_policy_fallback_warning_upgrades_as_fallback(monkeypatch):
    _clear_passport_env(monkeypatch)
    monkeypatch.setenv("SKEINRANK_DEBUG_ON_WARNINGS", "1")
    d = decide_effective_passport_level(
        requested="summary",
        warnings=["device_fallback: cuda -> cpu"],
        total_ms=10.0,
    )
    assert d.effective == "debug"
    assert d.passport_upgraded_by == ["fallback"]
    assert d.reason_details == {"fallback_warnings": ["device_fallback: cuda -> cpu"]}


def test_policy_mixed_warnings_produces_fallback_and_warnings(monkeypatch):
    _clear_passport_env(monkeypatch)
    monkeypatch.setenv("SKEINRANK_DEBUG_ON_WARNINGS", "1")
    d = decide_effective_passport_level(
        requested="summary",
        warnings=[
            "device_fallback: cuda -> cpu",
            "candidate text truncated (id=1, chars=10 -> 4)",
            "backend_fallback: unavailable -> builtin",
        ],
        total_ms=10.0,
    )
    assert d.effective == "debug"
    assert d.passport_upgraded_by == ["fallback", "warnings"]
    assert d.reason_details is not None
    assert d.reason_details.get("fallback_warnings") == [
        "device_fallback: cuda -> cpu",
        "backend_fallback: unavailable -> builtin",
    ]
    assert d.reason_details.get("warnings_count") == 1


def test_policy_latency_reason_details(monkeypatch):
    _clear_passport_env(monkeypatch)
    monkeypatch.setenv("SKEINRANK_DEBUG_LATENCY_MS", "5")
    d = decide_effective_passport_level(
        requested="summary",
        warnings=[],
        total_ms=6.0,
    )
    assert d.effective == "debug"
    assert d.passport_upgraded_by == ["latency"]
    assert d.reason_details == {"threshold_ms": 5.0, "total_ms": 6.0}


def test_policy_sample_reason_details(monkeypatch):
    _clear_passport_env(monkeypatch)
    monkeypatch.setenv("SKEINRANK_DEBUG_SAMPLE", "1.0")
    d = decide_effective_passport_level(
        requested="summary",
        warnings=[],
        total_ms=10.0,
    )
    assert d.effective == "debug"
    assert d.passport_upgraded_by == ["sample"]
    assert d.reason_details == {"p": 1.0}
