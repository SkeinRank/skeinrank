from __future__ import annotations

import os
from dataclasses import dataclass
from importlib import metadata
from typing import Any, Protocol, runtime_checkable

from skeinrank.adapters.builtin_lexical import BuiltinLexicalScorer
from skeinrank.adapters.cascade import CascadeScorer
from skeinrank.adapters.torch_bi_encoder import TorchBiEncoderRescorer
from skeinrank.app.profiles import ProfileSpec
from skeinrank.domain.errors import ModelUnavailable


def _safe_version(dist_name: str) -> str | None:
    try:
        return metadata.version(dist_name)
    except Exception:
        return None


@dataclass(frozen=True)
class BackendDiagnosis:
    """Structured backend availability + reasons."""

    backend_id: str
    available: bool
    details: dict[str, Any]
    errors: list[str]


@runtime_checkable
class Backend(Protocol):
    id: str

    def is_available(self, *, device: str | None = None) -> bool: ...

    def diagnose(self, *, device: str | None = None) -> BackendDiagnosis: ...

    def create_scorer(self, *, profile: ProfileSpec, resolved_device: str) -> Any: ...


class BuiltinBackend:
    id = "builtin"

    def is_available(self, *, device: str | None = None) -> bool:  # noqa: ARG002
        return True

    def diagnose(self, *, device: str | None = None) -> BackendDiagnosis:  # noqa: ARG002
        return BackendDiagnosis(
            backend_id=self.id,
            available=True,
            details={"always_available": True},
            errors=[],
        )

    def create_scorer(self, *, profile: ProfileSpec, resolved_device: str) -> Any:  # noqa: ARG002
        return BuiltinLexicalScorer()


class TorchBiEncoderBackend:
    id = "torch_bi_encoder"

    def is_available(self, *, device: str | None = None) -> bool:
        diag = self.diagnose(device=device)
        return bool(diag.available)

    def diagnose(self, *, device: str | None = None) -> BackendDiagnosis:
        errors: list[str] = []
        details: dict[str, Any] = {
            "torch_version": _safe_version("torch"),
            "transformers_version": _safe_version("transformers"),
            "force_no_torch": os.getenv("SKEINRANK_FORCE_NO_TORCH") == "1",
            "cuda_available": None,
            "cuda_build": None,
            "gpu_name": None,
            "fp16_supported": None,
            "bf16_supported": None,
            "cuda_compute_capability": None,
        }

        if details["force_no_torch"]:
            errors.append("torch backend disabled by SKEINRANK_FORCE_NO_TORCH=1")
            return BackendDiagnosis(
                backend_id=self.id, available=False, details=details, errors=errors
            )

        # Check optional deps.
        try:
            import torch  # type: ignore
        except Exception as e:
            errors.append(f"torch import failed: {e}")
            return BackendDiagnosis(
                backend_id=self.id, available=False, details=details, errors=errors
            )

        try:
            import transformers  # type: ignore  # noqa: F401
        except Exception as e:
            errors.append(f"transformers import failed: {e}")
            return BackendDiagnosis(
                backend_id=self.id, available=False, details=details, errors=errors
            )

        # Device hints (do not raise).
        try:
            details["cuda_available"] = bool(torch.cuda.is_available())
        except Exception:
            details["cuda_available"] = False
        try:
            details["cuda_build"] = getattr(
                getattr(torch, "version", None), "cuda", None
            )
        except Exception:
            details["cuda_build"] = None
        try:
            if details.get("cuda_available"):
                details["gpu_name"] = str(torch.cuda.get_device_name(0))
        except Exception:
            details["gpu_name"] = None

        # Precision capability hints (best-effort).
        try:
            details["fp16_supported"] = bool(details.get("cuda_available"))
        except Exception:
            details["fp16_supported"] = None
        try:
            if details.get("cuda_available") and hasattr(
                torch.cuda, "is_bf16_supported"
            ):
                details["bf16_supported"] = bool(torch.cuda.is_bf16_supported())
            elif details.get("cuda_available"):
                details["bf16_supported"] = False
            else:
                details["bf16_supported"] = False
        except Exception:
            details["bf16_supported"] = None
        try:
            if details.get("cuda_available"):
                cc = torch.cuda.get_device_capability(0)
                details["cuda_compute_capability"] = f"{cc[0]}.{cc[1]}"
        except Exception:
            details["cuda_compute_capability"] = None

        # Optional: if a specific device is requested, reflect support.
        if device == "cuda" and not details.get("cuda_available"):
            errors.append("cuda requested but torch.cuda.is_available() is False")

        return BackendDiagnosis(
            backend_id=self.id,
            available=(len(errors) == 0),
            details=details,
            errors=errors,
        )

    def create_scorer(self, *, profile: ProfileSpec, resolved_device: str) -> Any:
        # Mirror the adapter's explicit guard for consistent error messages.
        if os.getenv("SKEINRANK_FORCE_NO_TORCH") == "1":
            raise ModelUnavailable(
                "torch backend disabled by SKEINRANK_FORCE_NO_TORCH=1; install skeinrank[torch]"
            )

        return TorchBiEncoderRescorer(
            model_id=profile.model_id,
            model_revision=profile.model_revision,
            device=resolved_device,
            max_length=profile.max_length,
            batch_size=profile.batch_size,
            auto_batch=profile.auto_batch,
            torch_amp=getattr(profile, "torch_amp", False),
            torch_dtype=getattr(profile, "torch_dtype", "float32"),
            normalize_embeddings=profile.normalize_embeddings,
            similarity=profile.similarity,
            query_prefix=profile.query_prefix,
            doc_prefix=profile.doc_prefix,
        )


