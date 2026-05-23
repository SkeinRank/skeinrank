"""Pydantic request and response schemas for the governance API."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from .dictionary_spec import DICTIONARY_SCHEMA_VERSION


class ServiceInfo(BaseModel):
    """Service metadata returned by health endpoints."""

    name: str
    version: str


class DatabaseHealth(BaseModel):
    """Database connectivity status."""

    ok: bool
    url: str
    error: str | None = None


class ExternalDependencyHealth(BaseModel):
    """External dependency connectivity status."""

    ok: bool
    configured: bool = True
    url: str | None = None
    name: str | None = None
    version: str | None = None
    error: str | None = None


class HealthzResponse(BaseModel):
    """Health check response."""

    status: str = Field(..., examples=["ok", "degraded"])
    service: ServiceInfo
    database: DatabaseHealth


class LivezResponse(BaseModel):
    """Liveness check response."""

    status: str = Field(..., examples=["ok"])
    service: ServiceInfo


class ReadyzResponse(BaseModel):
    """Readiness check response with external dependency status."""

    status: str = Field(..., examples=["ok", "degraded"])
    service: ServiceInfo
    database: DatabaseHealth
    elasticsearch: ExternalDependencyHealth


class DashboardReadinessItem(BaseModel):
    """One product dashboard readiness item."""

    status: str = Field(..., examples=["ok", "degraded", "not_configured", "unknown"])
    configured: bool = True
    message: str | None = None
    url: str | None = None
    name: str | None = None
    version: str | None = None


class DashboardCounts(BaseModel):
    """Dashboard aggregate counts."""

    profiles: int
    canonical_terms: int
    aliases: int
    bindings: int
    ready_bindings: int
    stale_bindings: int
    updating_bindings: int
    failed_bindings: int
    never_enriched_bindings: int
    running_jobs: int
    failed_jobs: int


class DashboardSetupChecklist(BaseModel):
    """High-level first-run setup progress."""

    has_profile: bool
    has_terms: bool
    has_binding: bool
    has_successful_enrichment: bool
    has_runtime_snapshot: bool


class DashboardRecentJob(BaseModel):
    """Compact enrichment job row for the dashboard."""

    id: int
    binding_id: int
    binding_name: str
    profile_name: str
    status: str
    source_index: str
    target_index: str | None = None
    alias_name: str | None = None
    snapshot_version: str | None = None
    documents_seen: int
    documents_enriched: int
    documents_failed: int
    error_message: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class DashboardBindingSummary(BaseModel):
    """Compact binding health row for the dashboard."""

    id: int
    name: str
    profile_name: str
    index_name: str
    is_enabled: bool
    status: str
    snapshot_version: str | None = None
    pending_snapshot_version: str | None = None
    last_successful_job_id: int | None = None
    latest_job: DashboardRecentJob | None = None
    updated_at: datetime


class DashboardSummaryResponse(BaseModel):
    """Product dashboard summary for the governance console home page."""

    readiness: dict[str, DashboardReadinessItem]
    counts: DashboardCounts
    setup: DashboardSetupChecklist
    bindings: list[DashboardBindingSummary] = Field(default_factory=list)
    recent_jobs: list[DashboardRecentJob] = Field(default_factory=list)


class SnapshotDiffSummary(BaseModel):
    """Difference between the active runtime snapshot and current profile state."""

    active_checksum: str | None = None
    current_checksum: str | None = None
    active_aliases: int
    current_aliases: int
    added_aliases: int
    removed_aliases: int
    changed_aliases: int
    changed: bool


class SnapshotBindingState(BaseModel):
    """Runtime snapshot state for one binding."""

    id: int
    name: str
    profile_name: str
    index_name: str
    filter_field: str | None = None
    filter_value: str | None = None
    is_enabled: bool
    status: str
    active_snapshot_version: str | None = None
    pending_snapshot_version: str | None = None
    last_successful_snapshot_at: datetime | None = None
    last_successful_job_id: int | None = None
    latest_job_id: int | None = None
    latest_job_status: str | None = None
    latest_job_error: str | None = None
    rollback_available: bool
    snapshot_aliases_total: int
    current_aliases_total: int
    diff: SnapshotDiffSummary
    updated_at: datetime


class SnapshotHistoryItem(BaseModel):
    """One enrichment job that produced or attempted a runtime snapshot."""

    job_id: int
    binding_id: int
    binding_name: str
    profile_name: str
    status: str
    snapshot_version: str | None = None
    previous_snapshot_version: str | None = None
    checksum: str | None = None
    alias_entries_total: int
    documents_seen: int
    documents_enriched: int
    documents_failed: int
    target_index: str | None = None
    alias_name: str | None = None
    rollback_available: bool
    error_message: str | None = None
    created_at: datetime
    finished_at: datetime | None = None


class SnapshotCounts(BaseModel):
    """Aggregate runtime snapshot counters."""

    bindings: int
    active_snapshots: int
    stale_snapshots: int
    pending_snapshots: int
    failed_updates: int
    never_enriched: int
    rollback_available: int


class SnapshotSummaryResponse(BaseModel):
    """Product runtime snapshot summary for the Snapshots UI tab."""

    counts: SnapshotCounts
    bindings: list[SnapshotBindingState] = Field(default_factory=list)
    history: list[SnapshotHistoryItem] = Field(default_factory=list)


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


class StopListCreateRequest(BaseModel):
    """Request body for creating a profile stop-list entry."""

    value: str = Field(..., min_length=1, max_length=256)
    target: str = "both"
    reason: str | None = None
    is_active: bool = True


class StopListUpdateRequest(BaseModel):
    """Request body for updating a profile stop-list entry."""

    value: str | None = Field(default=None, min_length=1, max_length=256)
    target: str | None = None
    reason: str | None = None
    is_active: bool | None = None


class StopListEntryResponse(BaseModel):
    """Profile stop-list entry response."""

    id: int
    profile_id: int
    value: str
    normalized_value: str
    target: str
    reason: str | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class GlobalStopListCreateRequest(BaseModel):
    """Request body for creating a global stop-list entry."""

    value: str = Field(..., min_length=1, max_length=256)
    target: str = "both"
    reason: str | None = None
    is_active: bool = True


class GlobalStopListUpdateRequest(BaseModel):
    """Request body for updating a global stop-list entry."""

    value: str | None = Field(default=None, min_length=1, max_length=256)
    target: str | None = None
    reason: str | None = None
    is_active: bool | None = None


class GlobalStopListEntryResponse(BaseModel):
    """Global stop-list entry response."""

    id: int
    value: str
    normalized_value: str
    target: str
    reason: str | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ElasticsearchBindingCreateRequest(BaseModel):
    """Request body for creating an Elasticsearch enrichment binding."""

    name: str = Field(..., min_length=1, max_length=128)
    profile_name: str = Field(..., min_length=1, max_length=128)
    description: str | None = None
    index_name: str = Field(..., min_length=1, max_length=256)
    text_fields: list[str] = Field(..., min_length=1)
    target_field: str = Field(..., min_length=1, max_length=256)
    filter_field: str | None = Field(default=None, max_length=256)
    filter_value: str | None = Field(default=None, max_length=512)
    timestamp_field: str | None = Field(default=None, max_length=256)
    time_window_days: int | None = Field(default=None, ge=1, le=3650)
    mode: str = "dry_run"
    write_strategy: str = "reindex_alias_swap"
    is_enabled: bool = True


class ElasticsearchBindingUpdateRequest(BaseModel):
    """Request body for updating an Elasticsearch enrichment binding."""

    name: str | None = Field(default=None, min_length=1, max_length=128)
    profile_name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = None
    index_name: str | None = Field(default=None, min_length=1, max_length=256)
    text_fields: list[str] | None = Field(default=None, min_length=1)
    target_field: str | None = Field(default=None, min_length=1, max_length=256)
    filter_field: str | None = Field(default=None, max_length=256)
    filter_value: str | None = Field(default=None, max_length=512)
    timestamp_field: str | None = Field(default=None, max_length=256)
    time_window_days: int | None = Field(default=None, ge=1, le=3650)
    mode: str | None = None
    write_strategy: str | None = None
    is_enabled: bool | None = None


class ElasticsearchBindingResponse(BaseModel):
    """Saved Elasticsearch enrichment binding response."""

    id: int
    profile_id: int
    profile_name: str
    name: str
    normalized_name: str
    description: str | None = None
    provider: str
    index_name: str
    text_fields: list[str]
    target_field: str
    filter_field: str | None = None
    filter_value: str | None = None
    timestamp_field: str | None = None
    time_window_days: int | None = None
    mode: str
    write_strategy: str
    is_enabled: bool
    last_successful_snapshot_version: str | None = None
    last_successful_snapshot_at: datetime | None = None
    last_successful_job_id: int | None = None
    pending_snapshot_version: str | None = None
    snapshot_status: str = "uninitialized"
    created_at: datetime
    updated_at: datetime


class ElasticsearchConnectionStatusResponse(BaseModel):
    """Elasticsearch connection discovery status."""

    configured: bool
    ok: bool
    url: str | None = None
    cluster_name: str | None = None
    cluster_version: str | None = None
    error: str | None = None


class ElasticsearchIndexResponse(BaseModel):
    """Elasticsearch index discovered from _cat/indices."""

    name: str
    health: str | None = None
    status: str | None = None
    docs_count: int | None = None


class ElasticsearchMappingFieldResponse(BaseModel):
    """Flattened Elasticsearch mapping field returned to the UI."""

    name: str
    type: str
    is_text_candidate: bool
    is_discriminator_candidate: bool


class ElasticsearchIndexMappingResponse(BaseModel):
    """Usable fields discovered from an Elasticsearch index mapping."""

    index_name: str
    fields: list[ElasticsearchMappingFieldResponse]


class ElasticsearchBindingDryRunRequest(BaseModel):
    """Request body for previewing a binding without writing to Elasticsearch."""

    limit: int = Field(default=3, ge=1, le=20)


class ElasticsearchDryRunMatchedAlias(BaseModel):
    """Alias match found in a sample Elasticsearch document."""

    alias_value: str
    canonical_value: str
    slot: str
    matched_text: str
    confidence: float


class ElasticsearchBindingDryRunDocument(BaseModel):
    """Preview of one document that would be enriched by a binding."""

    document_id: str
    index_name: str
    text_preview: str
    source_preview: dict[str, list[str]]
    matched_aliases: list[ElasticsearchDryRunMatchedAlias]
    would_write: dict[str, Any]


class ElasticsearchBindingDryRunResponse(BaseModel):
    """Read-only dry-run result for one Elasticsearch binding."""

    binding: ElasticsearchBindingResponse
    limit: int
    documents: list[ElasticsearchBindingDryRunDocument]
    warnings: list[str] = Field(default_factory=list)


class ElasticsearchEvidenceRequest(BaseModel):
    """Request body for bounded Elasticsearch evidence search."""

    query: str = Field(..., min_length=1, max_length=256)
    canonical_value: str | None = Field(default=None, max_length=256)
    max_documents: int = Field(default=5, ge=1, le=10)
    context_chars: int = Field(default=80, ge=20, le=240)


class ElasticsearchEvidenceDocument(BaseModel):
    """One bounded evidence fragment found in Elasticsearch."""

    document_id: str
    index_name: str
    field: str
    fragment: str
    highlighted_fragment: str
    matched_text: str
    match_start: int
    match_end: int


class ElasticsearchEvidenceResponse(BaseModel):
    """Bounded read-only Elasticsearch evidence search response."""

    binding: ElasticsearchBindingResponse
    query: str
    normalized_query: str
    canonical_value: str | None = None
    max_documents: int
    documents: list[ElasticsearchEvidenceDocument]
    warnings: list[str] = Field(default_factory=list)


class SuggestionEvidenceSnapshot(BaseModel):
    """Saved evidence snapshot attached to a governance suggestion."""

    binding_id: int
    binding_name: str
    index_name: str
    profile_name: str
    query: str
    normalized_query: str
    canonical_value: str | None = None
    max_documents: int
    documents: list[ElasticsearchEvidenceDocument]
    warnings: list[str] = Field(default_factory=list)


class SuggestionEvidenceRefreshRequest(BaseModel):
    """Request body for refreshing and saving suggestion evidence."""

    binding_id: int
    query: str | None = Field(default=None, min_length=1, max_length=256)
    max_documents: int = Field(default=5, ge=1, le=10)
    context_chars: int = Field(default=80, ge=20, le=240)


class ElasticsearchEnrichmentJobCreateRequest(BaseModel):
    """Request body for starting an Elasticsearch enrichment job."""

    target_index_name: str | None = Field(default=None, min_length=1, max_length=256)
    alias_name: str | None = Field(default=None, min_length=1, max_length=256)
    snapshot_version: str | None = Field(default=None, min_length=1, max_length=128)
    max_documents: int = Field(default=1000, ge=1, le=10000)
    chunk_size: int | None = Field(default=None, ge=1, le=1000)


class ElasticsearchEnrichmentJobCancelRequest(BaseModel):
    """Request body for safely cancelling an Elasticsearch enrichment job."""

    reason: str | None = Field(default=None, max_length=512)


class ElasticsearchEnrichmentJobRollbackRequest(BaseModel):
    """Request body for rolling back a completed reindex alias-swap job."""

    reason: str | None = Field(default=None, max_length=512)


class ElasticsearchEnrichmentJobResponse(BaseModel):
    """Elasticsearch enrichment job status response."""

    id: int
    binding_id: int
    profile_id: int
    binding_name: str
    profile_name: str
    status: str
    write_strategy: str
    source_index: str
    target_index: str | None = None
    alias_name: str | None = None
    snapshot_version: str | None = None
    previous_snapshot_version: str | None = None
    requested_by: str | None = None
    documents_seen: int
    documents_enriched: int
    documents_failed: int
    result_json: dict[str, Any]
    error_message: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class SuggestionCreateRequest(BaseModel):
    """Request body for proposing a terminology change for later review."""

    suggestion_type: str = "alias"
    canonical_value: str = Field(..., min_length=1, max_length=256)
    alias_value: str | None = Field(default=None, min_length=1, max_length=256)
    slot: str = Field(..., min_length=1, max_length=64)
    description: str | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    source: str = "manual"
    context: str | None = None
    binding_id: int | None = Field(default=None, ge=1)
    proposal_source_type: str = Field(default="human", max_length=32)
    proposal_source_name: str | None = Field(default=None, max_length=128)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=128)
    source_payload: dict[str, Any] | None = None
    validation_summary: dict[str, Any] | None = None


class SuggestionReviewRequest(BaseModel):
    """Request body for approving or rejecting a suggestion."""

    review_comment: str | None = None


class SuggestionResponse(BaseModel):
    """Suggestion response used by approval workflow clients."""

    id: int
    profile_id: int
    term_id: int | None = None
    alias_id: int | None = None
    binding_id: int | None = None
    suggestion_type: str
    canonical_value: str
    normalized_canonical: str
    alias_value: str | None = None
    normalized_alias: str | None = None
    slot: str
    description: str | None = None
    confidence: float
    source: str
    context: str | None = None
    proposal_source_type: str
    proposal_source_name: str | None = None
    idempotency_key: str | None = None
    source_payload: dict[str, Any] | None = None
    validation_summary: dict[str, Any] | None = None
    status: str
    created_by: str | None = None
    reviewed_by: str | None = None
    review_comment: str | None = None
    reviewed_at: datetime | None = None
    evidence_snapshot: SuggestionEvidenceSnapshot | None = None
    evidence_checked_by: str | None = None
    evidence_checked_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ProposalSourceQualityResponse(BaseModel):
    """Aggregated source-quality signal for proposal submitters."""

    proposal_source_type: str
    proposal_source_name: str
    proposals_total: int
    pending: int
    approved: int
    rejected: int
    validation_passed: int
    validation_warning: int
    validation_blocked: int
    validation_unknown: int
    approval_rate: float
    rejection_rate: float
    blocked_rate: float
    average_confidence: float


class ProposalBatchApplyRequest(BaseModel):
    """Apply pending proposals as one audited batch.

    If ``suggestion_ids`` is omitted, all pending suggestions for the profile are
    applied. Snapshot publishing is optional and requires ``binding_id``.
    """

    suggestion_ids: list[int] | None = Field(default=None, min_length=1)
    review_comment: str | None = None
    publish_snapshot: bool = False
    binding_id: int | None = Field(default=None, ge=1)
    snapshot_version: str | None = Field(default=None, min_length=1, max_length=128)


class ProposalBatchSnapshotResponse(BaseModel):
    """Runtime snapshot information produced by a proposal batch."""

    published: bool = False
    binding_id: int | None = None
    snapshot_version: str | None = None
    snapshot_status: str = "unpublished"
    checksum: str | None = None
    alias_entries_total: int = 0


class ProposalBatchApplyResponse(BaseModel):
    """Result of applying a batch of pending proposals."""

    status: str = "applied"
    profile_name: str
    normalized_profile_name: str
    requested_suggestion_ids: list[int] = Field(default_factory=list)
    applied_suggestion_ids: list[int] = Field(default_factory=list)
    created_terms: int = 0
    created_aliases: int = 0
    snapshot: ProposalBatchSnapshotResponse
    suggestions: list[SuggestionResponse] = Field(default_factory=list)


class AgentToolBindingContextResponse(BaseModel):
    """Binding context exposed to agents and automation tools."""

    id: int
    name: str
    profile_name: str
    normalized_profile_name: str
    provider: str
    index_name: str
    text_fields: list[str]
    target_field: str
    filter_field: str | None = None
    filter_value: str | None = None
    timestamp_field: str | None = None
    time_window_days: int | None = None
    is_enabled: bool
    snapshot_version: str | None = None
    snapshot_status: str = "uninitialized"


class AgentToolValidateAliasRequest(BaseModel):
    """Agent/tool request for validating an alias proposal without saving it."""

    profile_name: str | None = Field(default=None, min_length=1, max_length=128)
    binding_id: int | None = Field(default=None, ge=1)
    canonical_value: str = Field(..., min_length=1, max_length=256)
    alias_value: str = Field(..., min_length=1, max_length=256)
    slot: str = Field(..., min_length=1, max_length=64)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    proposal_source_type: str = Field(default="agent", max_length=32)
    proposal_source_name: str | None = Field(default=None, max_length=128)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=128)
    source_payload: dict[str, Any] | None = None


class AgentToolValidateAliasResponse(BaseModel):
    """Validation result for an agent/tool alias proposal."""

    profile_name: str
    normalized_profile_name: str
    binding_id: int | None = None
    canonical_value: str
    alias_value: str
    slot: str
    confidence: float
    proposal_source_type: str
    proposal_source_name: str | None = None
    idempotency_key: str | None = None
    validation_summary: dict[str, Any]


class AgentToolSuggestAliasRequest(BaseModel):
    """Agent/tool request for creating an alias proposal for review."""

    profile_name: str | None = Field(default=None, min_length=1, max_length=128)
    binding_id: int | None = Field(default=None, ge=1)
    canonical_value: str = Field(..., min_length=1, max_length=256)
    alias_value: str = Field(..., min_length=1, max_length=256)
    slot: str = Field(..., min_length=1, max_length=64)
    description: str | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    context: str | None = None
    proposal_source_type: str = Field(default="agent", max_length=32)
    proposal_source_name: str | None = Field(default=None, max_length=128)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=128)
    source_payload: dict[str, Any] | None = None


class AgentToolSuggestAliasResponse(BaseModel):
    """Created alias proposal response for tools."""

    created: bool = True
    suggestion: SuggestionResponse
    validation_summary: dict[str, Any]


class AgentToolExplainQueryRequest(BaseModel):
    """Agent/tool request for explaining runtime query canonicalization."""

    profile_name: str | None = Field(default=None, min_length=1, max_length=128)
    binding_id: int | None = Field(default=None, ge=1)
    query: str = Field(..., min_length=1, max_length=2000)
    text_fields: list[str] | None = Field(default=None, min_length=1)
    target_field: str | None = Field(default=None, min_length=1, max_length=256)
    size: int = Field(default=10, ge=1, le=100)
    canonical_boost: float = Field(default=3.0, ge=0.0, le=100.0)
    include_evidence: bool = True
    max_matches: int = Field(default=100, ge=1, le=1000)


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


class TextCanonicalizeRequest(BaseModel):
    """Request body for runtime text canonicalization."""

    profile_name: str | None = Field(default=None, min_length=1, max_length=128)
    binding_id: int | None = Field(default=None, ge=1)
    text: str = Field(..., min_length=1, max_length=20000)
    mode: str = Field(
        default="annotate", examples=["annotate", "replace", "attributes"]
    )
    include_evidence: bool = True
    max_matches: int = Field(default=100, ge=1, le=1000)


class TextCanonicalizeMatch(BaseModel):
    """One alias span detected in a runtime canonicalization request."""

    alias_value: str
    canonical_value: str
    slot: str
    matched_text: str
    start: int
    end: int
    confidence: float
    source: str = "alias"


class TextCanonicalizeEvidence(BaseModel):
    """Explainable evidence for one runtime text canonicalization match."""

    reason: str
    alias_value: str
    canonical_value: str
    slot: str
    matched_text: str
    start: int
    end: int
    confidence: float
    source: str = "alias"


class TextCanonicalizeResponse(BaseModel):
    """Runtime text canonicalization response with optional replacement output."""

    profile_name: str
    normalized_profile_name: str
    mode: str
    binding_id: int | None = None
    snapshot_version: str | None = None
    snapshot_source: str = "latest_profile"
    original_text: str
    canonical_text: str
    changed: bool
    canonical_values: list[str] = Field(default_factory=list)
    slots: dict[str, list[str]] = Field(default_factory=dict)
    matched_aliases: list[str] = Field(default_factory=list)
    replacements: list[TextCanonicalizeMatch] = Field(default_factory=list)
    evidence: list[TextCanonicalizeEvidence] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class QueryPlanRequest(BaseModel):
    """Request body for building a runtime Elasticsearch query plan."""

    profile_name: str | None = Field(default=None, min_length=1, max_length=128)
    binding_id: int | None = Field(default=None, ge=1)
    query: str = Field(..., min_length=1, max_length=2000)
    text_fields: list[str] | None = Field(default=None, min_length=1)
    target_field: str | None = Field(default=None, min_length=1, max_length=256)
    size: int = Field(default=10, ge=1, le=100)
    canonical_boost: float = Field(default=3.0, ge=0.0, le=100.0)
    include_evidence: bool = True
    max_matches: int = Field(default=100, ge=1, le=1000)


class QueryPlanResponse(BaseModel):
    """Runtime query understanding and Elasticsearch DSL preview."""

    profile_name: str
    normalized_profile_name: str
    query: str
    canonical_query: str
    changed: bool
    text_fields: list[str]
    target_field: str
    binding_id: int | None = None
    snapshot_version: str | None = None
    snapshot_source: str = "latest_profile"
    canonical_values: list[str] = Field(default_factory=list)
    slots: dict[str, list[str]] = Field(default_factory=dict)
    matched_aliases: list[str] = Field(default_factory=list)
    replacements: list[TextCanonicalizeMatch] = Field(default_factory=list)
    evidence: list[TextCanonicalizeEvidence] = Field(default_factory=list)
    elasticsearch: dict[str, Any]
    warnings: list[str] = Field(default_factory=list)


class SearchRequest(BaseModel):
    """Request body for executing runtime search against Elasticsearch."""

    profile_name: str | None = Field(default=None, min_length=1, max_length=128)
    binding_id: int | None = Field(default=None, ge=1)
    index_name: str | None = Field(default=None, min_length=1, max_length=256)
    query: str = Field(..., min_length=1, max_length=2000)
    text_fields: list[str] | None = Field(default=None, min_length=1)
    target_field: str | None = Field(default=None, min_length=1, max_length=256)
    size: int = Field(default=10, ge=1, le=100)
    canonical_boost: float = Field(default=3.0, ge=0.0, le=100.0)
    include_source: bool = True
    source_fields: list[str] | None = None
    include_evidence: bool = True
    max_matches: int = Field(default=100, ge=1, le=1000)


class SearchHitResponse(BaseModel):
    """One runtime search hit returned from Elasticsearch."""

    id: str
    index: str
    score: float | None = None
    source: dict[str, Any] = Field(default_factory=dict)
    skeinrank: dict[str, Any] | None = None


class SearchResponse(BaseModel):
    """Runtime search response with query understanding metadata."""

    profile_name: str
    normalized_profile_name: str
    index_name: str
    query: str
    canonical_query: str
    changed: bool
    binding_id: int | None = None
    snapshot_version: str | None = None
    snapshot_source: str = "latest_profile"
    canonical_values: list[str] = Field(default_factory=list)
    slots: dict[str, list[str]] = Field(default_factory=dict)
    matched_aliases: list[str] = Field(default_factory=list)
    replacements: list[TextCanonicalizeMatch] = Field(default_factory=list)
    evidence: list[TextCanonicalizeEvidence] = Field(default_factory=list)
    elasticsearch: dict[str, Any]
    total: dict[str, Any] | int | None = None
    hits: list[SearchHitResponse] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class MultiSearchRequest(BaseModel):
    """Request body for executing runtime search across multiple bindings."""

    binding_ids: list[int] = Field(..., min_length=1, max_length=20)
    query: str = Field(..., min_length=1, max_length=2000)
    size: int = Field(default=10, ge=1, le=100)
    per_binding_size: int | None = Field(default=None, ge=1, le=100)
    canonical_boost: float = Field(default=3.0, ge=0.0, le=100.0)
    include_source: bool = True
    source_fields: list[str] | None = None
    include_evidence: bool = True
    max_matches: int = Field(default=100, ge=1, le=1000)


class MultiSearchHitResponse(SearchHitResponse):
    """One merged runtime search hit with binding context."""

    binding_id: int
    profile_name: str
    snapshot_version: str | None = None
    snapshot_source: str = "latest_profile"


class MultiSearchBindingResponse(BaseModel):
    """Per-binding runtime search result included in a multi-search response."""

    binding_id: int
    status: str
    profile_name: str | None = None
    normalized_profile_name: str | None = None
    index_name: str | None = None
    snapshot_version: str | None = None
    snapshot_source: str | None = None
    canonical_query: str | None = None
    changed: bool | None = None
    canonical_values: list[str] = Field(default_factory=list)
    slots: dict[str, list[str]] = Field(default_factory=dict)
    matched_aliases: list[str] = Field(default_factory=list)
    total: dict[str, Any] | int | None = None
    hits_count: int = 0
    warnings: list[str] = Field(default_factory=list)
    error: str | None = None


class MultiSearchResponse(BaseModel):
    """Runtime multi-binding search response."""

    query: str
    binding_ids: list[int]
    size: int
    per_binding_size: int
    total_bindings: int
    succeeded_bindings: int
    failed_bindings: int
    results: list[MultiSearchBindingResponse] = Field(default_factory=list)
    hits: list[MultiSearchHitResponse] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ConsoleDictionaryAliasInput(BaseModel):
    """Alias entry accepted by the user console import API."""

    value: str = Field(..., min_length=1, max_length=256)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    status: str = "active"
    notes: str | None = None


class ConsoleDictionaryTermInput(BaseModel):
    """Canonical term entry accepted by the user console import API."""

    canonical_value: str = Field(..., min_length=1, max_length=256)
    slot: str = Field(..., min_length=1, max_length=64)
    description: str | None = None
    status: str = "active"
    aliases: list[str | ConsoleDictionaryAliasInput] = Field(default_factory=list)


class ConsoleStopListInput(BaseModel):
    """Stop-list entry accepted by the user console import API."""

    value: str = Field(..., min_length=1, max_length=256)
    target: str = "both"
    reason: str | None = None
    is_active: bool = True


class ConsoleDictionaryPayload(BaseModel):
    """Dictionary migration payload for validation and import."""

    schema_version: str | None = Field(default=DICTIONARY_SCHEMA_VERSION)
    profile_name: str = Field(..., min_length=1, max_length=128)
    profile_description: str | None = None
    create_profile: bool = True
    mode: str = "upsert"
    terms: list[ConsoleDictionaryTermInput] = Field(default_factory=list)
    profile_stop_list: list[str | ConsoleStopListInput] = Field(default_factory=list)
    global_stop_list: list[str | ConsoleStopListInput] = Field(default_factory=list)


class ConsoleDictionaryIssue(BaseModel):
    """Validation issue returned by the user console API."""

    code: str
    message: str
    path: str | None = None
    severity: str = "error"


class ConsoleDictionarySummary(BaseModel):
    """High-level migration summary returned by the user console API."""

    terms_total: int = 0
    aliases_total: int = 0
    profile_stop_list_total: int = 0
    global_stop_list_total: int = 0
    would_create_terms: int = 0
    would_update_terms: int = 0
    would_create_aliases: int = 0
    would_update_aliases: int = 0
    would_create_profile_stop_list_entries: int = 0
    would_update_profile_stop_list_entries: int = 0
    would_create_global_stop_list_entries: int = 0
    would_update_global_stop_list_entries: int = 0
    created_terms: int = 0
    updated_terms: int = 0
    created_aliases: int = 0
    updated_aliases: int = 0
    created_profile_stop_list_entries: int = 0
    updated_profile_stop_list_entries: int = 0
    created_global_stop_list_entries: int = 0
    updated_global_stop_list_entries: int = 0
    duplicates: int = 0
    conflicts: int = 0
    blocked_by_stop_list: int = 0
    errors: int = 0
    warnings: int = 0


class ConsoleDictionaryReport(BaseModel):
    """Validation/import report for a dictionary migration payload."""

    status: str
    schema_version: str
    profile_name: str
    normalized_profile_name: str
    profile_exists: bool
    mode: str
    summary: ConsoleDictionarySummary
    errors: list[ConsoleDictionaryIssue] = Field(default_factory=list)
    warnings: list[ConsoleDictionaryIssue] = Field(default_factory=list)


class ConsoleDictionaryExportResponse(BaseModel):
    """Stable user-console dictionary export shape."""

    schema_version: str = DICTIONARY_SCHEMA_VERSION
    profile_name: str
    profile_description: str | None = None
    terms: list[ConsoleDictionaryTermInput]
    profile_stop_list: list[ConsoleStopListInput]
    global_stop_list: list[ConsoleStopListInput]


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
    status: str = "active"
    is_active: bool | None = None


class UserUpdateRequest(BaseModel):
    """Request body for updating a governance API user."""

    username: str | None = Field(default=None, min_length=1, max_length=128)
    password: str | None = Field(default=None, min_length=1, max_length=512)
    display_name: str | None = Field(default=None, max_length=256)
    role: str | None = None
    status: str | None = None
    is_active: bool | None = None


class UserStatusUpdateRequest(BaseModel):
    """Request body for changing a user's account status."""

    status: str


