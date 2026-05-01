from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from skeinrank.domain.errors import ModelUnavailable
from skeinrank.domain.types import Candidate


@dataclass(frozen=True)
class _PrecisionResolution:
    """Resolved precision policy for the Torch bi-encoder.

    This is intentionally torch-free so it can be unit-tested without CUDA.
    """

    amp_enabled: bool
    autocast_dtype: str  # "float32"|"float16"|"bfloat16"
    variant: str  # passport.variant
    warnings: list[str]


def resolve_torch_precision(
    *,
    device: str,
    amp: bool | None = None,
    dtype: str | None = None,
    torch_amp: bool | None = None,
    torch_dtype: str | None = None,
    cuda_available: bool,
    bf16_supported: bool,
) -> _PrecisionResolution:
    """Resolve autocast precision in a deterministic way.

    Rules (product-facing):
    - CPU always uses float32; amp/dtype are ignored with a warning.
    - On CUDA:
        dtype=float16 -> fp16 autocast
        dtype=bfloat16 -> bf16 autocast (fallback if unsupported)
        dtype=auto -> bf16 if supported, else fp16
    - `amp` is treated as a convenience flag; if dtype != float32 we implicitly enable amp.
    """

    # Backward/forward compatible aliases: allow callers to pass either
    # (amp, dtype) or (torch_amp, torch_dtype).
    if amp is None and torch_amp is not None:
        amp = torch_amp
    if dtype is None and torch_dtype is not None:
        dtype = torch_dtype
    if amp is None:
        amp = False
    if dtype is None:
        dtype = "float32"
    if torch_amp is not None and amp != torch_amp:
        raise ValueError("Conflicting values for amp and torch_amp")
    if torch_dtype is not None and dtype != torch_dtype:
        raise ValueError("Conflicting values for dtype and torch_dtype")

    device = (device or "auto").lower()
    dtype = (dtype or "float32").lower()

    # Normalize aliases.
    if dtype in ("fp16", "half"):
        dtype = "float16"
    if dtype in ("bf16",):
        dtype = "bfloat16"

    warnings: list[str] = []

    # CPU path: always fp32.
    if device == "cpu" or (device == "auto" and not cuda_available):
        if amp or dtype not in ("float32", "auto"):
            warnings.append("precision_ignored_on_cpu")
        return _PrecisionResolution(
            amp_enabled=False,
            autocast_dtype="float32",
            variant="torch.float32",
            warnings=warnings,
        )

    # CUDA requested/auto with CUDA available.
    if not cuda_available:
        # Defensive: should not happen if device resolution is correct.
        warnings.append("precision_fallback: fp16 -> fp32")
        return _PrecisionResolution(
            amp_enabled=False,
            autocast_dtype="float32",
            variant="torch.float32",
            warnings=warnings,
        )

    # Decide target autocast dtype.
    target: str
    if dtype == "auto":
        target = "bfloat16" if bf16_supported else "float16"
    elif dtype in ("float32", "float16", "bfloat16"):
        target = dtype
    else:
        # Unknown dtype -> keep safe.
        target = "float32"

    # Apply fallbacks for unsupported bf16.
    if target == "bfloat16" and not bf16_supported:
        # Prefer fp16 over fp32 on CUDA.
        warnings.append("precision_fallback: bf16 -> fp16")
        target = "float16"

    # Effective amp: enabled if explicitly requested OR if precision is not fp32.
    amp_enabled = bool(amp) or target != "float32"

    if not amp_enabled or target == "float32":
        return _PrecisionResolution(
            amp_enabled=False,
            autocast_dtype="float32",
            variant="torch.float32",
            warnings=warnings,
        )

    variant = "torch.amp.bf16" if target == "bfloat16" else "torch.amp.fp16"
    return _PrecisionResolution(
        amp_enabled=True,
        autocast_dtype=target,
        variant=variant,
        warnings=warnings,
    )


@dataclass(frozen=True)
class TorchBiEncoderConfig:
    """Configuration for TorchBiEncoderRescorer."""

    model_id: str
    model_revision: str | None = None
    device: str = "auto"  # auto|cpu|cuda
    max_length: int = 256
    batch_size: int | None = None
    auto_batch: bool = True
    normalize_embeddings: bool = True
    similarity: str = "dot"  # dot|cosine
    query_prefix: str | None = None
    doc_prefix: str | None = None
    # Precision controls.
    #
    # The adapter keeps model weights in their default dtype (typically fp32)
    # and uses autocast to control compute precision on GPU.
    #
    # - torch_amp: enable autocast on CUDA.
    # - torch_dtype: float32|float16|bfloat16|auto.
    torch_amp: bool = False
    torch_dtype: str = "float32"


