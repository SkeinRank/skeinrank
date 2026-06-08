"""Profiles and profile validation.

Profiles are declarative presets that define how SkeinRank should run.
The core package intentionally keeps runtime scoring dependency-free: the
built-in lexical scorer is enough for local SDK demos, contracts, and tests.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ProfileSpec(BaseModel):
    """A declarative profile specification."""

    id: str
    description: str

    model_config = ConfigDict(protected_namespaces=())

    # Device preference for execution.
    # Core supports auto/cpu/cuda as user-facing values. The built-in scorer runs
    # on CPU; CUDA requests fall back through the standard device policy.
    device: str = Field(default="auto")
    strict_cuda: bool = Field(default=False)
    device_preference: list[str] = Field(default_factory=lambda: ["cuda", "cpu"])
    strict_device: bool = Field(default=False)

    # Backend/model identifier. The core package exposes one dependency-free backend.
    backend: str = Field(default="builtin")
    preferred_backends: list[str] | None = Field(default=None)

    model_id: str = Field(default="builtin/lexical")
    model_revision: str | None = Field(default=None)

    # Common runtime knobs retained for API compatibility.
    max_length: int = Field(default=512, ge=8)
    batch_size: int | None = Field(default=None)
    auto_batch: bool = Field(default=True)
    warmup: str = Field(default="none")
    soft_deadline_ms: float | None = Field(default=None, ge=0)
    max_candidates: int = Field(default=2000, ge=1)
    max_text_chars: int = Field(default=20_000, ge=1)

    def stable_hash(self) -> str:
        payload = self.model_dump(mode="json", exclude_none=True)
        blob = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
        return hashlib.sha256(blob).hexdigest()[:16]


# Built-in presets. Keep names stable.
_PROFILES: dict[str, ProfileSpec] = {
    "rerank_auto": ProfileSpec(
        id="rerank_auto",
        description="Builtin lexical scoring (fast, no dependencies).",
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
        description="Builtin lexical scoring with CUDA preference; falls back to CPU.",
        device="cuda",
        backend="builtin",
        preferred_backends=["builtin"],
        warmup="none",
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

    dp = getattr(spec, "device_preference", None)
    if dp is not None:
        if not isinstance(dp, list) or len(dp) == 0:
            errors.append("device_preference must be a non-empty list")
        else:
            bad = [d for d in dp if d not in {"cuda", "cpu"}]
            if bad:
                errors.append("device_preference entries must be: cuda, cpu")

    pb = getattr(spec, "preferred_backends", None)
    if pb is not None:
        if not isinstance(pb, list) or len(pb) == 0:
            errors.append("preferred_backends must be a non-empty list when provided")
        elif isinstance(pb, list):
            bad = [b for b in pb if b not in {"builtin"}]
            if bad:
                errors.append("preferred_backends entries must be valid backend ids")

    if getattr(spec, "strict_device", None) is not None and not isinstance(
        spec.strict_device, bool
    ):
        errors.append("strict_device must be a boolean")

    if spec.warmup not in {"none", "first_call", "init"}:
        errors.append("warmup must be one of: none, first_call, init")
    if spec.backend not in {"builtin"}:
        errors.append("backend must be: builtin")
    if spec.batch_size is not None and spec.batch_size < 1:
        errors.append("batch_size must be >= 1 when provided")
    if spec.max_candidates <= 0:
        errors.append("max_candidates must be > 0")
    if spec.max_text_chars <= 0:
        errors.append("max_text_chars must be > 0")

    return ValidationResult(ok=(len(errors) == 0), errors=errors)
