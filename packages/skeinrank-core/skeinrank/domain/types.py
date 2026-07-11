"""Stable data contracts.

These models define the public, stable input/output formats for SkeinRank.

Design goals:
- minimal, universal, library-first
- JSON-serializable (via Pydantic)
- future-proof (schema versioning)
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, model_serializer

SCHEMA_VERSION = "1"


class RequestRuntime(BaseModel):
    """Execution environment metadata for audit/debug."""

    python_version: str
    platform: str
    onnxruntime_version: Optional[str] = None
    torch_version: Optional[str] = None
    cuda_available: Optional[bool] = None
    gpu_name: Optional[str] = None


class Candidate(BaseModel):
    """A document candidate to rerank."""

    model_config = ConfigDict(extra="allow")

    id: str = Field(..., description="Candidate identifier")
    text: str = Field(..., description="Candidate text content")
    metadata: dict[str, Any] | None = Field(
        default=None, description="Optional metadata"
    )


class InvalidCandidatePolicy(str, Enum):
    """Validation policy for malformed rerank candidates."""

    ERROR = "error"
    SKIP_EMPTY_TEXT = "skip_empty_text"


class SkippedCandidate(BaseModel):
    """One candidate omitted by an explicit validation policy."""

    index: int = Field(ge=0)
    id: str
    code: str = "empty_text"
    message: str = "Candidate text is empty."


class CandidateValidationSummary(BaseModel):
    """Candidate validation outcome returned even when passports are disabled."""

    policy: InvalidCandidatePolicy
    input_count: int = Field(ge=0)
    accepted_count: int = Field(ge=0)
    skipped_count: int = Field(ge=0)
    skipped_by_reason: dict[str, int] = Field(default_factory=dict)
    skipped_candidates: list[SkippedCandidate] = Field(default_factory=list)


class RerankRequest(BaseModel):
    """A single rerank request for :meth:`~skeinrank.app.engine.RerankEngine.rerank_many`.

    This type is intentionally minimal and JSON-friendly.
    """

    query: str = Field(..., description="Query string")
    candidates: list[Candidate] = Field(..., description="Candidates to rerank")
    top_k: int | None = Field(
        default=None, description="Optional per-request top_k override"
    )


class RankedItem(BaseModel):
    """A ranked output item."""

    id: str
    score: float
    rank: int


class StageEvent(BaseModel):
    """Timing and debug info for a single stage.

    Notes
    -----
    The stable JSON field name is ``elapsed_ms``.
    For convenience (and nicer ergonomics in notebooks), a read-only
    ``ms`` property is provided as an alias.
    """

    model_config = ConfigDict(protected_namespaces=())

    name: str
    elapsed_ms: float
    details: dict[str, Any] = Field(default_factory=dict)

    @property
    def ms(self) -> float:
        return self.elapsed_ms


class RequestPassport(BaseModel):
    """Explainability + reproducibility metadata."""

    model_config = ConfigDict(protected_namespaces=())

    schema_version: str = Field(default=SCHEMA_VERSION)
    passport_level: str = Field(
        default="debug",
        description="Passport verbosity level: summary | debug. (off => passport is null)",
    )
    passport_upgraded_by: list[str] = Field(
        default_factory=list,
        description="Why the passport is debug for this request: explicit|sample|latency|warnings|fallback.",
    )

    reason_details: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Extra parameters explaining why the passport was upgraded. "
            "Only populated for debug passports."
        ),
    )
    request_id: str = Field(description="Unique request identifier (UUID).")
    runtime: RequestRuntime
    total_ms: float = Field(description="Total wall time across stages (ms).")
    profile_id: str
    profile_hash: str
    device: str
    backend: str
    provider: str | None = None
    variant: str | None = None
    model_id: str
    model_revision: str | None = None
    stages: list[StageEvent] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class RerankResult(BaseModel):
    """Result of reranking."""

    query: str
    ranked: list[RankedItem]
    passport: RequestPassport | None = None
    candidate_validation: CandidateValidationSummary | None = None

    @model_serializer(mode="wrap")
    def _serialize(self, handler):
        payload = handler(self)
        if self.candidate_validation is None:
            payload.pop("candidate_validation", None)
        return payload


class ScoreResult(BaseModel):
    """Result of scoring without sorting."""

    query: str
    scores: dict[str, float]
    passport: RequestPassport | None = None
    candidate_validation: CandidateValidationSummary | None = None

    @model_serializer(mode="wrap")
    def _serialize(self, handler):
        payload = handler(self)
        if self.candidate_validation is None:
            payload.pop("candidate_validation", None)
        return payload