class UserTokenRevokeResponse(BaseModel):
    """Response returned when user-owned personal API tokens are revoked."""

    username: str
    revoked_api_tokens: int


class UserResponse(BaseModel):
    """Governance API user response without password material."""

    id: int
    username: str
    normalized_username: str
    display_name: str | None = None
    role: str
    status: str = "active"
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


class ApiTokenCreateRequest(BaseModel):
    """Request body for creating a personal API token."""

    name: str = Field(..., min_length=1, max_length=128)
    scopes: list[str] = Field(default_factory=list)
    expires_in_days: int | None = Field(default=90, ge=1, le=3650)


class ApiTokenResponse(BaseModel):
    """Masked personal or service-account API token metadata."""

    id: int
    name: str
    token_prefix: str
    scopes: list[str]
    owner_type: str
    owner_name: str
    expires_at: datetime | None = None
    revoked_at: datetime | None = None
    last_used_at: datetime | None = None
    created_by: str | None = None
    created_at: datetime
    updated_at: datetime


class ApiTokenCreateResponse(ApiTokenResponse):
    """Create response that returns the plaintext token once."""

    access_token: str
    token_type: str = "bearer"


class ServiceAccountCreateRequest(BaseModel):
    """Request body for creating a service account."""

    name: str = Field(..., min_length=1, max_length=128)
    display_name: str | None = Field(default=None, max_length=256)
    description: str | None = None
    role: str
    is_active: bool = True


class ServiceAccountUpdateRequest(BaseModel):
    """Request body for updating a service account."""

    name: str | None = Field(default=None, min_length=1, max_length=128)
    display_name: str | None = Field(default=None, max_length=256)
    description: str | None = None
    role: str | None = None
    is_active: bool | None = None


class ServiceAccountResponse(BaseModel):
    """Service account metadata without token material."""

    id: int
    name: str
    normalized_name: str
    display_name: str | None = None
    description: str | None = None
    role: str
    is_active: bool
    created_by: str | None = None
    last_used_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
