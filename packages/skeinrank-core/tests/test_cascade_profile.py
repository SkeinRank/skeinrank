from __future__ import annotations

import pytest
from skeinrank import Candidate, RerankEngine
from skeinrank.app import profiles as profiles_mod
from skeinrank.backends import registry as reg
from skeinrank.domain.errors import ModelUnavailable


class _FakeScorer:
    """A tiny deterministic scorer used to test cascade logic without torch."""

    def __init__(self, *, kind: str, resolved_device: str):
        self.kind = kind
        self.resolved_device = resolved_device
        self.provider = "fake"
        self.resolved_variant = "fake"
        self.effective_batch_size = None
        self.last_warnings: list[str] = []

    def score(
        self, query: str, candidates: list[Candidate], *, batch_size: int | None = None
    ):  # noqa: ARG002
        if self.kind == "quality_raise":
            raise RuntimeError("simulated stage2 failure")
        # Stage1: score by descending id (d>c>b>a) for a stable top-M selection.
        if self.kind == "fast":
            return {c.id: float(ord(c.id[0])) for c in candidates}

        # Stage2: invert the order within top-M so we can observe that stage2 wins.
        # (E.g. if stage1 picked {"d", "c"}, stage2 should rank "c" above "d".)
        return {c.id: 1000.0 - float(ord(c.id[0])) for c in candidates}


class _FakeTorchBackend:
    """Replaces the torch backend for unit tests."""

    id = "torch_bi_encoder"

    def __init__(self, *, stage2_available: bool = True, stage2_raises: bool = False):
        self._stage2_available = stage2_available
        self._stage2_raises = stage2_raises

    def is_available(self, *, device: str | None = None) -> bool:  # noqa: ARG002
        return True

    def diagnose(self, *, device: str | None = None):  # noqa: ARG002
        # Keep the shape compatible with BackendDiagnosis.
        return reg.BackendDiagnosis(
            backend_id=self.id,
            available=True,
            details={"cuda_available": True},
            errors=[],
        )

    def create_scorer(self, *, profile, resolved_device: str):  # noqa: ANN001
        # We detect stage by model id in the profile.
        if "large" in (profile.model_id or ""):
            if not self._stage2_available:
                raise ModelUnavailable("stage2 unavailable")
            if self._stage2_raises:
                return _FakeScorer(
                    kind="quality_raise", resolved_device=resolved_device
                )
            return _FakeScorer(kind="quality", resolved_device=resolved_device)
        return _FakeScorer(kind="fast", resolved_device=resolved_device)


@pytest.fixture()
def _patch_fake_torch_backend(monkeypatch):
    """Patch the registry so cascade can be tested without torch installed."""

    fake = _FakeTorchBackend(stage2_available=True)
    monkeypatch.setitem(reg._REGISTRY, "torch_bi_encoder", fake)
    yield fake


def test_cascade_profile_exists():
    spec = profiles_mod.get_profile("e5_cascade_fast_quality_m10")
    assert spec.backend == "cascade"
    assert spec.cascade_stage1_profile_id == "e5_fast_torch"
    assert spec.cascade_stage2_profile_id == "e5_quality_torch"
    assert spec.cascade_top_m == 10

    spec_fp16 = profiles_mod.get_profile("e5_cascade_fast_quality_fp16_m10")
    assert spec_fp16.backend == "cascade"
    assert spec_fp16.cascade_stage1_profile_id == "e5_fast_torch"
    assert spec_fp16.cascade_stage2_profile_id == "e5_quality_torch_fp16"
    assert spec_fp16.cascade_top_m == 10

    spec_bf16 = profiles_mod.get_profile("e5_cascade_fast_quality_bf16_m10")
    assert spec_bf16.backend == "cascade"
    assert spec_bf16.cascade_stage1_profile_id == "e5_fast_torch"
    assert spec_bf16.cascade_stage2_profile_id == "e5_quality_torch_bf16"
    assert spec_bf16.cascade_top_m == 10


