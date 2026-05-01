from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

ATTRIBUTE_SCHEMA_VERSION = "1"


class AttributeSlot(str, Enum):
    STACK = "STACK"
    LANGUAGE = "LANGUAGE"
    FRAMEWORK = "FRAMEWORK"
    LIB = "LIB"
    TOOL = "TOOL"
    CLOUD = "CLOUD"
    DB = "DB"
    OS = "OS"
    PROTOCOL = "PROTOCOL"
    ERROR = "ERROR"
    COMPONENT = "COMPONENT"
    VERSION = "VERSION"


class AttributeSnapshot(BaseModel):
    """Versioned terminology snapshot used to build runtime matchers."""

    version: str = Field(
        description="Stable version of the terminology profile snapshot"
    )
    source: str = Field(
        default="file", description="Snapshot source, e.g. file | postgres-export"
    )
    created_at: str | None = Field(
        default=None, description="Human-readable creation date or timestamp"
    )
    description: str | None = Field(default=None)


class AttributeEvidence(BaseModel):
    source: str = Field(
        description="Evidence source: alias | regex | gliner | e5 | keybert | literal"
    )
    matched_text: str = Field(
        description="Original text span that triggered the attribute"
    )
    start: int | None = Field(default=None)
    end: int | None = Field(default=None)
    rule_id: str | None = Field(default=None)


class ExtractedAttribute(BaseModel):
    slot: AttributeSlot
    value: str = Field(description="Canonical attribute value")
    source: str = Field(description="Primary source used to extract the attribute")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    evidences: list[AttributeEvidence] = Field(default_factory=list)


class AttributeTrace(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    slot: AttributeSlot
    value: str
    source: str
    matched_text: str
    rule_id: str | None = None
    canonicalized_from: str | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    reason: str | None = None


class AttributeProfile(BaseModel):
    profile_id: str
    description: str
    total_limit: int = Field(ge=1)
    slot_limits: dict[AttributeSlot, int] = Field(default_factory=dict)
    snapshot: AttributeSnapshot
    alias_matcher_backend: str = Field(default="simple")


class AttributeStageStatus(BaseModel):
    stage: str
    enabled: bool = False
    available: bool = False
    executed: bool = False
    emitted_candidates: int = 0
    warning: str | None = None


class AttributePassport(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    schema_version: str = Field(default=ATTRIBUTE_SCHEMA_VERSION)
    profile_id: str
    snapshot: AttributeSnapshot | None = None
    alias_matcher_backend: str | None = None
    normalized_text: str
    proposed: list[AttributeTrace] = Field(default_factory=list)
    accepted: list[AttributeTrace] = Field(default_factory=list)
    filtered_out: list[AttributeTrace] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    stage_status: list[AttributeStageStatus] = Field(default_factory=list)


class AttributePack(BaseModel):
    text: str
    profile_id: str
    snapshot: AttributeSnapshot | None = None
    alias_matcher_backend: str | None = None
    attributes: list[ExtractedAttribute] = Field(default_factory=list)
    passport: AttributePassport | None = None
