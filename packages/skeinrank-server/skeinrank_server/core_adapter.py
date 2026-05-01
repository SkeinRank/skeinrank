from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from .errors import CoreUnavailable


@dataclass
class CoreOutput:
    ranked: list[dict[str, Any]]
    passport: Optional[dict[str, Any]]


@dataclass
class AttributeCoreOutput:
    profile_id: str
    attributes: list[dict[str, Any]]
    passport: Optional[dict[str, Any]]


class CoreAdapter:
    """Lazy wrapper around skeinrank-core."""

    def __init__(self) -> None:
        try:
            from skeinrank import (  # type: ignore
                Candidate,
                RerankEngine,
                extract_attributes,
            )
        except Exception as e:
            raise CoreUnavailable(
                f"skeinrank-core is not available: {type(e).__name__}: {e}"
            ) from e
        self._RerankEngine = RerankEngine
        self._Candidate = Candidate
        self._extract_attributes = extract_attributes

    def rerank(
        self,
        *,
        profile: str,
        query: str,
        candidates: list[dict[str, Any]],
        top_k: int,
        passport: str,
        warmup: bool = False,
        batch_size: int | None = None,
    ) -> CoreOutput:
        engine = self._RerankEngine(profile=profile)
        cands = [
            self._Candidate(id=str(c["id"]), text=str(c["text"])) for c in candidates
        ]
        out = engine.rerank(
            query,
            cands,
            top_k=int(top_k),
            warmup=bool(warmup),
            passport=passport,
            batch_size=batch_size,
        )
        ranked = [{"id": r.id, "score": float(r.score)} for r in out.ranked]
        passport_obj = None
        if getattr(out, "passport", None) is not None:
            passport_obj = out.passport.model_dump()
        return CoreOutput(ranked=ranked, passport=passport_obj)

    def extract_attributes(
        self,
        *,
        text: str,
        profile: str,
        debug: bool = False,
        use_gliner: bool | None = None,
        use_e5: bool | None = None,
        use_keybert: bool | None = None,
    ) -> AttributeCoreOutput:
        out = self._extract_attributes(
            text,
            profile=profile,
            debug=debug,
            use_gliner=use_gliner,
            use_e5=use_e5,
            use_keybert=use_keybert,
        )
        passport_obj = (
            out.passport.model_dump(mode="json") if out.passport is not None else None
        )
        if passport_obj is not None and not passport_obj.get("stage_status"):
            passport_obj.pop("stage_status", None)
        return AttributeCoreOutput(
            profile_id=str(out.profile_id),
            attributes=[item.model_dump(mode="json") for item in out.attributes],
            passport=passport_obj,
        )

    def diagnostics(self) -> dict[str, Any]:
        engine = self._RerankEngine(profile="e5_fast_torch")
        return engine.diagnostics()
