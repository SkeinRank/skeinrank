"""Application-level orchestrator (public entrypoint).

This module defines :class:`~skeinrank.RerankEngine` and the convenience
functions :func:`~skeinrank.rerank` / :func:`~skeinrank.score`.

The implementation is intentionally small and dependency-free:
- strict contract validation
- stable I/O types
- request passport (optional)
- a built-in lightweight scorer so the package works out of the box
"""

from __future__ import annotations

import platform
import sys
import uuid
from time import perf_counter
from typing import Any, Sequence

from ..backends.device import DeviceResolution, resolve_device
from ..backends.registry import diagnose_backends, get_backend
from ..domain.errors import ContractError, ModelUnavailable
from ..domain.types import (
    Candidate,
    CandidateValidationSummary,
    InvalidCandidatePolicy,
    RankedItem,
    RequestPassport,
    RerankRequest,
    RerankResult,
    ScoreResult,
    SkippedCandidate,
    StageEvent,
)
from .passport_policy import (
    decide_effective_passport_level,
    resolve_requested_passport_level,
)
from .profiles import ProfileSpec, get_profile


def _runtime_info() -> dict:
    return {
        "python_version": sys.version.split(" ")[0],
        "platform": platform.platform(),
        "cuda_available": False,
        "gpu_name": None,
        "fp16_supported": False,
        "bf16_supported": False,
        "cuda_compute_capability": None,
    }


