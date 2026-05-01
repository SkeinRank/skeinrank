from skeinrank import RerankEngine


def test_engine_diagnostics_shape():
    eng = RerankEngine(profile="rerank_auto")
    d = eng.diagnostics()

    assert isinstance(d, dict)
    assert "runtime" in d and isinstance(d["runtime"], dict)
    assert "backends" in d and isinstance(d["backends"], dict)

    # Builtin must always be present.
    assert "builtin" in d["backends"]
    b = d["backends"]["builtin"]
    assert "available" in b
    assert b["available"] is True

    # Runtime section should include precision capability hints (best-effort).
    rt = d["runtime"]
    assert "cuda_available" in rt
    assert "gpu_name" in rt
    assert "fp16_supported" in rt
    assert "bf16_supported" in rt
    assert "cuda_compute_capability" in rt

    # Torch backend entry should exist even if deps are missing.
    assert "torch_bi_encoder" in d["backends"]
    t = d["backends"]["torch_bi_encoder"]
    assert "available" in t
    assert "details" in t and isinstance(t["details"], dict)
    assert "errors" in t and isinstance(t["errors"], list)