class TorchBiEncoderRescorer:
    """Bi-encoder rescoring backend using PyTorch + Transformers.

    Scores each candidate with a vector similarity between query embedding and document embedding.
    """

    def __init__(
        self,
        *,
        model_id: str,
        model_revision: str | None = None,
        device: str = "auto",
        max_length: int = 256,
        batch_size: int | None = None,
        auto_batch: bool = True,
        query_prefix: str | None = None,
        doc_prefix: str | None = None,
        normalize_embeddings: bool = True,
        similarity: str = "dot",
        torch_amp: bool = False,
        torch_dtype: str = "float32",
    ):
        cfg = TorchBiEncoderConfig(
            model_id=model_id,
            model_revision=model_revision,
            device=device,
            max_length=max_length,
            batch_size=batch_size,
            auto_batch=auto_batch,
            query_prefix=query_prefix,
            doc_prefix=doc_prefix,
            normalize_embeddings=normalize_embeddings,
            similarity=similarity,
            torch_amp=torch_amp,
            torch_dtype=torch_dtype,
        )
        if os.getenv("SKEINRANK_FORCE_NO_TORCH") == "1":
            raise ModelUnavailable(
                "torch backend disabled by SKEINRANK_FORCE_NO_TORCH=1; install skeinrank[torch]"
            )

        self._cfg = cfg

        try:
            import torch  # type: ignore
            from transformers import AutoModel, AutoTokenizer  # type: ignore
        except Exception as e:  # pragma: no cover
            raise ModelUnavailable(
                "Torch bi-encoder backend requires optional deps. Install: poetry install -E torch"
            ) from e

        self._torch = torch
        self._AutoTokenizer = AutoTokenizer
        self._AutoModel = AutoModel

        self._device = self._resolve_device(cfg.device)
        self._tokenizer = self._AutoTokenizer.from_pretrained(
            cfg.model_id, revision=cfg.model_revision
        )
        self._model = self._AutoModel.from_pretrained(
            cfg.model_id, revision=cfg.model_revision
        )
        self._model.eval()
        try:
            self._model.to(self._device)
        except Exception:
            # some stubs or CPU-only builds may not support .to(device)
            pass

        # Precision policy (used for passports and autocast).
        self.provider = "torch"
        cuda_available = False
        bf16_supported = False
        try:
            cuda_available = bool(torch.cuda.is_available())
        except Exception:
            cuda_available = False
        try:
            bf16_fn = getattr(torch.cuda, "is_bf16_supported", None)
            bf16_supported = (
                bool(bf16_fn()) if callable(bf16_fn) and cuda_available else False
            )
        except Exception:
            bf16_supported = False

        self._precision = resolve_torch_precision(
            device=self.resolved_device,
            amp=cfg.torch_amp,
            dtype=cfg.torch_dtype,
            cuda_available=cuda_available,
            bf16_supported=bf16_supported,
        )
        # Variant in passport reflects *compute* precision (autocast), not necessarily weights.
        self.variant = self._precision.variant
        # Warnings are stable per-engine configuration; we attach them to each request for observability.
        self._precision_warnings = list(self._precision.warnings)
        self.last_warnings: list[str] = []

        # If prefixes are not specified, apply sensible defaults for E5.
        if cfg.query_prefix is None and "e5-" in cfg.model_id:
            object.__setattr__(self._cfg, "query_prefix", "query: ")  # type: ignore
        if cfg.doc_prefix is None and "e5-" in cfg.model_id:
            object.__setattr__(self._cfg, "doc_prefix", "passage: ")  # type: ignore

    def runtime_meta(self) -> dict[str, Any]:
        torch = self._torch
        meta: dict[str, Any] = {}
        try:
            meta["torch_version"] = getattr(torch, "__version__", None)
        except Exception:
            meta["torch_version"] = None
        try:
            meta["cuda_available"] = bool(torch.cuda.is_available())
        except Exception:
            meta["cuda_available"] = False
        # Precision capabilities.
        try:
            meta["fp16_supported"] = bool(meta.get("cuda_available"))
        except Exception:
            meta["fp16_supported"] = False
        try:
            bf16_fn = getattr(torch.cuda, "is_bf16_supported", None)
            meta["bf16_supported"] = (
                bool(bf16_fn())
                if callable(bf16_fn) and meta.get("cuda_available")
                else False
            )
        except Exception:
            meta["bf16_supported"] = False
        try:
            if meta.get("cuda_available"):
                meta["gpu_name"] = torch.cuda.get_device_name(0)
            else:
                meta["gpu_name"] = None
        except Exception:
            meta["gpu_name"] = None
        return meta

    @property
    def resolved_device(self) -> str:
        """Resolved compute device used by the backend ("cpu" or "cuda")."""
        try:
            d = str(self._device)
        except Exception:
            d = "cpu"
        return "cuda" if "cuda" in d else "cpu"

    @property
    def resolved_variant(self) -> str | None:
        """Resolved model variant (e.g. dtype), if available."""
        return getattr(self, "variant", None)

    def warmup(self, query: str | None = None, docs: list[str] | None = None) -> None:
        """Warm caches/models.

        Contract: must be callable with *no arguments*.
        Some orchestrators (e.g., :class:`skeinrank.RerankEngine`) call ``warmup()``
        during init/first call without having a real request payload.

        Parameters
        ----------
        query:
            Optional query string. If not provided, a deterministic dummy query is used.
        docs:
            Optional list of document strings. If not provided, a deterministic dummy doc is used.
        """
        q = query if query is not None else "warmup query"
        doc_text = (docs[0] if docs else None) or "warmup doc"

        # One dry forward to initialize kernels/caches.
        _ = self.score(q, [Candidate(id="_warmup", text=doc_text)], batch_size=1)

    def score(
        self,
        query: str,
        candidates: list[Candidate],
        *,
        batch_size: int | None = None,
    ) -> dict[str, float]:
        cfg = self._cfg

        # Reset per-request warnings.
        self.last_warnings = list(
            getattr(
                self,
                "_precision",
                _PrecisionResolution(False, None, "torch.float32", []),
            ).warnings
        )

        if not candidates:
            return {}

        used_batch = self._resolve_batch_size(batch_size)
        # Exposed for passports/diagnostics.
        self.effective_batch_size = used_batch

        # Encode query once.
        q_text = self._apply_prefix(query, cfg.query_prefix)
        q_emb = self._encode_texts([q_text], used_batch=1)[0:1, :]

        # Encode docs in batches.
        ids = [c.id for c in candidates]
        texts = [self._apply_prefix(c.text, cfg.doc_prefix) for c in candidates]

        scores: dict[str, float] = {}
        for start in range(0, len(texts), used_batch):
            batch_texts = texts[start : start + used_batch]
            d_emb = self._encode_texts(batch_texts, used_batch=len(batch_texts))

            # Similarity: (B, D) @ (D, 1) -> (B,)
            sim = (d_emb @ q_emb.T).squeeze(-1)
            for j, s in enumerate(sim.tolist()):
                scores[ids[start + j]] = float(s)

        return scores

    def score_many(
        self,
        queries: list[str],
        candidates_list: list[list[Candidate]],
        *,
        batch_size: int | None = None,
    ) -> list[dict[str, float]]:
        """Score many (query, candidates) pairs in a single forward pass.

        This is designed for server-side micro-batching. It reduces Python overhead
        and improves GPU utilization by batching tokenization + model forward.
        """
        torch = self._torch
        cfg = self._cfg

        if len(queries) != len(candidates_list):
            raise ValueError("queries and candidates_list must have the same length")

        # Reset per-batch warnings.
        self.last_warnings = list(
            getattr(
                self,
                "_precision",
                _PrecisionResolution(False, None, "torch.float32", []),
            ).warnings
        )

        n_reqs = len(queries)
        if n_reqs == 0:
            return []

        used_batch = self._resolve_batch_size(batch_size)
        self.effective_batch_size = used_batch

        # Encode all queries (batched).
        q_texts = [self._apply_prefix(q, cfg.query_prefix) for q in queries]
        q_bs = min(len(q_texts), used_batch) if used_batch > 0 else 1
        q_emb = self._encode_texts(q_texts, used_batch=q_bs)  # (Q, D)

        # Flatten docs with a per-row query index.
        flat_ids: list[str] = []
        flat_texts: list[str] = []
        flat_qidx: list[int] = []
        sizes: list[int] = []

        for qi, cands in enumerate(candidates_list):
            sizes.append(len(cands))
            for c in cands:
                flat_ids.append(c.id)
                flat_texts.append(self._apply_prefix(c.text, cfg.doc_prefix))
                flat_qidx.append(qi)

        # Prepare per-request score dicts.
        out: list[dict[str, float]] = [dict() for _ in range(n_reqs)]
        if not flat_texts:
            return out

        # Encode docs in batches and compute row-wise similarity.
        for start in range(0, len(flat_texts), used_batch):
            batch_texts = flat_texts[start : start + used_batch]
            batch_qidx = flat_qidx[start : start + used_batch]
            batch_ids = flat_ids[start : start + used_batch]

            d_emb = self._encode_texts(
                batch_texts, used_batch=len(batch_texts)
            )  # (B, D)
            q_emb_b = q_emb[torch.tensor(batch_qidx, device=d_emb.device)]  # (B, D)
            sim = (d_emb * q_emb_b).sum(dim=-1)  # (B,)

            for j, s in enumerate(sim.tolist()):
                out[batch_qidx[j]][batch_ids[j]] = float(s)

        return out

    # ------------------------- internals -------------------------

    def _apply_prefix(self, text: str, prefix: str | None) -> str:
        if not prefix:
            return text
        return f"{prefix}{text}"

    def _resolve_device(self, device: str):
        torch = self._torch
        if device == "cuda":
            try:
                return (
                    torch.device("cuda")
                    if torch.cuda.is_available()
                    else torch.device("cpu")
                )
            except Exception:
                return "cpu"
        if device == "cpu":
            try:
                return torch.device("cpu")
            except Exception:
                return "cpu"
        # auto
        try:
            return (
                torch.device("cuda")
                if torch.cuda.is_available()
                else torch.device("cpu")
            )
        except Exception:
            return "cpu"

    def _resolve_batch_size(self, override: int | None) -> int:
        if override is not None:
            return max(1, int(override))

        if not self._cfg.auto_batch:
            # If auto batching is disabled but batch_size is omitted, fall back to a safe default.
            bs = self._cfg.batch_size if self._cfg.batch_size is not None else 32
            return max(1, int(bs))

        # Heuristic defaults: safe, not necessarily optimal. Override via API for benches.
        torch = self._torch
        try:
            if torch.cuda.is_available():
                return 64
        except Exception:
            pass
        return 16

    def _encode_texts(self, texts: list[str], used_batch: int):
        torch = self._torch
        cfg = self._cfg

        inputs = self._tokenizer(
            texts,
            padding=True,
            truncation=True,
            max_length=int(cfg.max_length),
            return_tensors="pt",
        )

        # Move to device if possible.
        try:
            inputs = {k: v.to(self._device) for k, v in inputs.items()}
        except Exception:
            pass

        with torch.no_grad():
            # Forward pass with optional autocast precision on CUDA.
            if (
                getattr(self, "_precision", None)
                and self._precision.amp_enabled
                and self.resolved_device == "cuda"
            ):
                autocast_dtype = None
                try:
                    if self._precision.autocast_dtype == "bfloat16":
                        autocast_dtype = torch.bfloat16
                    elif self._precision.autocast_dtype == "float16":
                        autocast_dtype = torch.float16
                except Exception:
                    autocast_dtype = None

                try:
                    with torch.autocast(
                        device_type="cuda", dtype=autocast_dtype, enabled=True
                    ):
                        out = self._model(**inputs)
                except Exception:
                    # Fallback: run without autocast.
                    out = self._model(**inputs)
            else:
                out = self._model(**inputs)

        last_hidden = getattr(out, "last_hidden_state", None)
        if last_hidden is None:
            # Some models may return a tuple.
            last_hidden = out[0]

        # Mean pooling with attention mask.
        mask = inputs.get("attention_mask")
        if mask is None:
            emb = last_hidden.mean(dim=1)
        else:
            mask = mask.unsqueeze(-1).to(last_hidden.dtype)
            summed = (last_hidden * mask).sum(dim=1)
            denom = mask.sum(dim=1).clamp(min=1e-9)
            emb = summed / denom

        if cfg.normalize_embeddings:
            emb = torch.nn.functional.normalize(emb, p=2, dim=1)

        if cfg.similarity not in {"dot", "cosine"}:
            raise ValueError(f"Unsupported similarity='{cfg.similarity}'")

        return emb
