"""Pydantic request and response schemas for the governance API."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ServiceInfo(BaseModel):
    """Service metadata returned by health endpoints."""

    name: str
    version: str


class DatabaseHealth(BaseModel):
    """Database connectivity status."""

    ok: bool
    url: str
    error: str | None = None


class HealthzResponse(BaseModel):
    """Health check response."""

    status: str = Field(..., examples=["ok", "degraded"])
    service: ServiceInfo
    database: DatabaseHealth


class ProfileCreateRequest(BaseModel):
    """Request body for creating a terminology profile."""

    name: str = Field(..., min_length=1, max_length=128)
    description: str | None = None


class ProfileUpdateRequest(BaseModel):
    """Request body for updating a terminology profile."""

    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = None


class ProfileResponse(BaseModel):
    """Terminology profile response."""

    id: int
    name: str
    normalized_name: str
    description: str | None = None
    created_at: datetime
    updated_at: datetime


class TermCreateRequest(BaseModel):
    """Request body for creating a canonical term."""

    canonical_value: str = Field(..., min_length=1, max_length=256)
    slot: str = Field(..., min_length=1, max_length=64)
    description: str | None = None
    status: str = "active"


class TermUpdateRequest(BaseModel):
    """Request body for updating a canonical term."""

    canonical_value: str | None = Field(default=None, min_length=1, max_length=256)
    slot: str | None = Field(default=None, min_length=1, max_length=64)
    description: str | None = None
    status: str | None = None


class AliasCreateRequest(BaseModel):
    """Request body for creating an alias for a canonical term."""

    alias_value: str = Field(..., min_length=1, max_length=256)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    status: str = "active"
    notes: str | None = None


class AliasUpdateRequest(BaseModel):
    """Request body for updating an alias for a canonical term."""

    alias_value: str | None = Field(default=None, min_length=1, max_length=256)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    status: str | None = None
    notes: str | None = None


class AliasResponse(BaseModel):
    """Alias response attached to canonical terms."""

    id: int
    alias_value: str
    normalized_alias: str
    status: str
    confidence: float
    notes: str | None = None
    created_at: datetime
    updated_at: datetime


class TermResponse(BaseModel):
    """Canonical term response."""

    id: int
    canonical_value: str
    normalized_value: str
    slot: str
    status: str
    description: str | None = None
    aliases: list[AliasResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class SnapshotExportRequest(BaseModel):
    """Request body for building a runtime snapshot from a profile."""

    snapshot_version: str | None = None
    description: str | None = None


class SnapshotMetadataResponse(BaseModel):
    """Runtime snapshot metadata."""

    version: str
    source: str
    created_at: str
    description: str | None = None


class SnapshotAliasGroupResponse(BaseModel):
    """Grouped aliases for one canonical term in a runtime snapshot."""

    slot: str
    canonical: str
    aliases: list[str | dict[str, Any]]


class RuntimeSnapshotResponse(BaseModel):
    """Runtime-compatible terminology snapshot response."""

    profile_id: str
    snapshot: SnapshotMetadataResponse
    alias_matcher: dict[str, str]
    aliases: list[SnapshotAliasGroupResponse]
    rules: list[dict[str, Any]] = Field(default_factory=list)


class ErrorResponse(BaseModel):
    """User-facing error response."""

    detail: str


class LoginRequest(BaseModel):
    """Request body for local governance API login."""

    username: str = Field(..., min_length=1, max_length=128)
    password: str = Field(..., min_length=1, max_length=512)


class UserCreateRequest(BaseModel):
    """Request body for creating a governance API user."""

    username: str = Field(..., min_length=1, max_length=128)
    password: str = Field(..., min_length=1, max_length=512)
    display_name: str | None = Field(default=None, max_length=256)
    role: str
    is_active: bool = True


class UserUpdateRequest(BaseModel):
    """Request body for updating a governance API user."""

    username: str | None = Field(default=None, min_length=1, max_length=128)
    password: str | None = Field(default=None, min_length=1, max_length=512)
    display_name: str | None = Field(default=None, max_length=256)
    role: str | None = None
    is_active: bool | None = None


class UserResponse(BaseModel):
    """Governance API user response without password material."""

    id: int
    username: str
    normalized_username: str
    display_name: str | None = None
    role: str
    is_active: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None
    last_login_at: datetime | None = None


class AuthTokenResponse(BaseModel):
    """Login response containing the bearer token and current user."""

    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    user: UserResponse