def test_cascade_debug_stages_and_rerank_order(_patch_fake_torch_backend):
    # Make a small cascade profile with top_m=2 for deterministic assertions.
    base = profiles_mod.get_profile("e5_cascade_fast_quality_m10")
    test_profile = base.model_copy(update={"id": "test_cascade_m2", "cascade_top_m": 2})

    engine = RerankEngine(profile=test_profile)
    cands = [
        Candidate(id="a", text="A"),
        Candidate(id="b", text="B"),
        Candidate(id="c", text="C"),
        Candidate(id="d", text="D"),
    ]

    out = engine.rerank("q", cands, top_k=2, debug=True, warmup=False)
    assert out.passport is not None
    assert [s.name for s in out.passport.stages] == [
        "score_fast",
        "score_quality",
        "sort",
    ]

    # Stage1 picks top-2 as {'d','c'} (highest ord). Stage2 inverts, so 'c' outranks 'd'.
    ids = [r.id for r in out.ranked]
    assert ids == ["c", "d"]


def test_cascade_fallback_when_stage2_unavailable(monkeypatch):
    # Patch registry with a fake torch backend where stage2 scorer creation fails.
    fake = _FakeTorchBackend(stage2_available=False)
    monkeypatch.setitem(reg._REGISTRY, "torch_bi_encoder", fake)

    base = profiles_mod.get_profile("e5_cascade_fast_quality_m10")
    test_profile = base.model_copy(update={"id": "test_cascade_m2", "cascade_top_m": 2})

    engine = RerankEngine(profile=test_profile)
    cands = [
        Candidate(id="a", text="A"),
        Candidate(id="b", text="B"),
        Candidate(id="c", text="C"),
        Candidate(id="d", text="D"),
    ]

    out = engine.rerank("q", cands, top_k=2, debug=True, warmup=False)
    assert out.passport is not None
    # Fallback uses stage1 order.
    ids = [r.id for r in out.ranked]
    assert ids == ["d", "c"]
    assert "cascade_fallback:stage2_unavailable" in out.passport.warnings

    # Stage list stays stable; stage2 is present but marked as skipped.
    stg = {s.name: s for s in out.passport.stages}
    assert "score_quality" in stg
    assert stg["score_quality"].details.get("skipped") is True
    assert stg["score_quality"].details.get("skip_reason") == "stage2_unavailable"
    # Detailed reason is available only in debug stage details (and should be short).
    assert isinstance(stg["score_quality"].details.get("unavailable_reason"), str)


def test_cascade_fallback_when_stage2_errors(monkeypatch):
    # Patch registry with a fake torch backend where stage2 scorer exists but errors at inference.
    fake = _FakeTorchBackend(stage2_available=True, stage2_raises=True)
    monkeypatch.setitem(reg._REGISTRY, "torch_bi_encoder", fake)

    base = profiles_mod.get_profile("e5_cascade_fast_quality_m10")
    test_profile = base.model_copy(
        update={"id": "test_cascade_m2_err", "cascade_top_m": 2}
    )

    engine = RerankEngine(profile=test_profile)
    cands = [
        Candidate(id="a", text="A"),
        Candidate(id="b", text="B"),
        Candidate(id="c", text="C"),
        Candidate(id="d", text="D"),
    ]

    out = engine.rerank("q", cands, top_k=2, debug=True, warmup=False)
    assert out.passport is not None

    # Fallback uses stage1 order.
    ids = [r.id for r in out.ranked]
    assert ids == ["d", "c"]
    assert "cascade_fallback:stage2_error" in out.passport.warnings

    # Stage2 exists but should be marked skipped due to error.
    stg = {s.name: s for s in out.passport.stages}
    assert stg["score_quality"].details.get("skipped") is True
    assert stg["score_quality"].details.get("skip_reason") == "stage2_error"
    assert stg["score_quality"].details.get("error_type") == "RuntimeError"
    assert "simulated stage2 failure" in str(
        stg["score_quality"].details.get("error_msg")
    )
