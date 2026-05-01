"""Cascade (multi-stage) scorer.

This scorer implements a simple and highly effective product-grade pattern:

1) Run a fast reranker on all candidates.
2) Select the top-M candidates.
3) Run a higher-quality reranker only on that top-M subset.

The final ranking is produced from stage2 scores, while candidates outside top-M
are kept with a very low score so they can never enter top_k.

The scorer exposes `score_with_stages(...)` so the engine can record separate
passport stages in debug mode.
"""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Any

from skeinrank.domain.types import Candidate, StageEvent

_VERY_LOW_SCORE = -1e9


def _truncate_text(text: str, *, max_len: int = 256) -> str:
    """Truncate text for safe structured logging.

    Keep warnings short and machine-parsable; detailed reasons belong in
    debug-only stage details.
    """
    s = "" if text is None else str(text)
    if max_len <= 0:
        return ""
    if len(s) <= max_len:
        return s
    if max_len <= 3:
        return s[:max_len]
    return s[: max_len - 3] + "..."


def _safe_getattr(obj: Any, name: str, default: Any = None) -> Any:
    try:
        return getattr(obj, name)
    except Exception:
        return default


@dataclass
class _StageInfo:
    name: str
    scorer: Any | None
    model_id: str | None


class CascadeScorer:
    """Two-stage cascade scorer."""

    provider = "cascade"

    def __init__(
        self,
        *,
        stage1_scorer: Any,
        stage2_scorer: Any | None,
        stage1_profile_id: str,
        stage2_profile_id: str,
        top_m: int,
        resolved_device: str,
        stage2_unavailable_reason: str | None = None,
    ) -> None:
        self._stage1 = _StageInfo(
            name="score_fast",
            scorer=stage1_scorer,
            model_id=_safe_getattr(stage1_scorer, "model_id"),
        )
        self._stage2 = _StageInfo(
            name="score_quality",
            scorer=stage2_scorer,
            model_id=_safe_getattr(stage2_scorer, "model_id"),
        )

        self.stage1_profile_id = stage1_profile_id
        self.stage2_profile_id = stage2_profile_id
        self.top_m = int(top_m)
        self.resolved_device = resolved_device
        self.resolved_variant = "cascade"

        self._stage2_unavailable_reason = stage2_unavailable_reason

        # Per-request warnings emitted by the scorer.
        self.last_warnings: list[str] = []

    def warmup(self) -> None:
        """Warm both stages (best-effort)."""
        self.last_warnings = []
        for st in (self._stage1, self._stage2):
            if st.scorer is None:
                continue
            fn = _safe_getattr(st.scorer, "warmup")
            if callable(fn):
                try:
                    # Some adapters implement warmup(query, docs), others warmup().
                    fn()  # type: ignore[misc]
                except TypeError:
                    # Best-effort fallback: tiny score call handled by engine.
                    pass

    def score(
        self, query: str, candidates: list[Candidate], *, batch_size: int | None = None
    ) -> dict[str, float]:
        scores, _ = self._score_internal(
            query, candidates, batch_size=batch_size, with_stages=False
        )
        return scores

    def score_with_stages(
        self, query: str, candidates: list[Candidate], *, batch_size: int | None = None
    ) -> tuple[dict[str, float], list[StageEvent]]:
        return self._score_internal(
            query, candidates, batch_size=batch_size, with_stages=True
        )

    def _score_internal(
        self,
        query: str,
        candidates: list[Candidate],
        *,
        batch_size: int | None,
        with_stages: bool,
    ) -> tuple[dict[str, float], list[StageEvent]]:
        self.last_warnings = []
        stage_events: list[StageEvent] = []

        # Stage 1: fast
        t0 = perf_counter()
        s1 = self._stage1.scorer.score(query, candidates, batch_size=batch_size)
        t1_ms = (perf_counter() - t0) * 1000.0

        # Propagate adapter warnings if present.
        self.last_warnings.extend(
            list(_safe_getattr(self._stage1.scorer, "last_warnings", []) or [])
        )

        # Pick top-M by stage1 scores.
        # Keep stable selection based on score desc then id.
        ranked1 = sorted(s1.items(), key=lambda kv: (kv[1], kv[0]), reverse=True)
        top_m = min(self.top_m, len(ranked1))
        top_ids = {doc_id for doc_id, _ in ranked1[:top_m]}
        subset = [c for c in candidates if c.id in top_ids]

        if with_stages:
            stage_events.append(
                StageEvent(
                    name=self._stage1.name,
                    elapsed_ms=t1_ms,
                    details={
                        "backend": _safe_getattr(
                            self._stage1.scorer, "backend", "torch_bi_encoder"
                        ),
                        "provider": _safe_getattr(
                            self._stage1.scorer, "provider", None
                        ),
                        "device": _safe_getattr(
                            self._stage1.scorer, "resolved_device", self.resolved_device
                        ),
                        "batch_size": _safe_getattr(
                            self._stage1.scorer,
                            "effective_batch_size",
                            _safe_getattr(self._stage1.scorer, "batch_size", None),
                        ),
                        "profile_id": self.stage1_profile_id,
                        "top_m": self.top_m,
                        "candidates_in": len(candidates),
                        "candidates_out": len(subset),
                    },
                )
            )

        # Stage 2: quality (best-effort)
        # If stage2 couldn't be constructed during engine init (or was explicitly
        # marked as unavailable), skip it and fall back to stage1.
        if self._stage2_unavailable_reason is not None or self._stage2.scorer is None:
            reason = self._stage2_unavailable_reason or "unavailable"
            # Keep warnings short and stable for metrics/alerting.
            self.last_warnings.append("cascade_fallback:stage2_unavailable")

            # Fallback: return stage1 scores.
            if with_stages:
                stage_events.append(
                    StageEvent(
                        name=self._stage2.name,
                        elapsed_ms=0.0,
                        details={
                            "skipped": True,
                            "skip_reason": "stage2_unavailable",
                            "unavailable_reason": _truncate_text(reason),
                            "profile_id": self.stage2_profile_id,
                        },
                    )
                )
            return s1, stage_events

        try:
            t0 = perf_counter()
            s2 = self._stage2.scorer.score(query, subset, batch_size=batch_size)
            t2_ms = (perf_counter() - t0) * 1000.0
            self.last_warnings.extend(
                list(_safe_getattr(self._stage2.scorer, "last_warnings", []) or [])
            )

            if with_stages:
                stage_events.append(
                    StageEvent(
                        name=self._stage2.name,
                        elapsed_ms=t2_ms,
                        details={
                            "backend": _safe_getattr(
                                self._stage2.scorer, "backend", "torch_bi_encoder"
                            ),
                            "provider": _safe_getattr(
                                self._stage2.scorer, "provider", None
                            ),
                            "device": _safe_getattr(
                                self._stage2.scorer,
                                "resolved_device",
                                self.resolved_device,
                            ),
                            "batch_size": _safe_getattr(
                                self._stage2.scorer,
                                "effective_batch_size",
                                _safe_getattr(self._stage2.scorer, "batch_size", None),
                            ),
                            "profile_id": self.stage2_profile_id,
                            "candidates_in": len(subset),
                        },
                    )
                )
        except Exception as e:  # noqa: BLE001
            # Robust fallback: any stage2 failure returns stage1 output.
            # Keep warnings short and stable for metrics/alerting.
            self.last_warnings.append("cascade_fallback:stage2_error")
            if with_stages:
                stage_events.append(
                    StageEvent(
                        name=self._stage2.name,
                        elapsed_ms=0.0,
                        details={
                            "skipped": True,
                            "skip_reason": "stage2_error",
                            "error_type": type(e).__name__,
                            "error_msg": _truncate_text(str(e)),
                            "profile_id": self.stage2_profile_id,
                        },
                    )
                )
            return s1, stage_events

        # Final scores: keep stage1 scores for all candidates, override with stage2
        # on the selected subset. This preserves correct behavior even when callers
        # request top_k > top_m, and provides a sensible ranking for the tail.
        final_scores: dict[str, float] = {
            doc_id: float(score) for doc_id, score in s1.items()
        }
        for doc_id, score in s2.items():
            final_scores[doc_id] = float(score)
        return final_scores, stage_events