class RerankEngine:
    """Main entrypoint for library users.

    Parameters
    ----------
    profile:
        Built-in profile id (for example, "rerank_auto") or a ProfileSpec.
    device:
        Optional device override: "auto" | "cpu" | "cuda". If provided,
        it overrides the profile's device.
    """

    def __init__(
        self, profile: str | ProfileSpec = "rerank_auto", device: str | None = None
    ):
        self._profile = get_profile(profile) if isinstance(profile, str) else profile
        if device is not None:
            # Override requested device (validated and resolved below).
            self._profile = self._profile.model_copy(update={"device": device})

        # Resolve device preference to an actual device for this runtime.
        self._device_resolution = self._resolve_device()

        # Build scorer on the resolved device.
        self._scorer = self._build_scorer(
            self._profile, resolved_device=self._device_resolution.resolved
        )

        # Warmup policy.
        self._warmed_up = False
        if self._profile.warmup == "init":
            # Eager warmup (loads artifacts and runs a tiny forward pass).
            self._do_warmup()

    def _build_scorer(self, profile: ProfileSpec, *, resolved_device: str):
        # Resolve backend order: preferred_backends overrides backend field.
        backend_ids = (
            profile.preferred_backends
            if profile.preferred_backends
            else [profile.backend]
        )

        last_error: Exception | None = None
        for backend_id in backend_ids:
            backend = get_backend(backend_id)
            if not backend.is_available(device=resolved_device):
                diag = backend.diagnose(device=resolved_device)
                last_error = ModelUnavailable(
                    f"Backend '{backend_id}' is not available on this runtime: "
                    + "; ".join(diag.errors)
                )
                continue

            return backend.create_scorer(
                profile=profile, resolved_device=resolved_device
            )

        if last_error is not None:
            raise last_error
        raise ModelUnavailable("No available backend for the selected profile")

    def _maybe_warmup(
        self, *, stage_events: list[StageEvent], warmup: bool | None
    ) -> None:
        """Warmup policy resolver.

        warmup:
          - True  -> force warmup now
          - False -> skip warmup
          - None  -> follow profile.warmup policy
        """
        if warmup is False:
            return
        if warmup is True:
            self._do_warmup(stage_events=stage_events)
            return

        policy = getattr(self._profile, "warmup", "first_call")
        if policy == "none":
            return
        if policy == "init":
            # already done in __init__, but keep safe if engine was constructed with warmup disabled
            if not self._warmed_up:
                self._do_warmup(stage_events=stage_events)
            return

        # default: first_call
        self._do_warmup(stage_events=stage_events)

    def _do_warmup(self, stage_events: list[StageEvent] | None = None) -> None:
        """Warm caches/models (optional stage recording)."""
        if self._warmed_up:
            return
        if self._profile.backend == "builtin":
            self._warmed_up = True
            return

        t0 = perf_counter()
        try:
            warmup_fn = getattr(self._scorer, "warmup", None)
            if callable(warmup_fn):
                warmup_fn()
            else:
                # Fallback: tiny score call
                _ = self._scorer.score(
                    "warmup", [Candidate(id="_warmup", text="warmup")]
                )
        finally:
            self._warmed_up = True
            if stage_events is not None:
                stage_events.append(
                    StageEvent(
                        name="warmup",
                        elapsed_ms=(perf_counter() - t0) * 1000.0,
                        details={
                            "backend": self._profile.backend,
                            "device": getattr(self._scorer, "resolved_device", None)
                            or getattr(self._profile, "device", None),
                            "provider": getattr(self._scorer, "provider", None),
                            "variant": getattr(self._scorer, "variant", None),
                        },
                    )
                )

    @property
    def profile(self) -> ProfileSpec:
        return self._profile

    def diagnostics(self) -> dict[str, Any]:
        """Return runtime + backend diagnostics for troubleshooting."""
        return {
            "runtime": _runtime_info(),
            "backends": {k: v.__dict__ for k, v in diagnose_backends().items()},
            "profile_id": self._profile.id,
            "profile_backend": self._profile.backend,
            "profile_device": self._profile.device,
        }

    def _resolve_device(self) -> DeviceResolution:
        # Determine strict flag (keep backward compatibility with strict_cuda).
        strict = bool(
            getattr(self._profile, "strict_device", False)
            or getattr(self._profile, "strict_cuda", False)
        )

        # Device preference list for "auto".
        pref = getattr(self._profile, "device_preference", None) or ["cuda", "cpu"]

        # The dependency-free core scorer is CPU-backed. Keep the device resolver
        # path active so CUDA requests still produce a clear fallback warning.
        cuda_available = False

        return resolve_device(
            requested=self._profile.device,
            device_preference=list(pref),
            cuda_available=cuda_available,
            strict_cuda=strict,
        )

    def rerank(
        self,
        query: str,
        candidates: Sequence[Candidate | dict[str, Any]],
        *,
        top_k: int = 20,
        debug: bool = False,
        passport: str | None = None,
        invalid_candidate_policy: str
        | InvalidCandidatePolicy = InvalidCandidatePolicy.ERROR,
        deadline_ms: float | None = None,
        batch_size: int | None = None,
        warmup: bool | None = None,
    ) -> RerankResult:
        """Rerank candidates for a query."""
        stage_events: list[StageEvent] = []

        requested_level = resolve_requested_passport_level(
            passport=passport, debug=debug
        )

        q = self._validate_query(query)
        cands, warnings, validation_summary = self._validate_candidates(
            candidates, invalid_candidate_policy=invalid_candidate_policy
        )
        if len(cands) == 0:
            if validation_summary is not None:
                raise ContractError(
                    "candidates must contain at least one candidate with non-empty text after validation"
                )
            raise ContractError("candidates must be a non-empty sequence")

        if top_k <= 0:
            raise ContractError("top_k must be > 0")

        # Optional warmup (only once per engine).
        self._maybe_warmup(stage_events=stage_events, warmup=warmup)

        # Stage: scoring
        # Custom scorers may provide fine-grained stage breakdown via
        # `score_with_stages(...)`. We call it whenever available so summary/debug
        # passports can reliably include stage names.
        score_with_stages = getattr(self._scorer, "score_with_stages", None)
        if callable(score_with_stages):
            scores, extra_stages = score_with_stages(q, cands, batch_size=batch_size)
            stage_events.extend(list(extra_stages or []))
        else:
            t_stage = perf_counter()
            scores = self._scorer.score(q, cands, batch_size=batch_size)
            stage_events.append(
                StageEvent(
                    name="score",
                    elapsed_ms=(perf_counter() - t_stage) * 1000.0,
                    details={
                        "backend": self._profile.backend,
                        "device": getattr(self._scorer, "resolved_device", "cpu"),
                        "provider": getattr(self._scorer, "provider", None),
                        "batch_size": getattr(
                            self._scorer,
                            "effective_batch_size",
                            getattr(self._scorer, "batch_size", None),
                        ),
                    },
                )
            )

        # Stage: sort
        t_stage = perf_counter()
        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
        ranked = ranked[: min(top_k, len(ranked))]
        out = [
            RankedItem(id=doc_id, score=float(score), rank=i + 1)
            for i, (doc_id, score) in enumerate(ranked)
        ]
        stage_events.append(
            StageEvent(name="sort", elapsed_ms=(perf_counter() - t_stage) * 1000.0)
        )

        passport_obj = None
        runtime_warnings = list(warnings) + list(
            getattr(self._scorer, "last_warnings", [])
        )
        # Include device-level fallbacks in the warning stream so policy triggers
        # (e.g., DEBUG_ON_WARNINGS) can capture degraded-mode events.
        if (
            getattr(self, "_device_resolution", None) is not None
            and self._device_resolution.fallback
        ):
            runtime_warnings.append("device_fallback: cuda -> cpu")

        # Soft latency policy: if a deadline was set, emit a warning when exceeded.
        deadline = (
            deadline_ms if deadline_ms is not None else self._profile.soft_deadline_ms
        )
        if deadline is not None:
            total_ms = sum(s.elapsed_ms for s in stage_events)
            if total_ms > float(deadline):
                runtime_warnings.append(
                    f"soft_deadline_ms exceeded (deadline={float(deadline):.2f}ms, elapsed={total_ms:.2f}ms)"
                )

        total_ms = float(sum(s.elapsed_ms for s in stage_events))
        decision = decide_effective_passport_level(
            requested=requested_level,
            warnings=runtime_warnings,
            total_ms=total_ms,
        )

        if decision.effective != "off":
            stage_events_out = stage_events
            if decision.effective == "summary":
                stage_events_out = [
                    s.model_copy(update={"details": {}}) for s in stage_events
                ]

            passport_obj = self._make_passport(
                passport_level=decision.effective,
                reason_details=(
                    decision.reason_details if decision.effective == "debug" else None
                ),
                stage_events=stage_events_out,
                warnings=runtime_warnings,
                passport_upgraded_by=decision.passport_upgraded_by,
                resolved_device=getattr(self._scorer, "resolved_device", "cpu"),
                provider=getattr(self._scorer, "provider", None),
                variant=getattr(self._scorer, "resolved_variant", None),
            )

        return RerankResult(
            query=q,
            ranked=out,
            passport=passport_obj,
            candidate_validation=validation_summary,
        )

    def rerank_many(
        self,
        requests: Sequence[RerankRequest | dict[str, Any]],
        *,
        top_k: int = 10,
        passport: str | None = None,
        debug: bool = False,
        invalid_candidate_policy: str
        | InvalidCandidatePolicy = InvalidCandidatePolicy.ERROR,
        warmup: bool = True,
        batch_size: int | None = None,
        deadline_ms: float | None = None,
    ) -> list[RerankResult]:
        """Rerank a batch of requests.

        If the underlying scorer implements ``score_many()``, SkeinRank will use it to score
        the whole batch in a single model forward pass (useful for server micro-batching).
        Otherwise it falls back to per-request scoring.
        """
        requested_level = resolve_requested_passport_level(
            passport=passport, debug=debug
        )

        if not isinstance(requests, Sequence):
            raise TypeError("requests must be a sequence of RerankRequest or dict")

        if len(requests) == 0:
            return []

        parsed: list[RerankRequest] = []
        for r in requests:
            if isinstance(r, RerankRequest):
                parsed.append(r)
            elif isinstance(r, dict):
                parsed.append(RerankRequest(**r))
            else:
                raise TypeError("each request must be a RerankRequest or dict")

        # Validate + normalize requests.
        queries: list[str] = []
        cands_list: list[list[Candidate]] = []
        topks: list[int] = []
        runtime_warnings_list: list[list[str]] = []
        validation_summaries: list[CandidateValidationSummary | None] = []
        stage_events_list: list[list[StageEvent]] = [[] for _ in parsed]

        for r in parsed:
            q = self._validate_query(r.query)

            k = int(r.top_k) if r.top_k is not None else int(top_k)
            if k <= 0:
                raise ContractError("top_k must be >= 1")

            cands, w, validation_summary = self._validate_candidates(
                r.candidates, invalid_candidate_policy=invalid_candidate_policy
            )
            if len(cands) == 0:
                raise ContractError(
                    "candidates must contain at least one candidate with non-empty text after validation"
                )
            queries.append(q)
            cands_list.append(cands)
            topks.append(k)
            runtime_warnings_list.append(list(w))
            validation_summaries.append(validation_summary)

        # Shared warmup once.
        warmup_ms_total = 0.0
        warmup_details: dict[str, Any] = {}
        if warmup:
            warmup_events: list[StageEvent] = []
            self._maybe_warmup(stage_events=warmup_events, warmup=warmup)
            if warmup_events:
                warmup_ms_total = float(warmup_events[-1].elapsed_ms)
                warmup_details = dict(warmup_events[-1].details)

        # Decide scoring strategy.
        use_score_many = hasattr(self._scorer, "score_many") and callable(
            getattr(self._scorer, "score_many")
        )
        scores_list: list[dict[str, float]] = []
        score_ms_total = 0.0

        score_details_base: dict[str, Any] = {
            "backend": self._profile.backend,
            "device": getattr(self._scorer, "resolved_device", "cpu"),
        }

        if use_score_many:
            t0 = perf_counter()
            scores_list = getattr(self._scorer, "score_many")(
                queries, cands_list, batch_size=batch_size
            )
            t1 = perf_counter()
            score_ms_total = (t1 - t0) * 1000.0

            score_details_base["batch_size"] = getattr(
                self._scorer, "effective_batch_size", batch_size
            )
            score_details_base["microbatch"] = True
            score_details_base["microbatch_size"] = len(parsed)
            score_details_base["microbatch_total_candidates"] = int(
                sum(len(c) for c in cands_list)
            )

            # Shared scorer warnings.
            scorer_warnings = list(getattr(self._scorer, "last_warnings", []) or [])
            if scorer_warnings:
                for w in runtime_warnings_list:
                    w.extend(scorer_warnings)

            # Allocate shared score time by candidate count.
            total_cands = max(int(sum(len(c) for c in cands_list)), 1)
            for i, cands in enumerate(cands_list):
                alloc = score_ms_total * (len(cands) / total_cands)
                details = dict(score_details_base)
                details["candidates_in"] = int(len(cands))
                stage_events_list[i].append(
                    StageEvent(name="score", elapsed_ms=float(alloc), details=details)
                )

        else:
            # Accurate per-request scoring.
            for i, (q, cands) in enumerate(zip(queries, cands_list)):
                t0 = perf_counter()
                scores = self._scorer.score(q, cands, batch_size=batch_size)
                t1 = perf_counter()
                scores_list.append(scores)

                details = dict(score_details_base)
                details["batch_size"] = getattr(
                    self._scorer, "effective_batch_size", batch_size
                )
                stage_events_list[i].append(
                    StageEvent(
                        name="score",
                        elapsed_ms=float((t1 - t0) * 1000.0),
                        details=details,
                    )
                )

                scorer_warnings = list(getattr(self._scorer, "last_warnings", []) or [])
                if scorer_warnings:
                    runtime_warnings_list[i].extend(scorer_warnings)

        # Allocate shared warmup time by candidate count.
        if warmup_ms_total > 0.0:
            total_cands = max(int(sum(len(c) for c in cands_list)), 1)
            for i, cands in enumerate(cands_list):
                alloc = warmup_ms_total * (len(cands) / total_cands)
                details = dict(warmup_details)
                details.update(
                    {"microbatch": True, "microbatch_size": len(parsed), "shared": True}
                )
                stage_events_list[i].insert(
                    0,
                    StageEvent(name="warmup", elapsed_ms=float(alloc), details=details),
                )

        # Build outputs.
        results: list[RerankResult] = []
        for i, (q, scores, k) in enumerate(zip(queries, scores_list, topks)):
            runtime_warnings = runtime_warnings_list[i]
            stage_events = stage_events_list[i]

            # Sort.
            t0_sort = perf_counter()
            ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
            ranked = ranked[: min(k, len(ranked))]
            out = [
                RankedItem(id=doc_id, score=float(score), rank=i + 1)
                for i, (doc_id, score) in enumerate(ranked)
            ]
            t1_sort = perf_counter()
            stage_events.append(
                StageEvent(
                    name="sort",
                    elapsed_ms=float((t1_sort - t0_sort) * 1000.0),
                    details={},
                )
            )

            # Soft deadline warning.
            deadline = (
                float(deadline_ms)
                if deadline_ms is not None
                else float(self._profile.soft_deadline_ms or 0.0)
            )
            if deadline > 0.0:
                total_ms_est = float(sum(s.elapsed_ms for s in stage_events))
                if total_ms_est > deadline:
                    runtime_warnings.append(
                        f"soft_deadline_ms exceeded (deadline={deadline:.2f}ms, elapsed={total_ms_est:.2f}ms)"
                    )

            total_ms = float(sum(s.elapsed_ms for s in stage_events))
            decision = decide_effective_passport_level(
                requested=requested_level,
                warnings=runtime_warnings,
                total_ms=total_ms,
            )

            passport_obj: RequestPassport | None = None
            if decision.effective != "off":
                stage_events_out = stage_events
                if decision.effective == "summary":
                    stage_events_out = [
                        s.model_copy(update={"details": {}}) for s in stage_events
                    ]

                passport_obj = self._make_passport(
                    passport_level=decision.effective,
                    reason_details=(
                        decision.reason_details
                        if decision.effective == "debug"
                        else None
                    ),
                    stage_events=stage_events_out,
                    warnings=runtime_warnings,
                    passport_upgraded_by=decision.passport_upgraded_by,
                    resolved_device=getattr(self._scorer, "resolved_device", "cpu"),
                    provider=getattr(self._scorer, "provider", None),
                    variant=getattr(self._scorer, "resolved_variant", None),
                )

            results.append(
                RerankResult(
                    query=q,
                    ranked=out,
                    passport=passport_obj,
                    candidate_validation=validation_summaries[i],
                )
            )

        return results

    def score(
        self,
        query: str,
        candidates: Sequence[Candidate | dict[str, Any]],
        *,
        debug: bool = False,
        passport: str | None = None,
        invalid_candidate_policy: str
        | InvalidCandidatePolicy = InvalidCandidatePolicy.ERROR,
        deadline_ms: float | None = None,
        batch_size: int | None = None,
        warmup: bool | None = None,
    ) -> ScoreResult:
        """Score candidates for a query without sorting."""
        stage_events: list[StageEvent] = []
        requested_level = resolve_requested_passport_level(
            passport=passport, debug=debug
        )
        q = self._validate_query(query)
        cands, warnings, validation_summary = self._validate_candidates(
            candidates, invalid_candidate_policy=invalid_candidate_policy
        )
        if len(cands) == 0:
            if validation_summary is not None:
                raise ContractError(
                    "candidates must contain at least one candidate with non-empty text after validation"
                )
            raise ContractError("candidates must be a non-empty sequence")

        # Optional warmup (only once per engine).
        self._maybe_warmup(stage_events=stage_events, warmup=warmup)

        score_with_stages = getattr(self._scorer, "score_with_stages", None)
        if callable(score_with_stages):
            scores, extra_stages = score_with_stages(q, cands, batch_size=batch_size)
            stage_events.extend(list(extra_stages or []))
        else:
            t_stage = perf_counter()
            scores = self._scorer.score(q, cands, batch_size=batch_size)
            stage_events.append(
                StageEvent(
                    name="score",
                    elapsed_ms=(perf_counter() - t_stage) * 1000.0,
                    details={
                        "backend": self._profile.backend,
                        "device": getattr(self._scorer, "resolved_device", "cpu"),
                        "provider": getattr(self._scorer, "provider", None),
                        "batch_size": getattr(
                            self._scorer,
                            "effective_batch_size",
                            getattr(self._scorer, "batch_size", None),
                        ),
                    },
                )
            )

        passport_obj = None
        runtime_warnings = list(warnings) + list(
            getattr(self._scorer, "last_warnings", [])
        )
        # Include device-level fallbacks in the warning stream so policy triggers
        # (e.g., DEBUG_ON_WARNINGS) can capture degraded-mode events.
        if (
            getattr(self, "_device_resolution", None) is not None
            and self._device_resolution.fallback
        ):
            runtime_warnings.append("device_fallback: cuda -> cpu")

        # Soft latency policy: warn (do not fail) if total time exceeds deadline.
        deadline = (
            deadline_ms if deadline_ms is not None else self._profile.soft_deadline_ms
        )
        if deadline is not None:
            total_ms = sum(s.elapsed_ms for s in stage_events)
            if total_ms > deadline:
                runtime_warnings.append(
                    f"soft_deadline_ms exceeded: deadline={deadline:.2f}ms, elapsed={total_ms:.2f}ms"
                )

        total_ms = float(sum(s.elapsed_ms for s in stage_events))
        decision = decide_effective_passport_level(
            requested=requested_level,
            warnings=runtime_warnings,
            total_ms=total_ms,
        )

        if decision.effective != "off":
            stage_events_out = stage_events
            if decision.effective == "summary":
                stage_events_out = [
                    s.model_copy(update={"details": {}}) for s in stage_events
                ]
            passport_obj = self._make_passport(
                passport_level=decision.effective,
                reason_details=(
                    decision.reason_details if decision.effective == "debug" else None
                ),
                stage_events=stage_events_out,
                warnings=runtime_warnings,
                passport_upgraded_by=decision.passport_upgraded_by,
                resolved_device=getattr(self._scorer, "resolved_device", "cpu"),
                provider=getattr(self._scorer, "provider", None),
                variant=getattr(self._scorer, "resolved_variant", None),
            )

        return ScoreResult(
            query=q,
            scores={k: float(v) for k, v in scores.items()},
            passport=passport_obj,
            candidate_validation=validation_summary,
        )

    def _validate_query(self, query: Any) -> str:
        if not isinstance(query, str):
            raise ContractError("query must be a string")
        q = query.strip()
        if not q:
            raise ContractError("query must be a non-empty string")
        return q

    def _validate_candidates(
        self,
        candidates: Sequence[Candidate | dict[str, Any]],
        *,
        invalid_candidate_policy: str | InvalidCandidatePolicy,
    ) -> tuple[
        list[Candidate],
        list[str],
        CandidateValidationSummary | None,
    ]:
        if candidates is None:
            raise ContractError("candidates must be provided")

        if not isinstance(candidates, Sequence):
            raise ContractError("candidates must be a sequence")

        if len(candidates) > self._profile.max_candidates:
            raise ContractError(
                f"too many candidates: {len(candidates)} (max_candidates={self._profile.max_candidates})"
            )

        policy = _normalize_invalid_candidate_policy(invalid_candidate_policy)
        out: list[Candidate] = []
        warnings: list[str] = []
        skipped: list[SkippedCandidate] = []
        for i, c in enumerate(candidates):
            try:
                cand = c if isinstance(c, Candidate) else Candidate.model_validate(c)
            except Exception as e:  # noqa: BLE001
                raise ContractError(f"invalid candidate at index {i}: {e}") from e

            if not cand.id:
                raise ContractError(f"candidate.id must be non-empty (index {i})")
            if not cand.text or not cand.text.strip():
                if policy == InvalidCandidatePolicy.SKIP_EMPTY_TEXT:
                    skipped.append(
                        SkippedCandidate(
                            index=i,
                            id=cand.id,
                            code="empty_text",
                            message="Candidate text is empty and was skipped.",
                        )
                    )
                    warnings.append(
                        f"candidate_skipped: empty_text (id={cand.id}, index={i})"
                    )
                    continue
                raise ContractError(f"candidate.text must be non-empty (id={cand.id})")

            if len(cand.text) > self._profile.max_text_chars:
                warnings.append(
                    f"candidate text truncated (id={cand.id}, chars={len(cand.text)} -> {self._profile.max_text_chars})"
                )
                cand = cand.model_copy(
                    update={"text": cand.text[: self._profile.max_text_chars]}
                )

            out.append(cand)

        validation_summary: CandidateValidationSummary | None = None
        if policy != InvalidCandidatePolicy.ERROR:
            validation_summary = CandidateValidationSummary(
                policy=policy,
                input_count=len(candidates),
                accepted_count=len(out),
                skipped_count=len(skipped),
                skipped_by_reason={"empty_text": len(skipped)} if skipped else {},
                skipped_candidates=skipped,
            )

        return out, warnings, validation_summary

    def _make_passport(
        self,
        *,
        passport_level: str,
        reason_details: dict[str, Any] | None,
        stage_events: list[StageEvent],
        warnings: list[str],
        passport_upgraded_by: list[str],
        resolved_device: str,
        provider: str | None,
        variant: str | None,
    ) -> RequestPassport:
        # Validate and normalize device.
        if resolved_device not in {"cpu", "cuda"}:
            # keep it simple for v0.0.x
            resolved_device = "cpu"

        # "Golden" audit fields (minimal, stable):
        # - request_id to correlate logs
        # - runtime snapshot for incident investigations
        # - total_ms as a convenient aggregate
        request_id = str(uuid.uuid4())
        runtime = _runtime_info()  # pydantic will coerce into RequestRuntime
        total_ms = float(sum(s.elapsed_ms for s in stage_events))

        return RequestPassport(
            passport_level=passport_level,
            passport_upgraded_by=passport_upgraded_by,
            reason_details=reason_details if passport_level == "debug" else None,
            request_id=request_id,
            runtime=runtime,
            total_ms=total_ms,
            profile_id=self._profile.id,
            profile_hash=self._profile.stable_hash(),
            device=resolved_device,
            backend=self._profile.backend,
            provider=provider,
            variant=variant,
            model_id=self._profile.model_id,
            model_revision=self._profile.model_revision,
            stages=stage_events,
            warnings=warnings,
        )