class CascadeBackend:
    """Two-stage cascade backend.

    v1 ships this as a first-class feature because it provides an excellent
    quality/latency tradeoff on many retrieval workloads.

    The backend depends on the torch bi-encoder backend for stage1/stage2.
    """

    id = "cascade"

    def is_available(self, *, device: str | None = None) -> bool:
        # Stage1 must be available; stage2 is best-effort.
        return bool(get_backend("torch_bi_encoder").is_available(device=device))

    def diagnose(self, *, device: str | None = None) -> BackendDiagnosis:
        base = get_backend("torch_bi_encoder").diagnose(device=device)
        # Re-wrap diagnosis to keep backend_id stable.
        return BackendDiagnosis(
            backend_id=self.id,
            available=base.available,
            details={
                **(base.details or {}),
                "depends_on": "torch_bi_encoder",
            },
            errors=list(base.errors or []),
        )

    def create_scorer(self, *, profile: ProfileSpec, resolved_device: str) -> Any:
        stage1_id = profile.cascade_stage1_profile_id or "e5_fast_torch"
        stage2_id = profile.cascade_stage2_profile_id or "e5_quality_torch"
        top_m = profile.cascade_top_m or 10

        # Resolve profiles for each stage.
        from skeinrank.app.profiles import get_profile

        s1_profile = get_profile(stage1_id)
        s2_profile = get_profile(stage2_id)

        # For v1, we only support torch bi-encoder stage profiles.
        if s1_profile.backend != "torch_bi_encoder":
            raise ModelUnavailable(
                f"Cascade stage1 profile must use backend torch_bi_encoder (got: {s1_profile.backend})"
            )
        if s2_profile.backend != "torch_bi_encoder":
            raise ModelUnavailable(
                f"Cascade stage2 profile must use backend torch_bi_encoder (got: {s2_profile.backend})"
            )

        torch_backend = get_backend("torch_bi_encoder")

        stage1_scorer = torch_backend.create_scorer(
            profile=s1_profile, resolved_device=resolved_device
        )

        stage2_scorer: Any | None = None
        stage2_reason: str | None = None
        try:
            stage2_scorer = torch_backend.create_scorer(
                profile=s2_profile, resolved_device=resolved_device
            )
        except Exception as e:  # noqa: BLE001
            stage2_reason = f"{type(e).__name__}: {e}"

        return CascadeScorer(
            stage1_scorer=stage1_scorer,
            stage2_scorer=stage2_scorer,
            stage1_profile_id=stage1_id,
            stage2_profile_id=stage2_id,
            top_m=int(top_m),
            resolved_device=resolved_device,
            stage2_unavailable_reason=stage2_reason,
        )


_REGISTRY: dict[str, Backend] = {
    BuiltinBackend.id: BuiltinBackend(),
    TorchBiEncoderBackend.id: TorchBiEncoderBackend(),
    CascadeBackend.id: CascadeBackend(),
}


def get_backend(backend_id: str) -> Backend:
    if backend_id not in _REGISTRY:
        raise ModelUnavailable(f"Unknown backend: {backend_id}")
    return _REGISTRY[backend_id]


def list_backends() -> list[str]:
    return sorted(_REGISTRY.keys())


def diagnose_backends(*, device: str | None = None) -> dict[str, BackendDiagnosis]:
    out: dict[str, BackendDiagnosis] = {}
    for bid, backend in _REGISTRY.items():
        try:
            out[bid] = backend.diagnose(device=device)
        except Exception as e:  # pragma: no cover
            out[bid] = BackendDiagnosis(
                backend_id=bid,
                available=False,
                details={},
                errors=[f"diagnose failed: {e}"],
            )
    return out
