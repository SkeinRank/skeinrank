"""Stable data contracts.

These models define the public, stable input/output formats for SkeinRank.

Design goals:
- minimal, universal, library-first
- JSON-serializable (via Pydantic)
- future-proof (schema versioning)
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

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


class ScoreResult(BaseModel):
    """Result of scoring without sorting."""

    query: str
    scores: dict[str, float]
    passport: RequestPassport | None = None