def _normalize_invalid_candidate_policy(
    value: str | InvalidCandidatePolicy,
) -> InvalidCandidatePolicy:
    if isinstance(value, InvalidCandidatePolicy):
        return value
    try:
        return InvalidCandidatePolicy(str(value).strip().lower())
    except ValueError as exc:
        allowed = ", ".join(policy.value for policy in InvalidCandidatePolicy)
        raise ContractError(
            f"invalid_candidate_policy must be one of: {allowed}"
        ) from exc


def rerank(
    query: str,
    candidates: Sequence[Candidate | dict[str, Any]],
    *,
    top_k: int = 20,
    profile: str | ProfileSpec = "rerank_auto",
    device: str | None = None,
    debug: bool = False,
    passport: str | None = None,
    invalid_candidate_policy: str
    | InvalidCandidatePolicy = InvalidCandidatePolicy.ERROR,
    deadline_ms: float | None = None,
) -> RerankResult:
    """Convenience function for one-off reranking."""
    return RerankEngine(profile=profile, device=device).rerank(
        query,
        candidates,
        top_k=top_k,
        debug=debug,
        passport=passport,
        invalid_candidate_policy=invalid_candidate_policy,
        deadline_ms=deadline_ms,
    )


def rerank_many(
    requests: Sequence[RerankRequest | dict[str, Any]],
    *,
    top_k: int = 20,
    profile: str | ProfileSpec = "rerank_auto",
    device: str | None = None,
    debug: bool = False,
    passport: str | None = None,
    invalid_candidate_policy: str
    | InvalidCandidatePolicy = InvalidCandidatePolicy.ERROR,
    deadline_ms: float | None = None,
    batch_size: int | None = None,
    warmup: bool = True,
) -> list[RerankResult]:
    """Convenience function for batch reranking.

    See :meth:`~skeinrank.app.engine.RerankEngine.rerank_many`.
    """
    return RerankEngine(profile=profile, device=device).rerank_many(
        requests,
        top_k=top_k,
        debug=debug,
        passport=passport,
        invalid_candidate_policy=invalid_candidate_policy,
        deadline_ms=deadline_ms,
        batch_size=batch_size,
        warmup=warmup,
    )


def score(
    query: str,
    candidates: Sequence[Candidate | dict[str, Any]],
    *,
    profile: str | ProfileSpec = "rerank_auto",
    device: str | None = None,
    debug: bool = False,
    passport: str | None = None,
    invalid_candidate_policy: str
    | InvalidCandidatePolicy = InvalidCandidatePolicy.ERROR,
    deadline_ms: float | None = None,
) -> ScoreResult:
    """Convenience function for one-off scoring."""
    return RerankEngine(profile=profile, device=device).score(
        query,
        candidates,
        debug=debug,
        passport=passport,
        invalid_candidate_policy=invalid_candidate_policy,
        deadline_ms=deadline_ms,
    )
