"""Profiles (presets) and profile validation.

Profiles are declarative presets that define how SkeinRank should run.

We keep this intentionally minimal:
- one built-in scorer backend that works out of the box
- profile selects device preference (auto/cpu/cuda)

Later releases may extend profiles with additional model backends.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ProfileSpec(BaseModel):
    """A declarative profile specification.

    Fields are designed to be forward compatible.
    """

    id: str
    description: str

    model_config = ConfigDict(protected_namespaces=())

    # Device preference for execution.
    # v1 supports: auto/cpu/cuda (cuda is best-effort and may require extras).
    device: str = Field(default="auto")

    # If True and device="cuda", fail fast if CUDA execution is not available.
    strict_cuda: bool = Field(default=False)
    # Ordered device preference used when device="auto".
    # Only "cuda" and "cpu" are supported in v1.x.
    device_preference: list[str] = Field(default_factory=lambda: ["cuda", "cpu"])

    # If True, fail fast instead of falling back to CPU when CUDA was requested/preferred.
    # (Kept for forward compatibility with future devices.)
    strict_device: bool = Field(default=False)

    # Backend/model identifier. In v0.0.x we ship a built-in lightweight scorer.
    backend: str = Field(default="builtin")
    # Preferred backends to try in order. If provided, SkeinRank will try each backend
    # and pick the first available option.
    preferred_backends: list[str] | None = Field(default=None)

    model_id: str = Field(default="builtin/lexical")
    model_revision: str | None = Field(default=None)

    # Common runtime knobs (used by ML backends).
    max_length: int = Field(default=512, ge=8)

    # Batch size is optional: when omitted and auto_batch=True, the backend
    # will pick a sensible value based on the resolved device.
    batch_size: int | None = Field(default=None)

    # If True, and batch_size is not explicitly set, the backend picks
    # a device-aware batch size.
    auto_batch: bool = Field(default=True)

    # Warmup policy for ML backends.
    # - "none": no warmup
    # - "first_call": warm up lazily on the first scoring call
    # - "init": warm up during engine initialization
    warmup: str = Field(default="none")

    # Optional soft latency budget (ms). If set, SkeinRank will emit a warning
    # when a request exceeds this budget (without failing the request).
    soft_deadline_ms: float | None = Field(default=None, ge=0)

    # ONNX-specific variant selector.
    # For the SkeinRank ONNX repo layout, the model lives under a subfolder:
    #   fp32/ , fp16/ , int8/
    onnx_variant: str = Field(default="auto")

    # Future knobs (kept for compatibility)
    max_candidates: int = Field(default=2000, ge=1)
    max_text_chars: int = Field(default=20_000, ge=1)

    # Bi-encoder scoring knobs (used by backend='torch_bi_encoder').
    normalize_embeddings: bool = Field(default=True)
    similarity: str = Field(default="dot")  # dot|cosine
    query_prefix: str | None = Field(default=None)
    doc_prefix: str | None = Field(default=None)

    # Torch precision controls (torch_bi_encoder)
    # Autocast is only applied on CUDA; CPU always uses float32.
    # torch_dtype: float32|float16|bfloat16|auto
    torch_amp: bool = Field(default=False)
    torch_dtype: str = Field(default="float32")

    # Cascade (multi-stage) reranking
    # When backend="cascade", SkeinRank runs stage1 reranking on all candidates,
    # then applies stage2 reranking only to the top-M subset from stage1.
    cascade_stage1_profile_id: str | None = Field(default=None)
    cascade_stage2_profile_id: str | None = Field(default=None)
    cascade_top_m: int | None = Field(default=None, ge=1)

    def stable_hash(self) -> str:
        payload = self.model_dump(mode="json", exclude_none=True)
        blob = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
        return hashlib.sha256(blob).hexdigest()[:16]


# Built-in presets. Keep names stable.
_PROFILES: dict[str, ProfileSpec] = {
    # Always-available baseline.
    "rerank_auto": ProfileSpec(
        id="rerank_auto",
        description="Builtin lexical scoring (fast, no deps).",
        device="auto",
        backend="builtin",
        preferred_backends=["builtin"],
        warmup="none",
    ),
    "rerank_cpu": ProfileSpec(
        id="rerank_cpu",
        description="Builtin lexical scoring (CPU).",
        device="cpu",
        backend="builtin",
        preferred_backends=["builtin"],
        warmup="none",
    ),
    "rerank_gpu": ProfileSpec(
        id="rerank_gpu",
        description="Builtin lexical scoring (CUDA-preferred; no-op for baseline).",
        device="cuda",
        backend="builtin",
        preferred_backends=["builtin"],
        warmup="none",
    ),
    # Torch bi-encoder rescoring (recommended modern path).
    "e5_fast_torch": ProfileSpec(
        id="e5_fast_torch",
        description="E5 base bi-encoder rescoring (auto device). Requires: skeinrank[torch].",
        device="auto",
        backend="torch_bi_encoder",
        preferred_backends=["torch_bi_encoder"],
        model_id="intfloat/e5-base-v2",
        max_length=256,
        batch_size=None,
        auto_batch=True,
        warmup="first_call",
        normalize_embeddings=True,
        similarity="dot",
        query_prefix="query: ",
        doc_prefix="passage: ",
    ),
    "e5_quality_torch": ProfileSpec(
        id="e5_quality_torch",
        description="E5 large bi-encoder rescoring (auto device). Requires: skeinrank[torch].",
        device="auto",
        backend="torch_bi_encoder",
        preferred_backends=["torch_bi_encoder"],
        model_id="intfloat/e5-large-v2",
        max_length=256,
        batch_size=None,
        auto_batch=True,
        warmup="first_call",
        normalize_embeddings=True,
        similarity="dot",
        query_prefix="query: ",
        doc_prefix="passage: ",
    ),
    # AMP variants (autocast compute on CUDA).
    "e5_fast_torch_fp16": ProfileSpec(
        id="e5_fast_torch_fp16",
        description="E5 base bi-encoder rescoring (CUDA autocast fp16). Requires: skeinrank[torch] + CUDA.",
        device="auto",
        backend="torch_bi_encoder",
        preferred_backends=["torch_bi_encoder"],
        model_id="intfloat/e5-base-v2",
        max_length=256,
        batch_size=None,
        auto_batch=True,
        warmup="first_call",
        normalize_embeddings=True,
        similarity="dot",
        query_prefix="query: ",
        doc_prefix="passage: ",
        torch_amp=True,
        torch_dtype="float16",
    ),
    "e5_quality_torch_fp16": ProfileSpec(
        id="e5_quality_torch_fp16",
        description="E5 large bi-encoder rescoring (CUDA autocast fp16). Requires: skeinrank[torch] + CUDA.",
        device="auto",
        backend="torch_bi_encoder",
        preferred_backends=["torch_bi_encoder"],
        model_id="intfloat/e5-large-v2",
        max_length=256,
        batch_size=None,
        auto_batch=True,
        warmup="first_call",
        normalize_embeddings=True,
        similarity="dot",
        query_prefix="query: ",
        doc_prefix="passage: ",
        torch_amp=True,
        torch_dtype="float16",
    ),
    "e5_quality_torch_bf16": ProfileSpec(
        id="e5_quality_torch_bf16",
        description="E5 large bi-encoder rescoring (CUDA autocast bf16). Requires: skeinrank[torch] + bf16-capable CUDA.",
        device="auto",
        backend="torch_bi_encoder",
        preferred_backends=["torch_bi_encoder"],
        model_id="intfloat/e5-large-v2",
        max_length=256,
        batch_size=None,
        auto_batch=True,
        warmup="first_call",
        normalize_embeddings=True,
        similarity="dot",
        query_prefix="query: ",
        doc_prefix="passage: ",
        torch_amp=True,
        torch_dtype="bfloat16",
    ),
    # Deterministic device pinning variants (handy for testing/ops).
    "e5_fast_cpu": ProfileSpec(
        id="e5_fast_cpu",
        description="E5 base bi-encoder rescoring (CPU). Requires: skeinrank[torch].",
        device="cpu",
        backend="torch_bi_encoder",
        preferred_backends=["torch_bi_encoder"],
        model_id="intfloat/e5-base-v2",
        max_length=256,
        batch_size=None,
        auto_batch=True,
        warmup="first_call",
        normalize_embeddings=True,
        similarity="dot",
        query_prefix="query: ",
        doc_prefix="passage: ",
    ),
    "e5_fast_gpu": ProfileSpec(
        id="e5_fast_gpu",
        description="E5 base bi-encoder rescoring (CUDA). Requires: skeinrank[torch].",
        device="cuda",
        backend="torch_bi_encoder",
        preferred_backends=["torch_bi_encoder"],
        model_id="intfloat/e5-base-v2",
        max_length=256,
        batch_size=None,
        auto_batch=True,
        warmup="first_call",
        normalize_embeddings=True,
        similarity="dot",
        query_prefix="query: ",
        doc_prefix="passage: ",
    ),
    "e5_fast_torch_cuda_only": ProfileSpec(
        id="e5_fast_torch_cuda_only",
        description="E5 base bi-encoder rescoring (CUDA required). Requires: skeinrank[torch] with CUDA.",
        device="cuda",
        strict_cuda=True,
        strict_device=True,
        backend="torch_bi_encoder",
        preferred_backends=["torch_bi_encoder"],
        model_id="intfloat/e5-base-v2",
        max_length=256,
        batch_size=None,
        auto_batch=True,
        warmup="first_call",
        normalize_embeddings=True,
        similarity="dot",
        query_prefix="query: ",
        doc_prefix="passage: ",
    ),
    # Cascade profile: fast pass on all candidates, then quality pass on top-M.
    "e5_cascade_fast_quality_m10": ProfileSpec(
        id="e5_cascade_fast_quality_m10",
        description=(
            "Cascade reranking: e5_fast_torch on all candidates, then e5_quality_torch on top-10. "
            "Requires: skeinrank[torch]."
        ),
        device="auto",
        backend="cascade",
        preferred_backends=["cascade"],
        warmup="first_call",
        cascade_stage1_profile_id="e5_fast_torch",
        cascade_stage2_profile_id="e5_quality_torch",
        cascade_top_m=10,
    ),
    "e5_cascade_fast_quality_fp16_m10": ProfileSpec(
        id="e5_cascade_fast_quality_fp16_m10",
        description=(
            "Cascade reranking: e5_fast_torch on all candidates, then e5_quality_torch_fp16 on top-10. "
            "Requires: skeinrank[torch] + CUDA."
        ),
        device="auto",
        backend="cascade",
        preferred_backends=["cascade"],
        warmup="first_call",
        cascade_stage1_profile_id="e5_fast_torch",
        cascade_stage2_profile_id="e5_quality_torch_fp16",
        cascade_top_m=10,
    ),
    "e5_cascade_fast_quality_bf16_m10": ProfileSpec(
        id="e5_cascade_fast_quality_bf16_m10",
        description=(
            "Cascade reranking: e5_fast_torch on all candidates, then e5_quality_torch_bf16 on top-10. "
            "Requires: skeinrank[torch] + bf16-capable CUDA."
        ),
        device="auto",
        backend="cascade",
        preferred_backends=["cascade"],
        warmup="first_call",
        cascade_stage1_profile_id="e5_fast_torch",
        cascade_stage2_profile_id="e5_quality_torch_bf16",
        cascade_top_m=10,
    ),
}


class ProfileInfo(BaseModel):
    id: str
    description: str


class ValidationResult(BaseModel):
    ok: bool
    errors: list[str] = Field(default_factory=list)


def list_profiles() -> list[ProfileInfo]:
    return [ProfileInfo(id=p.id, description=p.description) for p in _PROFILES.values()]


def get_profile(profile_id: str) -> ProfileSpec:
    if profile_id not in _PROFILES:
        raise KeyError(f"Unknown profile: {profile_id}")
    return _PROFILES[profile_id]


def validate_profile(profile: ProfileSpec | dict[str, Any]) -> ValidationResult:
    errors: list[str] = []
    try:
        spec = (
            profile
            if isinstance(profile, ProfileSpec)
            else ProfileSpec.model_validate(profile)
        )
    except Exception as e:  # noqa: BLE001
        return ValidationResult(ok=False, errors=[str(e)])

    if spec.device not in {"auto", "cpu", "cuda"}:
        errors.append("device must be one of: auto, cpu, cuda")

    # Validate device_preference when present (auto resolution uses it).
    dp = getattr(spec, "device_preference", None)
    if dp is not None:
        if not isinstance(dp, list) or len(dp) == 0:
            errors.append("device_preference must be a non-empty list")
        else:
            bad = [d for d in dp if d not in {"cuda", "cpu"}]
            if bad:
                errors.append("device_preference entries must be: cuda, cpu")

    # Validate preferred_backends when present.
    pb = getattr(spec, "preferred_backends", None)
    if pb is not None:
        if pb is not None and (not isinstance(pb, list) or len(pb) == 0):
            errors.append("preferred_backends must be a non-empty list when provided")
        elif isinstance(pb, list):
            bad = [b for b in pb if b not in {"builtin", "torch_bi_encoder", "cascade"}]
            if bad:
                errors.append("preferred_backends entries must be valid backend ids")

    if getattr(spec, "strict_device", None) is not None and not isinstance(
        spec.strict_device, bool
    ):
        errors.append("strict_device must be a boolean")

    if spec.warmup not in {"none", "first_call", "init"}:
        errors.append("warmup must be one of: none, first_call, init")
    if spec.backend not in {"builtin", "torch_bi_encoder", "cascade"}:
        errors.append("backend must be one of: builtin, torch_bi_encoder, cascade")
    if spec.similarity not in {"dot", "cosine"}:
        errors.append("similarity must be one of: dot, cosine")
    if spec.batch_size is not None and spec.batch_size < 1:
        errors.append("batch_size must be >= 1 when provided")
    if spec.max_candidates <= 0:
        errors.append("max_candidates must be > 0")
    if spec.max_text_chars <= 0:
        errors.append("max_text_chars must be > 0")

    return ValidationResult(ok=(len(errors) == 0), errors=errors)
