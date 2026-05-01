from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class RerankESRequest(BaseModel):
    query: str = Field(..., min_length=1)
    index: Optional[str] = None
    bm25_k: int = Field(100, ge=1, le=5000)
    top_k: int = Field(10, ge=1, le=2000)
    profile: Optional[str] = None
    passport: Optional[str] = None  # "summary" | "debug" | "off"
    batch_size: Optional[int] = Field(None, ge=1, le=4096)


class RankedItem(BaseModel):
    id: str
    score: float


class RerankESResponse(BaseModel):
    request_id: str
    profile: str
    index: str
    bm25_k: int
    top_k: int
    results: List[RankedItem]
    passport: Optional[Dict[str, Any]] = None


class AttributeExtractRequest(BaseModel):
    text: str = Field(..., min_length=1)
    profile: Optional[str] = None
    debug: bool = False
    use_gliner: Optional[bool] = None
    use_e5: Optional[bool] = None
    use_keybert: Optional[bool] = None


class AttributeEvidenceModel(BaseModel):
    source: str
    matched_text: str
    start: Optional[int] = None
    end: Optional[int] = None
    rule_id: Optional[str] = None


class ExtractedAttributeModel(BaseModel):
    slot: str
    value: str
    source: str
    confidence: float
    evidences: List[AttributeEvidenceModel] = Field(default_factory=list)


class AttributeExtractResponse(BaseModel):
    request_id: str
    profile: str
    attributes: List[ExtractedAttributeModel] = Field(default_factory=list)
    passport: Optional[Dict[str, Any]] = None


class HealthzResponse(BaseModel):
    status: str
    service: Dict[str, Any]
    elasticsearch: Dict[str, Any]


class DiagnosticsResponse(BaseModel):
    config: Dict[str, Any]
    core: Optional[Dict[str, Any]] = None
    elasticsearch: Dict[str, Any]
