from __future__ import annotations

from skeinrank.adapters.torch_bi_encoder import resolve_torch_precision
from skeinrank.app.profiles import get_profile


def test_precision_policy_cpu_forces_fp32_and_warns():
    r = resolve_torch_precision(
        device="cpu",
        amp=True,
        dtype="float16",
        cuda_available=False,
        bf16_supported=False,
    )
    assert r.variant == "torch.float32"
    assert r.amp_enabled is False
    assert "precision_ignored_on_cpu" in r.warnings


def test_precision_policy_cuda_bf16_fallback_to_fp16():
    r = resolve_torch_precision(
        device="cuda",
        amp=True,
        dtype="bfloat16",
        cuda_available=True,
        bf16_supported=False,
    )
    assert r.variant == "torch.amp.fp16"
    assert r.amp_enabled is True
    assert r.autocast_dtype == "float16"
    assert "precision_fallback: bf16 -> fp16" in r.warnings


def test_precision_policy_cuda_auto_prefers_bf16():
    r = resolve_torch_precision(
        device="cuda",
        amp=False,
        dtype="auto",
        cuda_available=True,
        bf16_supported=True,
    )
    # dtype=auto implies amp on CUDA.
    assert r.variant == "torch.amp.bf16"
    assert r.autocast_dtype == "bfloat16"
    assert r.warnings == []


def test_amp_profiles_exist():
    # Profiles are "first-class" contract.
    assert get_profile("e5_fast_torch_fp16").torch_dtype == "float16"
    assert get_profile("e5_quality_torch_fp16").torch_dtype == "float16"
    assert get_profile("e5_quality_torch_bf16").torch_dtype == "bfloat16"


def test_precision_policy_alias_keywords_supported():
    r = resolve_torch_precision(
        device="cuda",
        torch_amp=True,
        torch_dtype="float16",
        cuda_available=True,
        bf16_supported=True,
    )
    assert r.variant in ("torch.amp.fp16", "torch.amp.bf16", "torch.float32")
