from skeinrank import RerankEngine


def test_engine_diagnostics_shape():
    eng = RerankEngine(profile="rerank_auto")
    d = eng.diagnostics()

    assert isinstance(d, dict)
    assert "runtime" in d and isinstance(d["runtime"], dict)
    assert "backends" in d and isinstance(d["backends"], dict)

    assert set(d["backends"].keys()) == {"builtin"}
    b = d["backends"]["builtin"]
    assert b["available"] is True
    assert b["details"]["always_available"] is True
    assert b["errors"] == []

    rt = d["runtime"]
    assert "python_version" in rt
    assert "platform" in rt
    assert rt["cuda_available"] is False
    assert rt["gpu_name"] is None
    assert rt["fp16_supported"] is False
    assert rt["bf16_supported"] is False
    assert rt["cuda_compute_capability"] is None
