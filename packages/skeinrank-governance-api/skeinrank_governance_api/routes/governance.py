"""Terminology governance REST endpoints."""

from __future__ import annotations

import html
import re

from fastapi import (
    APIRouter,
    Body,
    Depends,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)
from skeinrank_governance.cli import (
    GovernanceCliError,
    add_alias,
    add_term,
    build_snapshot,
    create_profile,
    get_profile,
    get_term,
)
from skeinrank_governance.models import (
    ALIAS_STATUSES,
    ELASTICSEARCH_BINDING_MODES,
    ELASTICSEARCH_BINDING_PROVIDERS,
    ELASTICSEARCH_BINDING_WRITE_STRATEGIES,
    PROPOSAL_SOURCE_TYPES,
    STOP_LIST_TARGETS,
    SUGGESTION_SOURCES,
    SUGGESTION_STATUSES,
    SUGGESTION_TYPES,
    TERM_STATUSES,
    CanonicalTerm,
    ElasticsearchBinding,
    ElasticsearchEnrichmentJob,
    GovernanceGlobalStopListEntry,
    GovernanceStopListEntry,
    GovernanceSuggestion,
    TermAlias,
    TerminologyProfile,
    normalize_profile_name,
    normalize_value,
    utc_now,
)
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..auth import AuthContext, require_roles
from ..dependencies import get_session
from ..elasticsearch import (
    ElasticsearchDiscoveryClient,
    ElasticsearchDiscoveryError,
    compose_source_text,
    get_source_values,
    source_preview,
)
from ..observability.metrics import (
    record_proposal_batch_apply,
    record_proposal_review,
    record_proposal_submission,
)
from ..proposal_idempotency import (
    ProposalIdempotencyConflict,
    normalize_idempotency_key,
    resolve_idempotent_suggestion,
    resolve_idempotent_suggestion_from_validation_summary,
)
from ..proposal_quality import build_proposal_source_quality, validation_status
from ..proposal_validation import build_proposal_validation_summary
from ..runtime_snapshots import (
    alias_tuples_from_snapshot,
    binding_snapshot_status,
    build_runtime_snapshot_payload,
    clear_binding_pending_snapshot,
    mark_binding_snapshot_success,
    publish_binding_runtime_snapshot,
    restore_binding_previous_snapshot,
)
from ..schemas import (
    AliasCreateRequest,
    AliasResponse,
    AliasUpdateRequest,
    ElasticsearchBindingCreateRequest,
    ElasticsearchBindingDryRunDocument,
    ElasticsearchBindingDryRunRequest,
    ElasticsearchBindingDryRunResponse,
    ElasticsearchBindingResponse,
    ElasticsearchBindingUpdateRequest,
    ElasticsearchConnectionStatusResponse,
    ElasticsearchDryRunMatchedAlias,
    ElasticsearchEnrichmentJobCancelRequest,
    ElasticsearchEnrichmentJobCreateRequest,
    ElasticsearchEnrichmentJobResponse,
    ElasticsearchEnrichmentJobRollbackRequest,
    ElasticsearchEvidenceDocument,
    ElasticsearchEvidenceRequest,
    ElasticsearchEvidenceResponse,
    ElasticsearchIndexMappingResponse,
    ElasticsearchIndexResponse,
    ElasticsearchMappingFieldResponse,
    GlobalStopListCreateRequest,
    GlobalStopListEntryResponse,
    GlobalStopListUpdateRequest,
    ProfileCreateRequest,
    ProfileResponse,
    ProfileUpdateRequest,
    ProposalBatchApplyRequest,
    ProposalBatchApplyResponse,
    ProposalBatchSnapshotResponse,
    ProposalSourceQualityResponse,
    RuntimeSnapshotResponse,
    SnapshotExportRequest,
    StopListCreateRequest,
    StopListEntryResponse,
    StopListUpdateRequest,
    SuggestionCreateRequest,
    SuggestionEvidenceRefreshRequest,
    SuggestionResponse,
    SuggestionReviewRequest,
    TermCreateRequest,
    TermResponse,
    TermUpdateRequest,
)
from ..worker_queue import (
    EnrichmentJobQueueError,
    enqueue_elasticsearch_enrichment_job,
)

router = APIRouter(prefix="/v1/governance", tags=["governance"])


@router.get("/profiles", response_model=list[ProfileResponse])
def list_profiles(
    _current_user: AuthContext = Depends(
        require_roles("admin", "moderator", "contributor")
    ),
    session: Session = Depends(get_session),
) -> list[ProfileResponse]:
    """List terminology profiles."""

    profiles = list(
        session.scalars(
            select(TerminologyProfile).order_by(TerminologyProfile.normalized_name)
        )
    )
    return [_profile_response(profile) for profile in profiles]


@router.post(
    "/profiles",
    response_model=ProfileResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_profile_endpoint(
    request: ProfileCreateRequest,
    _admin: AuthContext = Depends(require_roles("admin")),
    session: Session = Depends(get_session),
) -> ProfileResponse:
    """Create a terminology profile."""

    try:
        profile = create_profile(
            session,
            request.name,
            description=request.description,
            actor="api",
        )
        session.commit()
        session.refresh(profile)
        return _profile_response(profile)
    except GovernanceCliError as exc:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except IntegrityError as exc:
        session.rollback()
        raise _integrity_conflict(exc) from exc


@router.patch(
    "/profiles/{profile_name}",
    response_model=ProfileResponse,
)
def update_profile_endpoint(
    profile_name: str,
    request: ProfileUpdateRequest,
    _admin: AuthContext = Depends(require_roles("admin")),
    session: Session = Depends(get_session),
) -> ProfileResponse:
    """Update a terminology profile name or description."""

    profile = _get_profile_or_404(session, profile_name)
    fields = request.model_fields_set

    if "name" in fields and request.name is not None:
        normalized_name = normalize_profile_name(request.name)
        existing = session.scalar(
            select(TerminologyProfile).where(
                TerminologyProfile.normalized_name == normalized_name,
                TerminologyProfile.id != profile.id,
            )
        )
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Profile already exists: {request.name}",
            )
        profile.name = request.name

    if "description" in fields:
        profile.description = request.description

    try:
        session.commit()
        session.refresh(profile)
        return _profile_response(profile)
    except IntegrityError as exc:
        session.rollback()
        raise _integrity_conflict(exc) from exc


@router.delete(
    "/profiles/{profile_name}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_profile_endpoint(
    profile_name: str,
    _admin: AuthContext = Depends(require_roles("admin")),
    session: Session = Depends(get_session),
) -> Response:
    """Delete a terminology profile and its child terms/aliases."""

    profile = _get_profile_or_404(session, profile_name)
    session.delete(profile)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/profiles/{profile_name}/stop-list",
    response_model=list[StopListEntryResponse],
)
def list_profile_stop_list(
    profile_name: str,
    _current_user: AuthContext = Depends(
        require_roles("admin", "moderator", "contributor")
    ),
    session: Session = Depends(get_session),
) -> list[StopListEntryResponse]:
    """List profile-scoped stop-list guardrails."""

    profile = _get_profile_or_404(session, profile_name)
    entries = list(
        session.scalars(
            select(GovernanceStopListEntry)
            .where(GovernanceStopListEntry.profile_id == profile.id)
            .order_by(
                GovernanceStopListEntry.target,
                GovernanceStopListEntry.normalized_value,
            )
        )
    )
    return [_stop_list_response(entry) for entry in entries]


@router.post(
    "/profiles/{profile_name}/stop-list",
    response_model=StopListEntryResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_profile_stop_list_entry(
    profile_name: str,
    request: StopListCreateRequest,
    _editor: AuthContext = Depends(require_roles("admin", "moderator")),
    session: Session = Depends(get_session),
) -> StopListEntryResponse:
    """Create a profile-scoped stop-list entry."""

    profile = _get_profile_or_404(session, profile_name)
    _validate_stop_list_target(request.target)
    normalized_value = normalize_value(request.value)
    _ensure_stop_list_entry_unique(
        session,
        profile,
        normalized_value=normalized_value,
        target=request.target,
    )

    entry = GovernanceStopListEntry(
        profile=profile,
        value=request.value,
        target=request.target,
        reason=request.reason,
        is_active=request.is_active,
    )
    session.add(entry)
    try:
        session.commit()
        session.refresh(entry)
        return _stop_list_response(entry)
    except IntegrityError as exc:
        session.rollback()
        raise _integrity_conflict(exc) from exc


@router.patch(
    "/profiles/{profile_name}/stop-list/{entry_id}",
    response_model=StopListEntryResponse,
)
def update_profile_stop_list_entry(
    profile_name: str,
    entry_id: int,
    request: StopListUpdateRequest,
    _editor: AuthContext = Depends(require_roles("admin", "moderator")),
    session: Session = Depends(get_session),
) -> StopListEntryResponse:
    """Update a profile-scoped stop-list entry."""

    profile = _get_profile_or_404(session, profile_name)
    entry = _get_stop_list_entry_or_404(session, profile, entry_id)
    fields = request.model_fields_set

    next_value = (
        request.value
        if "value" in fields and request.value is not None
        else entry.value
    )
    next_target = (
        request.target
        if "target" in fields and request.target is not None
        else entry.target
    )
    _validate_stop_list_target(next_target)

    if next_value != entry.value or next_target != entry.target:
        _ensure_stop_list_entry_unique(
            session,
            profile,
            normalized_value=normalize_value(next_value),
            target=next_target,
            exclude_id=entry.id,
        )
        entry.value = next_value
        entry.target = next_target

    if "reason" in fields:
        entry.reason = request.reason
    if "is_active" in fields and request.is_active is not None:
        entry.is_active = request.is_active

    try:
        session.commit()
        session.refresh(entry)
        return _stop_list_response(entry)
    except IntegrityError as exc:
        session.rollback()
        raise _integrity_conflict(exc) from exc


@router.delete(
    "/profiles/{profile_name}/stop-list/{entry_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_profile_stop_list_entry(
    profile_name: str,
    entry_id: int,
    _editor: AuthContext = Depends(require_roles("admin", "moderator")),
    session: Session = Depends(get_session),
) -> Response:
    """Delete a profile-scoped stop-list entry."""

    profile = _get_profile_or_404(session, profile_name)
    entry = _get_stop_list_entry_or_404(session, profile, entry_id)
    session.delete(entry)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/global-stop-list",
    response_model=list[GlobalStopListEntryResponse],
)
def list_global_stop_list(
    _current_user: AuthContext = Depends(
        require_roles("admin", "moderator", "contributor")
    ),
    session: Session = Depends(get_session),
) -> list[GlobalStopListEntryResponse]:
    """List global stop-list guardrails."""

    entries = list(
        session.scalars(
            select(GovernanceGlobalStopListEntry).order_by(
                GovernanceGlobalStopListEntry.target,
                GovernanceGlobalStopListEntry.normalized_value,
            )
        )
    )
    return [_global_stop_list_response(entry) for entry in entries]


@router.post(
    "/global-stop-list",
    response_model=GlobalStopListEntryResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_global_stop_list_entry(
    request: GlobalStopListCreateRequest,
    _editor: AuthContext = Depends(require_roles("admin", "moderator")),
    session: Session = Depends(get_session),
) -> GlobalStopListEntryResponse:
    """Create a global stop-list entry."""

    _validate_stop_list_target(request.target)
    normalized_value = normalize_value(request.value)
    _ensure_global_stop_list_entry_unique(
        session,
        normalized_value=normalized_value,
        target=request.target,
    )

    entry = GovernanceGlobalStopListEntry(
        value=request.value,
        target=request.target,
        reason=request.reason,
        is_active=request.is_active,
    )
    session.add(entry)
    try:
        session.commit()
        session.refresh(entry)
        return _global_stop_list_response(entry)
    except IntegrityError as exc:
        session.rollback()
        raise _integrity_conflict(exc) from exc


@router.patch(
    "/global-stop-list/{entry_id}",
    response_model=GlobalStopListEntryResponse,
)
def update_global_stop_list_entry(
    entry_id: int,
    request: GlobalStopListUpdateRequest,
    _editor: AuthContext = Depends(require_roles("admin", "moderator")),
    session: Session = Depends(get_session),
) -> GlobalStopListEntryResponse:
    """Update a global stop-list entry."""

    entry = _get_global_stop_list_entry_or_404(session, entry_id)
    fields = request.model_fields_set

    next_value = (
        request.value
        if "value" in fields and request.value is not None
        else entry.value
    )
    next_target = (
        request.target
        if "target" in fields and request.target is not None
        else entry.target
    )
    _validate_stop_list_target(next_target)

    if next_value != entry.value or next_target != entry.target:
        _ensure_global_stop_list_entry_unique(
            session,
            normalized_value=normalize_value(next_value),
            target=next_target,
            exclude_id=entry.id,
        )
        entry.value = next_value
        entry.target = next_target

    if "reason" in fields:
        entry.reason = request.reason
    if "is_active" in fields and request.is_active is not None:
        entry.is_active = request.is_active

    try:
        session.commit()
        session.refresh(entry)
        return _global_stop_list_response(entry)
    except IntegrityError as exc:
        session.rollback()
        raise _integrity_conflict(exc) from exc


@router.delete(
    "/global-stop-list/{entry_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_global_stop_list_entry(
    entry_id: int,
    _editor: AuthContext = Depends(require_roles("admin", "moderator")),
    session: Session = Depends(get_session),
) -> Response:
    """Delete a global stop-list entry."""

    entry = _get_global_stop_list_entry_or_404(session, entry_id)
    session.delete(entry)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/elasticsearch/connection/status",
    response_model=ElasticsearchConnectionStatusResponse,
)
def get_elasticsearch_connection_status(
    request: Request,
    _current_user: AuthContext = Depends(
        require_roles("admin", "moderator", "contributor")
    ),
) -> ElasticsearchConnectionStatusResponse:
    """Test whether the configured Elasticsearch endpoint is reachable."""

    client = ElasticsearchDiscoveryClient(request.app.state.config)
    if not client.is_configured:
        return ElasticsearchConnectionStatusResponse(
            configured=False,
            ok=False,
            error="Elasticsearch URL is not configured.",
        )

    try:
        info = client.cluster_info()
    except ElasticsearchDiscoveryError as exc:
        return ElasticsearchConnectionStatusResponse(
            configured=True,
            ok=False,
            url=client.url,
            error=str(exc),
        )

    version = info.get("version") if isinstance(info, dict) else None
    version_number = version.get("number") if isinstance(version, dict) else None
    return ElasticsearchConnectionStatusResponse(
        configured=True,
        ok=True,
        url=client.url,
        cluster_name=str(info.get("cluster_name"))
        if isinstance(info, dict) and info.get("cluster_name")
        else None,
        cluster_version=str(version_number) if version_number else None,
    )


@router.get(
    "/elasticsearch/indices",
    response_model=list[ElasticsearchIndexResponse],
)
def list_elasticsearch_indices(
    request: Request,
    _current_user: AuthContext = Depends(
        require_roles("admin", "moderator", "contributor")
    ),
) -> list[ElasticsearchIndexResponse]:
    """List Elasticsearch indices when a connection is configured."""

    client = ElasticsearchDiscoveryClient(request.app.state.config)
    if not client.is_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Elasticsearch URL is not configured.",
        )
    try:
        indices = client.list_indices()
    except ElasticsearchDiscoveryError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    return [ElasticsearchIndexResponse(**item) for item in indices]


@router.get(
    "/elasticsearch/indices/{index_name}/mapping",
    response_model=ElasticsearchIndexMappingResponse,
)
def get_elasticsearch_index_mapping(
    index_name: str,
    request: Request,
    _current_user: AuthContext = Depends(
        require_roles("admin", "moderator", "contributor")
    ),
) -> ElasticsearchIndexMappingResponse:
    """Return flattened mapping fields for one Elasticsearch index."""

    client = ElasticsearchDiscoveryClient(request.app.state.config)
    if not client.is_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Elasticsearch URL is not configured.",
        )
    try:
        fields = client.index_fields(index_name)
    except ElasticsearchDiscoveryError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    return ElasticsearchIndexMappingResponse(
        index_name=index_name,
        fields=[
            ElasticsearchMappingFieldResponse(**field.__dict__) for field in fields
        ],
    )


@router.get(
    "/elasticsearch/bindings",
    response_model=list[ElasticsearchBindingResponse],
)
def list_elasticsearch_bindings(
    profile_name: str | None = Query(default=None),
    _current_user: AuthContext = Depends(
        require_roles("admin", "moderator", "contributor")
    ),
    session: Session = Depends(get_session),
) -> list[ElasticsearchBindingResponse]:
    """List saved Elasticsearch enrichment bindings."""

    query = select(ElasticsearchBinding).join(TerminologyProfile)
    if profile_name is not None:
        profile = _get_profile_or_404(session, profile_name)
        query = query.where(ElasticsearchBinding.profile_id == profile.id)
    bindings = list(
        session.scalars(
            query.order_by(
                ElasticsearchBinding.is_enabled.desc(),
                ElasticsearchBinding.normalized_name,
            )
        )
    )
    return [_elasticsearch_binding_response(binding) for binding in bindings]


@router.post(
    "/elasticsearch/bindings",
    response_model=ElasticsearchBindingResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_elasticsearch_binding(
    request: ElasticsearchBindingCreateRequest,
    _editor: AuthContext = Depends(require_roles("admin", "moderator")),
    session: Session = Depends(get_session),
) -> ElasticsearchBindingResponse:
    """Create a saved Elasticsearch enrichment binding."""

    profile = _get_profile_or_404(session, request.profile_name)
    _validate_elasticsearch_binding_mode(request.mode)
    _validate_elasticsearch_binding_write_strategy(request.write_strategy)
    _validate_elasticsearch_binding_provider("elasticsearch")
    text_fields = _normalize_text_fields(request.text_fields)
    filter_field, filter_value = _normalize_optional_filter(
        request.filter_field, request.filter_value
    )
    timestamp_field, time_window_days = _normalize_time_filter(
        request.timestamp_field, request.time_window_days
    )
    _ensure_elasticsearch_binding_name_unique(
        session,
        normalized_name=normalize_profile_name(request.name),
    )

    binding = ElasticsearchBinding(
        profile=profile,
        name=request.name,
        description=request.description,
        provider="elasticsearch",
        index_name=request.index_name,
        text_fields=text_fields,
        target_field=request.target_field,
        filter_field=filter_field,
        filter_value=filter_value,
        timestamp_field=timestamp_field,
        time_window_days=time_window_days,
        mode=request.mode,
        write_strategy=request.write_strategy,
        is_enabled=request.is_enabled,
    )
    session.add(binding)
    try:
        session.commit()
        session.refresh(binding)
        return _elasticsearch_binding_response(binding)
    except IntegrityError as exc:
        session.rollback()
        raise _integrity_conflict(exc) from exc


@router.patch(
    "/elasticsearch/bindings/{binding_id}",
    response_model=ElasticsearchBindingResponse,
)
def update_elasticsearch_binding(
    binding_id: int,
    request: ElasticsearchBindingUpdateRequest,
    _editor: AuthContext = Depends(require_roles("admin", "moderator")),
    session: Session = Depends(get_session),
) -> ElasticsearchBindingResponse:
    """Update a saved Elasticsearch enrichment binding."""

    binding = _get_elasticsearch_binding_or_404(session, binding_id)
    fields = request.model_fields_set

    if "profile_name" in fields and request.profile_name is not None:
        binding.profile = _get_profile_or_404(session, request.profile_name)

    if "name" in fields and request.name is not None:
        _ensure_elasticsearch_binding_name_unique(
            session,
            normalized_name=normalize_profile_name(request.name),
            exclude_id=binding.id,
        )
        binding.name = request.name

    if "description" in fields:
        binding.description = request.description

    if "index_name" in fields and request.index_name is not None:
        binding.index_name = request.index_name

    if "text_fields" in fields and request.text_fields is not None:
        binding.text_fields = _normalize_text_fields(request.text_fields)

    if "target_field" in fields and request.target_field is not None:
        binding.target_field = request.target_field

    next_filter_field = (
        request.filter_field if "filter_field" in fields else binding.filter_field
    )
    next_filter_value = (
        request.filter_value if "filter_value" in fields else binding.filter_value
    )
    if "filter_field" in fields or "filter_value" in fields:
        binding.filter_field, binding.filter_value = _normalize_optional_filter(
            next_filter_field, next_filter_value
        )

    next_timestamp_field = (
        request.timestamp_field
        if "timestamp_field" in fields
        else binding.timestamp_field
    )
    next_time_window_days = (
        request.time_window_days
        if "time_window_days" in fields
        else binding.time_window_days
    )
    if "timestamp_field" in fields or "time_window_days" in fields:
        binding.timestamp_field, binding.time_window_days = _normalize_time_filter(
            next_timestamp_field, next_time_window_days
        )

    if "mode" in fields and request.mode is not None:
        _validate_elasticsearch_binding_mode(request.mode)
        binding.mode = request.mode

    if "write_strategy" in fields and request.write_strategy is not None:
        _validate_elasticsearch_binding_write_strategy(request.write_strategy)
        binding.write_strategy = request.write_strategy

    if "is_enabled" in fields and request.is_enabled is not None:
        binding.is_enabled = request.is_enabled

    try:
        session.commit()
        session.refresh(binding)
        return _elasticsearch_binding_response(binding)
    except IntegrityError as exc:
        session.rollback()
        raise _integrity_conflict(exc) from exc


@router.delete(
    "/elasticsearch/bindings/{binding_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_elasticsearch_binding(
    binding_id: int,
    _editor: AuthContext = Depends(require_roles("admin", "moderator")),
    session: Session = Depends(get_session),
) -> Response:
    """Delete a saved Elasticsearch enrichment binding."""

    binding = _get_elasticsearch_binding_or_404(session, binding_id)
    session.delete(binding)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/elasticsearch/bindings/{binding_id}/dry-run",
    response_model=ElasticsearchBindingDryRunResponse,
)
def dry_run_elasticsearch_binding(
    binding_id: int,
    request: Request,
    request_body: ElasticsearchBindingDryRunRequest | None = Body(default=None),
    _current_user: AuthContext = Depends(
        require_roles("admin", "moderator", "contributor")
    ),
    session: Session = Depends(get_session),
) -> ElasticsearchBindingDryRunResponse:
    """Preview enrichment for a binding without writing to Elasticsearch."""

    binding = _get_elasticsearch_binding_or_404(session, binding_id)
    if not binding.is_enabled:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Elasticsearch binding is disabled.",
        )

    limit = (request_body or ElasticsearchBindingDryRunRequest()).limit
    client = ElasticsearchDiscoveryClient(request.app.state.config)
    if not client.is_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Elasticsearch URL is not configured.",
        )

    try:
        hits = client.search_documents(
            index_name=binding.index_name,
            text_fields=list(binding.text_fields),
            limit=limit,
            filter_field=binding.filter_field,
            filter_value=binding.filter_value,
            timestamp_field=binding.timestamp_field,
            time_window_days=binding.time_window_days,
        )
    except ElasticsearchDiscoveryError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    alias_entries = _active_alias_entries_for_profile(session, binding.profile)
    snapshot_payload = build_runtime_snapshot_payload(session, binding.profile)
    documents: list[ElasticsearchBindingDryRunDocument] = []
    for hit in hits:
        text = compose_source_text(hit.source, list(binding.text_fields))
        matched_aliases = _match_alias_entries(text, alias_entries)
        would_write_payload = _dry_run_payload(
            binding,
            matched_aliases,
            snapshot_version=str(snapshot_payload["version"]),
        )
        preview_fields = list(binding.text_fields)
        if binding.filter_field:
            preview_fields = [*preview_fields, binding.filter_field]
        if binding.timestamp_field:
            preview_fields = [*preview_fields, binding.timestamp_field]
        documents.append(
            ElasticsearchBindingDryRunDocument(
                document_id=hit.id,
                index_name=hit.index,
                text_preview=text[:500],
                source_preview=source_preview(hit.source, preview_fields),
                matched_aliases=matched_aliases,
                would_write={binding.target_field: would_write_payload},
            )
        )

    warnings: list[str] = []
    if not hits:
        warnings.append("No sample documents matched this binding.")
    if binding.mode == "write":
        warnings.append(
            "Dry-run is read-only even though this binding is configured for write mode."
        )

    return ElasticsearchBindingDryRunResponse(
        binding=_elasticsearch_binding_response(binding),
        limit=limit,
        documents=documents,
        warnings=warnings,
    )


@router.post(
    "/elasticsearch/bindings/{binding_id}/evidence",
    response_model=ElasticsearchEvidenceResponse,
)
def find_elasticsearch_evidence(
    binding_id: int,
    request_body: ElasticsearchEvidenceRequest,
    request: Request,
    _current_user: AuthContext = Depends(
        require_roles("admin", "moderator", "contributor")
    ),
    session: Session = Depends(get_session),
) -> ElasticsearchEvidenceResponse:
    """Find bounded read-only evidence snippets for a term or alias."""

    binding = _get_elasticsearch_binding_or_404(session, binding_id)
    return _build_elasticsearch_evidence_response(
        request=request,
        session=session,
        binding=binding,
        request_body=request_body,
    )


@router.post(
    "/elasticsearch/bindings/{binding_id}/jobs",
    response_model=ElasticsearchEnrichmentJobResponse,
    status_code=status.HTTP_201_CREATED,
)
def start_elasticsearch_enrichment_job(
    binding_id: int,
    request: Request,
    request_body: ElasticsearchEnrichmentJobCreateRequest | None = Body(default=None),
    current_user: AuthContext = Depends(require_roles("admin", "moderator")),
    session: Session = Depends(get_session),
) -> ElasticsearchEnrichmentJobResponse:
    """Start an enrichment job for one Elasticsearch binding."""

    request_body = request_body or ElasticsearchEnrichmentJobCreateRequest()
    binding = _get_elasticsearch_binding_or_404(session, binding_id)
    if not binding.is_enabled:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Elasticsearch binding is disabled.",
        )
    if binding.mode != "write":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Elasticsearch binding must be in write mode before starting an enrichment job.",
        )

    client = ElasticsearchDiscoveryClient(request.app.state.config)
    if not client.is_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Elasticsearch URL is not configured.",
        )

    snapshot_payload = build_runtime_snapshot_payload(
        session,
        binding.profile,
        snapshot_version=request_body.snapshot_version,
    )
    previous_successful_job_id = binding.last_successful_job_id
    job = ElasticsearchEnrichmentJob(
        binding=binding,
        profile=binding.profile,
        status="queued",
        write_strategy=binding.write_strategy,
        source_index=binding.index_name,
        target_index=_job_target_index(binding, request_body.target_index_name),
        alias_name=_job_alias_name(binding, request_body.alias_name),
        snapshot_version=str(snapshot_payload["version"]),
        snapshot_json=snapshot_payload,
        previous_snapshot_version=binding.last_successful_snapshot_version,
        previous_snapshot_json=binding.runtime_snapshot_json,
        requested_by=current_user.username,
        result_json={},
    )
    binding.pending_snapshot_version = job.snapshot_version
    session.add(job)
    session.flush()
    if (
        binding.write_strategy == "reindex_alias_swap"
        and not request_body.target_index_name
    ):
        job.target_index = _default_reindex_target_name(binding, job.id)

    chunk_size = request_body.chunk_size or min(
        request.app.state.config.enrichment_chunk_size,
        request_body.max_documents,
    )
    job.result_json = {
        "job_backend": request.app.state.config.enrichment_jobs_backend,
        "max_documents": request_body.max_documents,
        "chunk_size": chunk_size,
        "snapshot_version": job.snapshot_version,
        "snapshot_aliases_total": len(
            (job.snapshot_json or {}).get("alias_entries") or []
        ),
        "previous_snapshot_version": job.previous_snapshot_version,
        "previous_successful_job_id": previous_successful_job_id,
    }

    if request.app.state.config.enrichment_jobs_backend == "celery":
        session.commit()
        session.refresh(job)
        try:
            queued_task = enqueue_elasticsearch_enrichment_job(
                config=request.app.state.config,
                job_id=job.id,
            )
        except EnrichmentJobQueueError as exc:
            job.status = "failed"
            job.error_message = str(exc)
            job.finished_at = utc_now()
            clear_binding_pending_snapshot(binding)
            session.commit()
            session.refresh(job)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(exc),
            ) from exc
        job.result_json = {
            **(job.result_json or {}),
            "celery_task_id": queued_task.task_id,
            "celery_queue": queued_task.queue,
        }
        session.commit()
        session.refresh(job)
        return _elasticsearch_enrichment_job_response(job)

    job.status = "running"
    job.started_at = utc_now()
    session.commit()
    session.refresh(job)

    try:
        result = _execute_elasticsearch_enrichment_job(
            client=client,
            session=session,
            binding=binding,
            job=job,
            max_documents=request_body.max_documents,
        )
    except ElasticsearchDiscoveryError as exc:
        job.status = "failed"
        job.error_message = str(exc)
        job.finished_at = utc_now()
        clear_binding_pending_snapshot(binding)
        session.commit()
        session.refresh(job)
        return _elasticsearch_enrichment_job_response(job)

    result = {**result, "job_backend": "sync"}
    job.status = "succeeded"
    job.documents_seen = result["documents_seen"]
    job.documents_enriched = result["documents_enriched"]
    job.documents_failed = result.get("documents_failed", 0)
    job.result_json = result
    job.finished_at = utc_now()
    mark_binding_snapshot_success(
        binding=binding, job=job, completed_at=job.finished_at
    )
    session.commit()
    session.refresh(job)
    return _elasticsearch_enrichment_job_response(job)


@router.get(
    "/elasticsearch/jobs",
    response_model=list[ElasticsearchEnrichmentJobResponse],
)
def list_elasticsearch_enrichment_jobs(
    binding_id: int | None = Query(default=None),
    _current_user: AuthContext = Depends(
        require_roles("admin", "moderator", "contributor")
    ),
    session: Session = Depends(get_session),
) -> list[ElasticsearchEnrichmentJobResponse]:
    """List Elasticsearch enrichment jobs."""

    query = select(ElasticsearchEnrichmentJob).join(ElasticsearchBinding)
    if binding_id is not None:
        query = query.where(ElasticsearchEnrichmentJob.binding_id == binding_id)
    jobs = list(
        session.scalars(
            query.order_by(
                ElasticsearchEnrichmentJob.created_at.desc(),
                ElasticsearchEnrichmentJob.id.desc(),
            )
        )
    )
    return [_elasticsearch_enrichment_job_response(job) for job in jobs]


@router.get(
    "/elasticsearch/jobs/{job_id}",
    response_model=ElasticsearchEnrichmentJobResponse,
)
def get_elasticsearch_enrichment_job(
    job_id: int,
    _current_user: AuthContext = Depends(
        require_roles("admin", "moderator", "contributor")
    ),
    session: Session = Depends(get_session),
) -> ElasticsearchEnrichmentJobResponse:
    """Return one Elasticsearch enrichment job."""

    job = _get_elasticsearch_enrichment_job_or_404(session, job_id)
    return _elasticsearch_enrichment_job_response(job)


@router.post(
    "/elasticsearch/jobs/{job_id}/cancel",
    response_model=ElasticsearchEnrichmentJobResponse,
)
def cancel_elasticsearch_enrichment_job(
    job_id: int,
    request_body: ElasticsearchEnrichmentJobCancelRequest | None = Body(default=None),
    current_user: AuthContext = Depends(require_roles("admin", "moderator")),
    session: Session = Depends(get_session),
) -> ElasticsearchEnrichmentJobResponse:
    """Request safe cancellation for a queued or running enrichment job."""

    job = _get_elasticsearch_enrichment_job_or_404(session, job_id)
    request_body = request_body or ElasticsearchEnrichmentJobCancelRequest()
    now = utc_now()
    cancellation = {
        "requested_by": current_user.username,
        "requested_at": now.isoformat(),
    }
    if request_body.reason:
        cancellation["reason"] = request_body.reason

    if job.status == "queued":
        job.status = "cancelled"
        job.finished_at = now
        job.error_message = None
        cancellation["cancelled_at"] = now.isoformat()
    elif job.status == "running":
        job.status = "cancel_requested"
    elif job.status == "cancel_requested":
        pass
    else:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot cancel enrichment job with status: {job.status}",
        )

    job.result_json = {
        **(job.result_json or {}),
        "cancellation": cancellation,
    }
    session.commit()
    session.refresh(job)
    return _elasticsearch_enrichment_job_response(job)


@router.post(
    "/elasticsearch/jobs/{job_id}/rollback",
    response_model=ElasticsearchEnrichmentJobResponse,
)
def rollback_elasticsearch_enrichment_job(
    job_id: int,
    request: Request,
    request_body: ElasticsearchEnrichmentJobRollbackRequest | None = Body(default=None),
    current_user: AuthContext = Depends(require_roles("admin", "moderator")),
    session: Session = Depends(get_session),
) -> ElasticsearchEnrichmentJobResponse:
    """Safely roll back a completed reindex+alias-swap enrichment job."""

    job = _get_elasticsearch_enrichment_job_or_404(session, job_id)
    request_body = request_body or ElasticsearchEnrichmentJobRollbackRequest()
    rollout = _validated_rollback_rollout(job)
    alias_name = str(rollout["alias_name"])
    rollback_index = str(rollout["rollback_candidate_index"])
    expected_current_indices = _rollout_expected_current_indices(rollout, job)

    try:
        client = ElasticsearchDiscoveryClient(request.app.state.config)
        if not client.is_configured:
            raise ElasticsearchDiscoveryError("Elasticsearch URL is not configured.")
        current_alias_indices = client.alias_indices(alias_name=alias_name)
        if sorted(current_alias_indices) != sorted(expected_current_indices):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Cannot rollback alias because current alias indices do not "
                    "match the expected post-rollout state."
                ),
            )
        alias_result = client.swap_alias(
            alias_name=alias_name,
            target_index=rollback_index,
        )
        alias_indices_after = client.alias_indices(alias_name=alias_name)
    except HTTPException:
        raise
    except ElasticsearchDiscoveryError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    now = utc_now()
    rollback_metadata = {
        "status": "rolled_back",
        "requested_by": current_user.username,
        "requested_at": now.isoformat(),
        "completed_at": now.isoformat(),
        "reason": request_body.reason,
        "alias_name": alias_name,
        "from_indices": current_alias_indices,
        "rollback_candidate_index": rollback_index,
        "alias_indices_after_rollback": alias_indices_after,
        "alias_result": alias_result,
    }
    result_json = dict(job.result_json or {})
    result_json["rollout"] = {
        **rollout,
        "status": "rolled_back",
        "rollback_available": False,
        "rollback_completed": True,
        "rollback_completed_at": now.isoformat(),
        "rollback": rollback_metadata,
        "rollback_hint": (
            f"Rollback completed: alias {alias_name} now points to {rollback_index}."
        ),
    }
    job.result_json = result_json
    restore_binding_previous_snapshot(binding=job.binding, job=job)
    session.commit()
    session.refresh(job)
    return _elasticsearch_enrichment_job_response(job)


@router.get(
    "/profiles/{profile_name}/terms",
    response_model=list[TermResponse],
)
def list_profile_terms(
    profile_name: str,
    _current_user: AuthContext = Depends(
        require_roles("admin", "moderator", "contributor")
    ),
    session: Session = Depends(get_session),
) -> list[TermResponse]:
    """List canonical terms and aliases for a terminology profile."""

    profile = _get_profile_or_404(session, profile_name)
    terms = list(
        session.scalars(
            select(CanonicalTerm)
            .where(CanonicalTerm.profile_id == profile.id)
            .order_by(CanonicalTerm.slot, CanonicalTerm.normalized_value)
        )
    )
    for term in terms:
        term.aliases.sort(key=lambda alias: alias.normalized_alias)
    return [_term_response(term) for term in terms]


@router.post(
    "/profiles/{profile_name}/terms",
    response_model=TermResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_profile_term(
    profile_name: str,
    request: TermCreateRequest,
    _editor: AuthContext = Depends(require_roles("admin", "moderator")),
    session: Session = Depends(get_session),
) -> TermResponse:
    """Add a canonical term to a terminology profile."""

    profile = _get_profile_or_404(session, profile_name)
    _ensure_not_stoplisted(
        session,
        profile,
        value=request.canonical_value,
        target="canonical",
        entity_name="Canonical term",
    )

    try:
        term = add_term(
            session,
            profile_name,
            request.canonical_value,
            slot=request.slot,
            description=request.description,
            status=request.status,
            actor="api",
        )
        session.commit()
        session.refresh(term)
        term.aliases.sort(key=lambda alias: alias.normalized_alias)
        return _term_response(term)
    except GovernanceCliError as exc:
        session.rollback()
        status_code = (
            status.HTTP_404_NOT_FOUND
            if str(exc).startswith("Profile not found")
            else status.HTTP_409_CONFLICT
        )
        raise HTTPException(status_code=status_code, detail=str(exc))
    except IntegrityError as exc:
        session.rollback()
        raise _integrity_conflict(exc) from exc


@router.get(
    "/profiles/{profile_name}/terms/{canonical_value}",
    response_model=TermResponse,
)
def get_profile_term(
    profile_name: str,
    canonical_value: str,
    _current_user: AuthContext = Depends(
        require_roles("admin", "moderator", "contributor")
    ),
    session: Session = Depends(get_session),
) -> TermResponse:
    """Return a canonical term and its aliases."""

    profile = _get_profile_or_404(session, profile_name)
    try:
        term = get_term(session, profile, canonical_value)
    except GovernanceCliError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    term.aliases.sort(key=lambda alias: alias.normalized_alias)
    return _term_response(term)


@router.patch(
    "/profiles/{profile_name}/terms/{canonical_value}",
    response_model=TermResponse,
)
def update_profile_term(
    profile_name: str,
    canonical_value: str,
    request: TermUpdateRequest,
    _editor: AuthContext = Depends(require_roles("admin", "moderator")),
    session: Session = Depends(get_session),
) -> TermResponse:
    """Update a canonical term inside a terminology profile."""

    profile = _get_profile_or_404(session, profile_name)
    try:
        term = get_term(session, profile, canonical_value)
    except GovernanceCliError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    fields = request.model_fields_set

    if "status" in fields and request.status is not None:
        _validate_status(request.status, TERM_STATUSES, "term")
        term.status = request.status

    if "canonical_value" in fields and request.canonical_value is not None:
        _ensure_not_stoplisted(
            session,
            profile,
            value=request.canonical_value,
            target="canonical",
            entity_name="Canonical term",
        )
        normalized_value = normalize_value(request.canonical_value)
        existing = session.scalar(
            select(CanonicalTerm).where(
                CanonicalTerm.profile_id == profile.id,
                CanonicalTerm.normalized_value == normalized_value,
                CanonicalTerm.id != term.id,
            )
        )
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Canonical term already exists in profile {profile.name!r}: "
                    f"{request.canonical_value}"
                ),
            )
        term.canonical_value = request.canonical_value

    if "slot" in fields and request.slot is not None:
        term.slot = request.slot

    if "description" in fields:
        term.description = request.description

    try:
        session.commit()
        session.refresh(term)
        term.aliases.sort(key=lambda alias: alias.normalized_alias)
        return _term_response(term)
    except IntegrityError as exc:
        session.rollback()
        raise _integrity_conflict(exc) from exc


@router.delete(
    "/profiles/{profile_name}/terms/{canonical_value}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_profile_term(
    profile_name: str,
    canonical_value: str,
    _editor: AuthContext = Depends(require_roles("admin", "moderator")),
    session: Session = Depends(get_session),
) -> Response:
    """Delete a canonical term and its aliases."""

    profile = _get_profile_or_404(session, profile_name)
    try:
        term = get_term(session, profile, canonical_value)
    except GovernanceCliError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    session.delete(term)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/profiles/{profile_name}/terms/{canonical_value}/aliases",
    response_model=AliasResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_term_alias(
    profile_name: str,
    canonical_value: str,
    request: AliasCreateRequest,
    _editor: AuthContext = Depends(require_roles("admin", "moderator")),
    session: Session = Depends(get_session),
) -> AliasResponse:
    """Add an alias to a canonical term."""

    profile = _get_profile_or_404(session, profile_name)
    _ensure_not_stoplisted(
        session,
        profile,
        value=request.alias_value,
        target="alias",
        entity_name="Alias",
    )

    try:
        alias = add_alias(
            session,
            profile_name,
            canonical_value,
            request.alias_value,
            confidence=request.confidence,
            status=request.status,
            notes=request.notes,
            actor="api",
        )
        session.commit()
        session.refresh(alias)
        return _alias_response(alias)
    except GovernanceCliError as exc:
        session.rollback()
        message = str(exc)
        status_code = (
            status.HTTP_404_NOT_FOUND
            if message.startswith("Profile not found")
            or message.startswith("Canonical term not found")
            else status.HTTP_409_CONFLICT
        )
        raise HTTPException(status_code=status_code, detail=message)
    except IntegrityError as exc:
        session.rollback()
        raise _integrity_conflict(exc) from exc


@router.patch(
    "/profiles/{profile_name}/terms/{canonical_value}/aliases/{alias_id}",
    response_model=AliasResponse,
)
def update_term_alias(
    profile_name: str,
    canonical_value: str,
    alias_id: int,
    request: AliasUpdateRequest,
    _editor: AuthContext = Depends(require_roles("admin", "moderator")),
    session: Session = Depends(get_session),
) -> AliasResponse:
    """Update an alias attached to a canonical term."""

    profile = _get_profile_or_404(session, profile_name)
    try:
        term = get_term(session, profile, canonical_value)
    except GovernanceCliError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    alias = _get_alias_or_404(session, term, alias_id)

    fields = request.model_fields_set

    if "status" in fields and request.status is not None:
        _validate_status(request.status, ALIAS_STATUSES, "alias")
        alias.status = request.status

    if "alias_value" in fields and request.alias_value is not None:
        _ensure_not_stoplisted(
            session,
            profile,
            value=request.alias_value,
            target="alias",
            entity_name="Alias",
        )
        normalized_alias = normalize_value(request.alias_value)
        existing = session.scalar(
            select(TermAlias).where(
                TermAlias.profile_id == profile.id,
                TermAlias.normalized_alias == normalized_alias,
                TermAlias.id != alias.id,
            )
        )
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Alias already exists in profile {profile.name!r}: {request.alias_value}",
            )
        alias.alias_value = request.alias_value

    if "confidence" in fields and request.confidence is not None:
        alias.confidence = request.confidence

    if "notes" in fields:
        alias.notes = request.notes

    try:
        session.commit()
        session.refresh(alias)
        return _alias_response(alias)
    except IntegrityError as exc:
        session.rollback()
        raise _integrity_conflict(exc) from exc


@router.delete(
    "/profiles/{profile_name}/terms/{canonical_value}/aliases/{alias_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_term_alias(
    profile_name: str,
    canonical_value: str,
    alias_id: int,
    _editor: AuthContext = Depends(require_roles("admin", "moderator")),
    session: Session = Depends(get_session),
) -> Response:
    """Delete an alias attached to a canonical term."""

    profile = _get_profile_or_404(session, profile_name)
    try:
        term = get_term(session, profile, canonical_value)
    except GovernanceCliError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    alias = _get_alias_or_404(session, term, alias_id)
    session.delete(alias)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/proposals/source-quality",
    response_model=list[ProposalSourceQualityResponse],
)
def list_proposal_source_quality(
    profile_name: str | None = Query(default=None, min_length=1, max_length=128),
    proposal_source_type: str | None = Query(default=None, max_length=32),
    proposal_source_name: str | None = Query(default=None, max_length=128),
    _current_user: AuthContext = Depends(require_roles("admin", "moderator")),
    session: Session = Depends(get_session),
) -> list[ProposalSourceQualityResponse]:
    """Return aggregate quality signals for proposal sources.

    This endpoint is intentionally computed from persisted proposal state rather
    than Prometheus counters, so reviewers can inspect source quality after
    restarts and across manual/agent proposal flows.
    """

    if proposal_source_type is not None:
        _validate_status(
            proposal_source_type,
            PROPOSAL_SOURCE_TYPES,
            "proposal source type",
        )
    rows = build_proposal_source_quality(
        session,
        profile_name=profile_name,
        proposal_source_type=proposal_source_type,
        proposal_source_name=proposal_source_name,
    )
    return [
        ProposalSourceQualityResponse(
            proposal_source_type=row.proposal_source_type,
            proposal_source_name=row.proposal_source_name,
            proposals_total=row.proposals_total,
            pending=row.pending,
            approved=row.approved,
            rejected=row.rejected,
            validation_passed=row.validation_passed,
            validation_warning=row.validation_warning,
            validation_blocked=row.validation_blocked,
            validation_unknown=row.validation_unknown,
            approval_rate=row.approval_rate,
            rejection_rate=row.rejection_rate,
            blocked_rate=row.blocked_rate,
            average_confidence=row.average_confidence,
        )
        for row in rows
    ]


@router.get(
    "/profiles/{profile_name}/suggestions",
    response_model=list[SuggestionResponse],
)
def list_profile_suggestions(
    profile_name: str,
    status_filter: str | None = Query(default=None, alias="status"),
    _current_user: AuthContext = Depends(
        require_roles("admin", "moderator", "contributor")
    ),
    session: Session = Depends(get_session),
) -> list[SuggestionResponse]:
    """List governance suggestions for a terminology profile."""

    profile = _get_profile_or_404(session, profile_name)
    if status_filter is not None:
        _validate_status(status_filter, SUGGESTION_STATUSES, "suggestion")
    query = select(GovernanceSuggestion).where(
        GovernanceSuggestion.profile_id == profile.id
    )
    if status_filter is not None:
        query = query.where(GovernanceSuggestion.status == status_filter)
    suggestions = list(
        session.scalars(
            query.order_by(
                GovernanceSuggestion.status,
                GovernanceSuggestion.updated_at.desc(),
                GovernanceSuggestion.id.desc(),
            )
        )
    )
    return [_suggestion_response(suggestion) for suggestion in suggestions]


@router.post(
    "/profiles/{profile_name}/suggestions",
    response_model=SuggestionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_profile_suggestion(
    profile_name: str,
    request: SuggestionCreateRequest,
    response: Response,
    current_user: AuthContext = Depends(
        require_roles("admin", "moderator", "contributor")
    ),
    session: Session = Depends(get_session),
) -> SuggestionResponse:
    """Create a pending governance suggestion without mutating active terms."""

    profile = _get_profile_or_404(session, profile_name)
    _validate_status(request.source, SUGGESTION_SOURCES, "suggestion source")
    _validate_status(request.suggestion_type, SUGGESTION_TYPES, "suggestion type")
    _validate_status(
        request.proposal_source_type,
        PROPOSAL_SOURCE_TYPES,
        "proposal source type",
    )

    binding_id = request.binding_id
    if request.binding_id is not None:
        binding = _get_elasticsearch_binding_or_404(session, request.binding_id)
        if binding.profile_id != profile.id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Proposal binding must belong to the suggestion profile.",
            )
        binding_id = binding.id

    idempotency_key = normalize_idempotency_key(request.idempotency_key)
    try:
        existing_suggestion = resolve_idempotent_suggestion(
            session,
            profile=profile,
            idempotency_key=idempotency_key,
            suggestion_type=request.suggestion_type,
            canonical_value=request.canonical_value,
            alias_value=request.alias_value,
            slot=request.slot,
            binding_id=binding_id,
            proposal_source_type=request.proposal_source_type,
        )
    except ProposalIdempotencyConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    if existing_suggestion is not None:
        response.status_code = status.HTTP_200_OK
        record_proposal_submission(
            source_type=existing_suggestion.proposal_source_type,
            suggestion_type=existing_suggestion.suggestion_type,
            validation_status=validation_status(
                existing_suggestion.validation_summary_json
            ),
            outcome="idempotent_retry",
        )
        return _suggestion_response(existing_suggestion)

    if request.suggestion_type == "alias":
        if request.alias_value is None or not request.alias_value.strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Alias suggestions require alias_value.",
            )
        _ensure_not_stoplisted(
            session,
            profile,
            value=request.alias_value,
            target="alias",
            entity_name="Alias suggestion",
        )
    elif request.suggestion_type == "canonical_term":
        _ensure_not_stoplisted(
            session,
            profile,
            value=request.canonical_value,
            target="canonical",
            entity_name="Canonical term suggestion",
        )
        if request.alias_value is not None and request.alias_value.strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Canonical term suggestions must not include alias_value.",
            )
        existing = session.scalar(
            select(CanonicalTerm).where(
                CanonicalTerm.profile_id == profile.id,
                CanonicalTerm.normalized_value
                == normalize_value(request.canonical_value),
            )
        )
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Canonical term already exists in profile {profile.name!r}: "
                    f"{request.canonical_value}"
                ),
            )

    validation_summary = request.validation_summary
    if validation_summary is None:
        validation_summary = build_proposal_validation_summary(
            session,
            profile,
            suggestion_type=request.suggestion_type,
            canonical_value=request.canonical_value,
            alias_value=request.alias_value,
            slot=request.slot,
            confidence=request.confidence,
            proposal_source_type=request.proposal_source_type,
            proposal_source_name=request.proposal_source_name,
            idempotency_key=idempotency_key,
            source_payload=request.source_payload,
        )
        try:
            existing_suggestion = resolve_idempotent_suggestion_from_validation_summary(
                session,
                validation_summary,
                suggestion_type=request.suggestion_type,
                canonical_value=request.canonical_value,
                alias_value=request.alias_value,
                slot=request.slot,
                binding_id=binding_id,
                proposal_source_type=request.proposal_source_type,
            )
        except ProposalIdempotencyConflict as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
            ) from exc
        if existing_suggestion is not None:
            response.status_code = status.HTTP_200_OK
            record_proposal_submission(
                source_type=existing_suggestion.proposal_source_type,
                suggestion_type=existing_suggestion.suggestion_type,
                validation_status=validation_status(
                    existing_suggestion.validation_summary_json
                ),
                outcome="idempotent_retry",
            )
            return _suggestion_response(existing_suggestion)

    suggestion = GovernanceSuggestion(
        profile=profile,
        suggestion_type=request.suggestion_type,
        canonical_value=request.canonical_value,
        alias_value=request.alias_value,
        slot=request.slot,
        description=request.description,
        confidence=request.confidence,
        source=request.source,
        context=request.context,
        binding_id=binding_id,
        proposal_source_type=request.proposal_source_type,
        proposal_source_name=request.proposal_source_name,
        idempotency_key=idempotency_key,
        source_payload_json=request.source_payload,
        validation_summary_json=validation_summary,
        status="pending",
        created_by=current_user.username,
    )
    session.add(suggestion)
    try:
        session.commit()
        session.refresh(suggestion)
        record_proposal_submission(
            source_type=suggestion.proposal_source_type,
            suggestion_type=suggestion.suggestion_type,
            validation_status=validation_status(suggestion.validation_summary_json),
            outcome="created",
        )
        return _suggestion_response(suggestion)
    except IntegrityError as exc:
        session.rollback()
        try:
            existing_suggestion = resolve_idempotent_suggestion(
                session,
                profile=profile,
                idempotency_key=idempotency_key,
                suggestion_type=request.suggestion_type,
                canonical_value=request.canonical_value,
                alias_value=request.alias_value,
                slot=request.slot,
                binding_id=binding_id,
                proposal_source_type=request.proposal_source_type,
            )
        except ProposalIdempotencyConflict as conflict_exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(conflict_exc),
            ) from conflict_exc
        if existing_suggestion is not None:
            response.status_code = status.HTTP_200_OK
            record_proposal_submission(
                source_type=existing_suggestion.proposal_source_type,
                suggestion_type=existing_suggestion.suggestion_type,
                validation_status=validation_status(
                    existing_suggestion.validation_summary_json
                ),
                outcome="idempotent_retry",
            )
            return _suggestion_response(existing_suggestion)
        raise _integrity_conflict(exc) from exc


@router.post(
    "/profiles/{profile_name}/suggestions/{suggestion_id}/evidence/refresh",
    response_model=SuggestionResponse,
)
def refresh_suggestion_evidence(
    profile_name: str,
    suggestion_id: int,
    request_body: SuggestionEvidenceRefreshRequest,
    request: Request,
    current_user: AuthContext = Depends(
        require_roles("admin", "moderator", "contributor")
    ),
    session: Session = Depends(get_session),
) -> SuggestionResponse:
    """Refresh and save an Elasticsearch evidence snapshot for a pending suggestion."""

    profile = _get_profile_or_404(session, profile_name)
    suggestion = _get_suggestion_or_404(session, profile, suggestion_id)
    _ensure_pending_suggestion(suggestion)

    binding = _get_elasticsearch_binding_or_404(session, request_body.binding_id)
    if binding.profile_id != profile.id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Evidence binding must belong to the suggestion profile.",
        )

    query = request_body.query
    if query is None:
        query = suggestion.alias_value or suggestion.canonical_value

    evidence_response = _build_elasticsearch_evidence_response(
        request=request,
        session=session,
        binding=binding,
        request_body=ElasticsearchEvidenceRequest(
            query=query,
            canonical_value=suggestion.canonical_value,
            max_documents=request_body.max_documents,
            context_chars=request_body.context_chars,
        ),
    )

    suggestion.evidence_snapshot = _suggestion_evidence_snapshot(evidence_response)
    suggestion.evidence_checked_by = current_user.username
    suggestion.evidence_checked_at = utc_now()

    session.commit()
    session.refresh(suggestion)
    return _suggestion_response(suggestion)


@router.post(
    "/profiles/{profile_name}/suggestions/{suggestion_id}/approve",
    response_model=SuggestionResponse,
)
def approve_profile_suggestion(
    profile_name: str,
    suggestion_id: int,
    request: SuggestionReviewRequest | None = Body(default=None),
    reviewer: AuthContext = Depends(require_roles("admin", "moderator")),
    session: Session = Depends(get_session),
) -> SuggestionResponse:
    """Approve a pending suggestion and create an active alias."""

    request = request or SuggestionReviewRequest()
    profile = _get_profile_or_404(session, profile_name)
    suggestion = _get_suggestion_or_404(session, profile, suggestion_id)
    _ensure_pending_suggestion(suggestion)

    if suggestion.suggestion_type == "alias":
        _approve_alias_suggestion(session, profile, suggestion)
    elif suggestion.suggestion_type == "canonical_term":
        _approve_canonical_term_suggestion(session, profile, suggestion)
    else:  # pragma: no cover - guarded by database/API validation
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Invalid suggestion type: {suggestion.suggestion_type}",
        )

    suggestion.status = "approved"
    suggestion.reviewed_by = reviewer.username
    suggestion.review_comment = request.review_comment
    suggestion.reviewed_at = utc_now()

    try:
        session.commit()
        session.refresh(suggestion)
        record_proposal_review(
            source_type=suggestion.proposal_source_type,
            decision="approved",
        )
        return _suggestion_response(suggestion)
    except IntegrityError as exc:
        session.rollback()
        raise _integrity_conflict(exc) from exc


@router.post(
    "/profiles/{profile_name}/suggestions/{suggestion_id}/reject",
    response_model=SuggestionResponse,
)
def reject_profile_suggestion(
    profile_name: str,
    suggestion_id: int,
    request: SuggestionReviewRequest | None = Body(default=None),
    reviewer: AuthContext = Depends(require_roles("admin", "moderator")),
    session: Session = Depends(get_session),
) -> SuggestionResponse:
    """Reject a pending alias suggestion without changing active aliases."""

    request = request or SuggestionReviewRequest()
    profile = _get_profile_or_404(session, profile_name)
    suggestion = _get_suggestion_or_404(session, profile, suggestion_id)
    _ensure_pending_suggestion(suggestion)

    suggestion.status = "rejected"
    suggestion.reviewed_by = reviewer.username
    suggestion.review_comment = request.review_comment
    suggestion.reviewed_at = utc_now()

    session.commit()
    session.refresh(suggestion)
    record_proposal_review(
        source_type=suggestion.proposal_source_type,
        decision="rejected",
    )
    return _suggestion_response(suggestion)


@router.post(
    "/profiles/{profile_name}/suggestions/apply-batch",
    response_model=ProposalBatchApplyResponse,
)
def apply_profile_suggestion_batch(
    profile_name: str,
    request: ProposalBatchApplyRequest | None = Body(default=None),
    reviewer: AuthContext = Depends(require_roles("admin", "moderator")),
    session: Session = Depends(get_session),
) -> ProposalBatchApplyResponse:
    """Apply pending proposals as one atomic batch and optionally publish a snapshot.

    This endpoint is the headless proposal release path: agents and tools submit
    pending suggestions, then a moderator/admin applies a reviewed set in one
    transaction. When requested, the same transaction pins a fresh runtime
    snapshot on the target binding.
    """

    request = request or ProposalBatchApplyRequest()
    profile = _get_profile_or_404(session, profile_name)
    binding = None
    if request.publish_snapshot and request.binding_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="publish_snapshot requires binding_id.",
        )
    if request.binding_id is not None:
        binding = _get_elasticsearch_binding_or_404(session, request.binding_id)
        if binding.profile_id != profile.id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Proposal batch binding must belong to the profile.",
            )

    suggestions = _pending_suggestions_for_batch(
        session=session,
        profile=profile,
        suggestion_ids=request.suggestion_ids,
    )
    if not suggestions:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No pending suggestions are available for this batch.",
        )

    _ensure_batch_suggestions_are_applyable(suggestions)

    created_terms = 0
    created_aliases = 0
    now = utc_now()
    for suggestion in _ordered_suggestions_for_apply(suggestions):
        if suggestion.suggestion_type == "canonical_term":
            _approve_canonical_term_suggestion(session, profile, suggestion)
            created_terms += 1
        elif suggestion.suggestion_type == "alias":
            _approve_alias_suggestion(session, profile, suggestion)
            created_aliases += 1
        else:  # pragma: no cover - guarded by database/API validation
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Invalid suggestion type: {suggestion.suggestion_type}",
            )
        suggestion.status = "approved"
        suggestion.reviewed_by = reviewer.username
        suggestion.review_comment = request.review_comment
        suggestion.reviewed_at = now

    snapshot_response = ProposalBatchSnapshotResponse(published=False)
    if request.publish_snapshot and binding is not None:
        session.flush()
        snapshot_payload = publish_binding_runtime_snapshot(
            session,
            binding,
            snapshot_version=request.snapshot_version,
        )
        snapshot_response = ProposalBatchSnapshotResponse(
            published=True,
            binding_id=binding.id,
            snapshot_version=str(snapshot_payload.get("version") or ""),
            snapshot_status=binding_snapshot_status(binding),
            checksum=str(snapshot_payload.get("checksum") or ""),
            alias_entries_total=len(alias_tuples_from_snapshot(snapshot_payload)),
        )

    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise _integrity_conflict(exc) from exc

    record_proposal_batch_apply(
        status="applied",
        publish_snapshot=request.publish_snapshot,
        suggestions_count=len(suggestions),
    )
    for suggestion in suggestions:
        record_proposal_review(
            source_type=suggestion.proposal_source_type,
            decision="batch_approved",
        )

    for suggestion in suggestions:
        session.refresh(suggestion)
    if binding is not None:
        session.refresh(binding)
        if snapshot_response.published:
            snapshot_response = ProposalBatchSnapshotResponse(
                published=True,
                binding_id=binding.id,
                snapshot_version=binding.last_successful_snapshot_version,
                snapshot_status=binding_snapshot_status(binding),
                checksum=str(
                    (binding.runtime_snapshot_json or {}).get("checksum") or ""
                ),
                alias_entries_total=len(
                    alias_tuples_from_snapshot(binding.runtime_snapshot_json)
                ),
            )

    requested_ids = (
        list(dict.fromkeys(request.suggestion_ids))
        if request.suggestion_ids is not None
        else [suggestion.id for suggestion in suggestions]
    )
    return ProposalBatchApplyResponse(
        status="applied",
        profile_name=profile.name,
        normalized_profile_name=profile.normalized_name,
        requested_suggestion_ids=requested_ids,
        applied_suggestion_ids=[suggestion.id for suggestion in suggestions],
        created_terms=created_terms,
        created_aliases=created_aliases,
        snapshot=snapshot_response,
        suggestions=[_suggestion_response(suggestion) for suggestion in suggestions],
    )


@router.post(
    "/profiles/{profile_name}/snapshot/export",
    response_model=RuntimeSnapshotResponse,
)
def export_profile_snapshot(
    profile_name: str,
    request: SnapshotExportRequest | None = Body(default=None),
    _publisher: AuthContext = Depends(require_roles("admin", "moderator")),
    session: Session = Depends(get_session),
) -> dict:
    """Build and return a runtime-compatible snapshot for a profile.

    The endpoint does not write files or publish state. It returns the same
    snapshot shape that the runtime packages can consume through
    ``--profile-file`` or ``load_attribute_profile(...)``.
    """

    request = request or SnapshotExportRequest()
    try:
        return build_snapshot(
            session,
            profile_name,
            snapshot_version=request.snapshot_version,
            description=request.description,
        )
    except GovernanceCliError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


def _active_alias_entries_for_profile(
    session: Session, profile: TerminologyProfile
) -> list[tuple[str, str, str, float]]:
    """Return active alias rows not blocked by profile/global stop-list entries."""

    blocked_alias_values = _active_stop_values_for_target(
        session, profile, targets=("alias", "both")
    ) | _active_global_stop_values_for_target(session, targets=("alias", "both"))
    blocked_canonical_values = _active_stop_values_for_target(
        session, profile, targets=("canonical", "both")
    ) | _active_global_stop_values_for_target(session, targets=("canonical", "both"))
    aliases = list(
        session.scalars(
            select(TermAlias)
            .join(CanonicalTerm)
            .where(
                TermAlias.profile_id == profile.id,
                TermAlias.status == "active",
                CanonicalTerm.status == "active",
            )
            .order_by(TermAlias.normalized_alias)
        )
    )
    entries: list[tuple[str, str, str, float]] = []
    for alias in aliases:
        if alias.normalized_alias in blocked_alias_values:
            continue
        if alias.term.normalized_value in blocked_canonical_values:
            continue
        entries.append(
            (
                alias.normalized_alias,
                alias.term.canonical_value,
                alias.term.slot,
                alias.confidence,
            )
        )
    return entries


def _active_stop_values_for_target(
    session: Session, profile: TerminologyProfile, *, targets: tuple[str, ...]
) -> set[str]:
    values = session.scalars(
        select(GovernanceStopListEntry.normalized_value).where(
            GovernanceStopListEntry.profile_id == profile.id,
            GovernanceStopListEntry.is_active.is_(True),
            GovernanceStopListEntry.target.in_(targets),
        )
    )
    return set(values)


def _active_global_stop_values_for_target(
    session: Session, *, targets: tuple[str, ...]
) -> set[str]:
    values = session.scalars(
        select(GovernanceGlobalStopListEntry.normalized_value).where(
            GovernanceGlobalStopListEntry.is_active.is_(True),
            GovernanceGlobalStopListEntry.target.in_(targets),
        )
    )
    return set(values)


def _build_elasticsearch_evidence_response(
    *,
    request: Request,
    session: Session,
    binding: ElasticsearchBinding,
    request_body: ElasticsearchEvidenceRequest,
) -> ElasticsearchEvidenceResponse:
    if not binding.is_enabled:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Elasticsearch binding is disabled.",
        )

    normalized_query = normalize_value(request_body.query)
    if not normalized_query:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Evidence query must contain at least one non-space character.",
        )

    client = ElasticsearchDiscoveryClient(request.app.state.config)
    if not client.is_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Elasticsearch URL is not configured.",
        )

    try:
        hits = client.search_evidence_documents(
            index_name=binding.index_name,
            text_fields=list(binding.text_fields),
            query_text=request_body.query.strip(),
            limit=request_body.max_documents,
            filter_field=binding.filter_field,
            filter_value=binding.filter_value,
            timestamp_field=binding.timestamp_field,
            time_window_days=binding.time_window_days,
        )
    except ElasticsearchDiscoveryError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    documents: list[ElasticsearchEvidenceDocument] = []
    for hit in hits:
        document = _first_evidence_document_for_hit(
            hit_id=hit.id,
            hit_index=hit.index,
            source=hit.source,
            text_fields=list(binding.text_fields),
            query=request_body.query.strip(),
            context_chars=request_body.context_chars,
        )
        if document is not None:
            documents.append(document)
        if len(documents) >= request_body.max_documents:
            break

    warnings = _evidence_warnings(
        session=session,
        binding=binding,
        normalized_query=normalized_query,
        hits_count=len(hits),
        documents_count=len(documents),
    )

    return ElasticsearchEvidenceResponse(
        binding=_elasticsearch_binding_response(binding),
        query=request_body.query.strip(),
        normalized_query=normalized_query,
        canonical_value=request_body.canonical_value,
        max_documents=request_body.max_documents,
        documents=documents,
        warnings=warnings,
    )


def _suggestion_evidence_snapshot(
    evidence_response: ElasticsearchEvidenceResponse,
) -> dict[str, object]:
    binding = evidence_response.binding
    return {
        "binding_id": binding.id,
        "binding_name": binding.name,
        "index_name": binding.index_name,
        "profile_name": binding.profile_name,
        "query": evidence_response.query,
        "normalized_query": evidence_response.normalized_query,
        "canonical_value": evidence_response.canonical_value,
        "max_documents": evidence_response.max_documents,
        "documents": [
            document.model_dump(mode="json") for document in evidence_response.documents
        ],
        "warnings": list(evidence_response.warnings),
    }


def _first_evidence_document_for_hit(
    *,
    hit_id: str,
    hit_index: str,
    source: dict[str, object],
    text_fields: list[str],
    query: str,
    context_chars: int,
) -> ElasticsearchEvidenceDocument | None:
    for field in text_fields:
        for value in get_source_values(source, field):
            fragment = _evidence_fragment(
                value, query=query, context_chars=context_chars
            )
            if fragment is None:
                continue
            return ElasticsearchEvidenceDocument(
                document_id=hit_id,
                index_name=hit_index,
                field=field,
                fragment=fragment["fragment"],
                highlighted_fragment=fragment["highlighted_fragment"],
                matched_text=fragment["matched_text"],
                match_start=fragment["match_start"],
                match_end=fragment["match_end"],
            )
    return None


def _evidence_fragment(
    text: str, *, query: str, context_chars: int
) -> dict[str, object] | None:
    pattern = re.compile(rf"(?<!\w){re.escape(query)}(?!\w)", re.IGNORECASE)
    match = pattern.search(text)
    if match is None:
        return None

    fragment_start = max(0, match.start() - context_chars)
    fragment_end = min(len(text), match.end() + context_chars)
    prefix = "…" if fragment_start > 0 else ""
    suffix = "…" if fragment_end < len(text) else ""
    core = text[fragment_start:fragment_end]
    match_start = len(prefix) + match.start() - fragment_start
    match_end = len(prefix) + match.end() - fragment_start
    fragment = f"{prefix}{core}{suffix}"
    highlighted_fragment = (
        html.escape(fragment[:match_start])
        + "<mark>"
        + html.escape(fragment[match_start:match_end])
        + "</mark>"
        + html.escape(fragment[match_end:])
    )
    return {
        "fragment": fragment,
        "highlighted_fragment": highlighted_fragment,
        "matched_text": match.group(0),
        "match_start": match_start,
        "match_end": match_end,
    }


def _evidence_warnings(
    *,
    session: Session,
    binding: ElasticsearchBinding,
    normalized_query: str,
    hits_count: int,
    documents_count: int,
) -> list[str]:
    warnings: list[str] = []
    if hits_count == 0:
        warnings.append("No Elasticsearch documents matched this evidence query.")
    elif documents_count == 0:
        warnings.append(
            "Elasticsearch returned candidates, but no exact literal evidence matches were found."
        )

    blocked_alias_values = _active_stop_values_for_target(
        session, binding.profile, targets=("alias", "both")
    ) | _active_global_stop_values_for_target(session, targets=("alias", "both"))
    blocked_canonical_values = _active_stop_values_for_target(
        session, binding.profile, targets=("canonical", "both")
    ) | _active_global_stop_values_for_target(session, targets=("canonical", "both"))
    if normalized_query in blocked_alias_values:
        warnings.append("Evidence query is blocked as an alias by an active stop list.")
    if normalized_query in blocked_canonical_values:
        warnings.append(
            "Evidence query is blocked as a canonical value by an active stop list."
        )
    return warnings


def _match_alias_entries(
    text: str, alias_entries: list[tuple[str, str, str, float]]
) -> list[ElasticsearchDryRunMatchedAlias]:
    normalized_text = normalize_value(text)
    matches: list[ElasticsearchDryRunMatchedAlias] = []
    seen: set[tuple[str, str, str]] = set()
    for alias_value, canonical_value, slot, confidence in alias_entries:
        if not alias_value or not _contains_alias(normalized_text, alias_value):
            continue
        key = (alias_value, canonical_value, slot)
        if key in seen:
            continue
        seen.add(key)
        matches.append(
            ElasticsearchDryRunMatchedAlias(
                alias_value=alias_value,
                canonical_value=canonical_value,
                slot=slot,
                matched_text=alias_value,
                confidence=confidence,
            )
        )
    return matches


def _contains_alias(normalized_text: str, normalized_alias: str) -> bool:
    import re

    return (
        re.search(rf"(?<!\w){re.escape(normalized_alias)}(?!\w)", normalized_text)
        is not None
    )


def _dry_run_payload(
    binding: ElasticsearchBinding,
    matches: list[ElasticsearchDryRunMatchedAlias],
    *,
    snapshot_version: str | None = None,
) -> dict[str, object]:
    canonical_values = sorted({match.canonical_value for match in matches})
    slots: dict[str, set[str]] = {}
    matched_aliases_by_value: dict[str, set[str]] = {}
    for match in matches:
        slots.setdefault(match.slot, set()).add(match.canonical_value)
        matched_aliases_by_value.setdefault(match.canonical_value, set()).add(
            match.alias_value
        )
    return {
        "profile_id": binding.profile.name,
        "binding_id": binding.id,
        "binding_name": binding.name,
        "snapshot_version": snapshot_version,
        "canonical_values": canonical_values,
        "slots": {slot: sorted(values) for slot, values in sorted(slots.items())},
        "matched_aliases": sorted({match.alias_value for match in matches}),
        "matched_aliases_by_value": {
            value: sorted(aliases)
            for value, aliases in sorted(matched_aliases_by_value.items())
        },
    }


def _job_target_index(
    binding: ElasticsearchBinding, target_index_name: str | None
) -> str | None:
    """Return the target index recorded for a new enrichment job."""

    if binding.write_strategy == "in_place":
        return binding.index_name
    if target_index_name:
        return target_index_name.strip()
    return None


def _job_alias_name(
    binding: ElasticsearchBinding, alias_name: str | None
) -> str | None:
    """Return the alias name used by reindex+alias-swap jobs."""

    if binding.write_strategy != "reindex_alias_swap":
        return None
    if alias_name:
        return alias_name.strip()
    return binding.index_name


def _default_reindex_target_name(binding: ElasticsearchBinding, job_id: int) -> str:
    """Build a deterministic target index name for MVP reindex jobs."""

    safe_source_index = binding.index_name.strip().lower().replace(" ", "_")
    return f"{safe_source_index}__skeinrank_job_{job_id}"


def _execute_elasticsearch_enrichment_job(
    *,
    client: ElasticsearchDiscoveryClient,
    session: Session,
    binding: ElasticsearchBinding,
    job: ElasticsearchEnrichmentJob,
    max_documents: int,
) -> dict[str, object]:
    """Execute one synchronous MVP Elasticsearch enrichment job."""

    if binding.write_strategy == "reindex_alias_swap":
        if not job.target_index:
            raise ElasticsearchDiscoveryError(
                "Target index is required for reindex jobs"
            )
        client.create_reindex_target_index(
            source_index=binding.index_name,
            target_index=job.target_index,
        )
        reindex_result = client.reindex_documents(
            source_index=binding.index_name,
            target_index=job.target_index,
            filter_field=binding.filter_field,
            filter_value=binding.filter_value,
            timestamp_field=binding.timestamp_field,
            time_window_days=binding.time_window_days,
        )
        update_index = job.target_index
    elif binding.write_strategy == "in_place":
        reindex_result = None
        update_index = binding.index_name
    else:  # pragma: no cover - guarded by API/model validation
        raise ElasticsearchDiscoveryError(
            f"Unsupported write strategy: {binding.write_strategy}"
        )

    alias_entries = alias_tuples_from_snapshot(job.snapshot_json)
    if not alias_entries:
        alias_entries = _active_alias_entries_for_profile(session, binding.profile)
    hits = client.search_documents(
        index_name=update_index,
        text_fields=list(binding.text_fields),
        limit=max_documents,
        filter_field=binding.filter_field,
        filter_value=binding.filter_value,
        timestamp_field=binding.timestamp_field,
        time_window_days=binding.time_window_days,
    )

    updates: list[tuple[str, dict[str, object]]] = []
    matched_documents: list[dict[str, object]] = []
    for hit in hits:
        text = compose_source_text(hit.source, list(binding.text_fields))
        matched_aliases = _match_alias_entries(text, alias_entries)
        if not matched_aliases:
            continue
        would_write_payload = _dry_run_payload(
            binding, matched_aliases, snapshot_version=job.snapshot_version
        )
        updates.append((hit.id, {binding.target_field: would_write_payload}))
        matched_documents.append(
            {
                "document_id": hit.id,
                "index_name": hit.index,
                "matched_aliases": [
                    {
                        "alias_value": match.alias_value,
                        "canonical_value": match.canonical_value,
                        "slot": match.slot,
                        "matched_text": match.matched_text,
                        "confidence": match.confidence,
                    }
                    for match in matched_aliases
                ],
                "would_write": {binding.target_field: would_write_payload},
            }
        )

    bulk_result = client.bulk_update_documents(index_name=update_index, updates=updates)
    alias_result = None
    rollout_metadata = None
    if binding.write_strategy == "reindex_alias_swap":
        if not job.alias_name:
            raise ElasticsearchDiscoveryError(
                "Alias name is required for alias-swap jobs"
            )
        previous_alias_indices = client.alias_indices(alias_name=job.alias_name)
        rollout_metadata = _build_reindex_rollout_metadata(
            alias_name=job.alias_name,
            source_index=binding.index_name,
            target_index=update_index,
            previous_alias_indices=previous_alias_indices,
        )
        alias_result = client.swap_alias(
            alias_name=job.alias_name,
            target_index=update_index,
        )
        rollout_metadata = _complete_reindex_rollout_metadata(
            rollout_metadata=rollout_metadata,
            alias_result=alias_result,
            new_alias_indices=client.alias_indices(alias_name=job.alias_name),
        )

    return {
        "write_strategy": binding.write_strategy,
        "source_index": binding.index_name,
        "target_index": update_index,
        "alias_name": job.alias_name,
        "snapshot_version": job.snapshot_version,
        "previous_snapshot_version": job.previous_snapshot_version,
        "snapshot_aliases_total": len(
            (job.snapshot_json or {}).get("alias_entries") or []
        ),
        "timestamp_field": binding.timestamp_field,
        "time_window_days": binding.time_window_days,
        "documents_seen": len(hits),
        "documents_enriched": len(updates),
        "documents_failed": 0,
        "updated_document_ids": [document_id for document_id, _document in updates],
        "matched_documents": matched_documents,
        "reindex_result": reindex_result,
        "bulk_result": bulk_result,
        "alias_result": alias_result,
        "rollout": rollout_metadata,
    }


def _rollback_candidate_index(
    previous_alias_indices: list[str], target_index: str
) -> str | None:
    candidates = [index for index in previous_alias_indices if index != target_index]
    if len(candidates) == 1:
        return candidates[0]
    return None


def _build_reindex_rollout_metadata(
    *,
    alias_name: str,
    source_index: str,
    target_index: str,
    previous_alias_indices: list[str],
) -> dict[str, object]:
    rollback_candidate = _rollback_candidate_index(previous_alias_indices, target_index)
    alias_bootstrapped = not previous_alias_indices
    if alias_bootstrapped:
        rollback_hint = (
            "This is the first successful publish for this alias; no previous "
            "alias target exists for automatic rollback."
        )
    elif rollback_candidate:
        rollback_hint = (
            f"Manual rollback candidate: repoint alias {alias_name} "
            f"to {rollback_candidate}."
        )
    else:
        rollback_hint = (
            "No single previous alias index was found for automatic rollback "
            "planning."
        )
    return {
        "strategy": "reindex_alias_swap",
        "status": "prepared",
        "alias_name": alias_name,
        "source_index": source_index,
        "target_index": target_index,
        "previous_alias_indices": previous_alias_indices,
        "new_alias_indices": [],
        "alias_bootstrapped": alias_bootstrapped,
        "rollback_candidate_index": rollback_candidate,
        "rollback_available": rollback_candidate is not None,
        "alias_swap_completed": False,
        "alias_swap_started_at": utc_now().isoformat(),
        "alias_swapped_at": None,
        "alias_result": None,
        "cleanup_hint": (
            "If this rollout is cancelled or fails before alias swap, "
            f"review or delete target index {target_index}."
        ),
        "rollback_hint": rollback_hint,
    }


def _complete_reindex_rollout_metadata(
    *,
    rollout_metadata: dict[str, object],
    alias_result: dict[str, object] | None,
    new_alias_indices: list[str],
) -> dict[str, object]:
    return {
        **rollout_metadata,
        "status": "alias_swapped",
        "new_alias_indices": new_alias_indices,
        "alias_swap_completed": True,
        "alias_swapped_at": utc_now().isoformat(),
        "alias_result": alias_result,
    }


def _validated_rollback_rollout(job: ElasticsearchEnrichmentJob) -> dict[str, object]:
    if job.write_strategy != "reindex_alias_swap":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only reindex_alias_swap jobs can be rolled back.",
        )
    if job.status != "succeeded":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot rollback enrichment job with status: {job.status}",
        )
    result_json = job.result_json or {}
    rollout = result_json.get("rollout")
    if not isinstance(rollout, dict):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Rollback metadata is not available for this job.",
        )
    if rollout.get("strategy") != "reindex_alias_swap":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Rollback metadata does not describe a reindex alias-swap rollout.",
        )
    if rollout.get("rollback_completed") is True or isinstance(
        rollout.get("rollback"), dict
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This enrichment job has already been rolled back.",
        )
    alias_name = rollout.get("alias_name") or job.alias_name
    rollback_candidate = rollout.get("rollback_candidate_index")
    if not isinstance(alias_name, str) or not alias_name.strip():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Rollback alias name is missing.",
        )
    if not isinstance(rollback_candidate, str) or not rollback_candidate.strip():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Rollback candidate index is missing.",
        )
    if rollout.get("alias_swap_completed") is not True:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot rollback before alias swap has completed.",
        )
    if rollout.get("rollback_available") is not True:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Rollback is not available for this job.",
        )
    return {
        **rollout,
        "alias_name": alias_name,
        "rollback_candidate_index": rollback_candidate,
    }


def _rollout_expected_current_indices(
    rollout: dict[str, object], job: ElasticsearchEnrichmentJob
) -> list[str]:
    new_alias_indices = rollout.get("new_alias_indices")
    if isinstance(new_alias_indices, list) and new_alias_indices:
        return [str(index) for index in new_alias_indices]
    target_index = rollout.get("target_index") or job.target_index
    if isinstance(target_index, str) and target_index:
        return [target_index]
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Expected post-rollout alias state is missing.",
    )


def _get_elasticsearch_enrichment_job_or_404(
    session: Session, job_id: int
) -> ElasticsearchEnrichmentJob:
    job = session.scalar(
        select(ElasticsearchEnrichmentJob).where(
            ElasticsearchEnrichmentJob.id == job_id
        )
    )
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Elasticsearch enrichment job not found: {job_id}",
        )
    return job


def _elasticsearch_enrichment_job_response(
    job: ElasticsearchEnrichmentJob,
) -> ElasticsearchEnrichmentJobResponse:
    return ElasticsearchEnrichmentJobResponse(
        id=job.id,
        binding_id=job.binding_id,
        profile_id=job.profile_id,
        binding_name=job.binding.name,
        profile_name=job.profile.name,
        status=job.status,
        write_strategy=job.write_strategy,
        source_index=job.source_index,
        target_index=job.target_index,
        alias_name=job.alias_name,
        snapshot_version=job.snapshot_version,
        previous_snapshot_version=job.previous_snapshot_version,
        requested_by=job.requested_by,
        documents_seen=job.documents_seen,
        documents_enriched=job.documents_enriched,
        documents_failed=job.documents_failed,
        result_json=job.result_json or {},
        error_message=job.error_message,
        started_at=job.started_at,
        finished_at=job.finished_at,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


def _get_elasticsearch_binding_or_404(
    session: Session, binding_id: int
) -> ElasticsearchBinding:
    binding = session.scalar(
        select(ElasticsearchBinding).where(ElasticsearchBinding.id == binding_id)
    )
    if binding is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Elasticsearch binding not found: {binding_id}",
        )
    return binding


def _validate_elasticsearch_binding_provider(provider: str) -> None:
    if provider not in ELASTICSEARCH_BINDING_PROVIDERS:
        allowed_values = ", ".join(ELASTICSEARCH_BINDING_PROVIDERS)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Invalid Elasticsearch binding provider: {provider}. Allowed values: {allowed_values}",
        )


def _validate_elasticsearch_binding_mode(mode: str) -> None:
    if mode not in ELASTICSEARCH_BINDING_MODES:
        allowed_values = ", ".join(ELASTICSEARCH_BINDING_MODES)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Invalid Elasticsearch binding mode: {mode}. Allowed values: {allowed_values}",
        )


def _validate_elasticsearch_binding_write_strategy(write_strategy: str) -> None:
    if write_strategy not in ELASTICSEARCH_BINDING_WRITE_STRATEGIES:
        allowed_values = ", ".join(ELASTICSEARCH_BINDING_WRITE_STRATEGIES)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                f"Invalid Elasticsearch binding write strategy: {write_strategy}. "
                f"Allowed values: {allowed_values}"
            ),
        )


def _normalize_text_fields(text_fields: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for field in text_fields:
        value = field.strip()
        if not value:
            continue
        if value in seen:
            continue
        normalized.append(value)
        seen.add(value)
    if not normalized:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Elasticsearch binding requires at least one text field.",
        )
    return normalized


def _normalize_optional_filter(
    filter_field: str | None, filter_value: str | None
) -> tuple[str | None, str | None]:
    field = filter_field.strip() if filter_field is not None else None
    value = filter_value.strip() if filter_value is not None else None
    field = field or None
    value = value or None
    if (field is None) != (value is None):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Elasticsearch binding filter requires both filter_field and filter_value.",
        )
    return field, value


def _normalize_time_filter(
    timestamp_field: str | None, time_window_days: int | None
) -> tuple[str | None, int | None]:
    field = timestamp_field.strip() if timestamp_field is not None else None
    field = field or None
    if time_window_days is not None and field is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Elasticsearch binding time window requires timestamp_field.",
        )
    return field, time_window_days


def _ensure_elasticsearch_binding_name_unique(
    session: Session,
    *,
    normalized_name: str,
    exclude_id: int | None = None,
) -> None:
    query = select(ElasticsearchBinding).where(
        ElasticsearchBinding.normalized_name == normalized_name
    )
    if exclude_id is not None:
        query = query.where(ElasticsearchBinding.id != exclude_id)
    existing = session.scalar(query)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Elasticsearch binding already exists: {existing.name}",
        )


def _get_stop_list_entry_or_404(
    session: Session, profile: TerminologyProfile, entry_id: int
) -> GovernanceStopListEntry:
    entry = session.scalar(
        select(GovernanceStopListEntry).where(
            GovernanceStopListEntry.id == entry_id,
            GovernanceStopListEntry.profile_id == profile.id,
        )
    )
    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Stop-list entry not found for profile {profile.name!r}: {entry_id}",
        )
    return entry


def _get_global_stop_list_entry_or_404(
    session: Session, entry_id: int
) -> GovernanceGlobalStopListEntry:
    entry = session.scalar(
        select(GovernanceGlobalStopListEntry).where(
            GovernanceGlobalStopListEntry.id == entry_id
        )
    )
    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Global stop-list entry not found: {entry_id}",
        )
    return entry


def _ensure_global_stop_list_entry_unique(
    session: Session,
    *,
    normalized_value: str,
    target: str,
    exclude_id: int | None = None,
) -> None:
    query = select(GovernanceGlobalStopListEntry).where(
        GovernanceGlobalStopListEntry.normalized_value == normalized_value
    )
    if exclude_id is not None:
        query = query.where(GovernanceGlobalStopListEntry.id != exclude_id)
    candidates = list(session.scalars(query))
    for entry in candidates:
        if entry.target == target or entry.target == "both" or target == "both":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Global stop-list entry already exists: "
                    f"{entry.value} ({entry.target})"
                ),
            )


def _validate_stop_list_target(target: str) -> None:
    if target not in STOP_LIST_TARGETS:
        allowed_values = ", ".join(STOP_LIST_TARGETS)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Invalid stop-list target: {target}. Allowed values: {allowed_values}",
        )


def _ensure_stop_list_entry_unique(
    session: Session,
    profile: TerminologyProfile,
    *,
    normalized_value: str,
    target: str,
    exclude_id: int | None = None,
) -> None:
    query = select(GovernanceStopListEntry).where(
        GovernanceStopListEntry.profile_id == profile.id,
        GovernanceStopListEntry.normalized_value == normalized_value,
    )
    if exclude_id is not None:
        query = query.where(GovernanceStopListEntry.id != exclude_id)
    candidates = list(session.scalars(query))
    for entry in candidates:
        if entry.target == target or entry.target == "both" or target == "both":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Stop-list entry already exists in profile {profile.name!r}: "
                    f"{entry.value} ({entry.target})"
                ),
            )


def _stop_list_targets_for(target: str) -> tuple[str, ...]:
    if target == "alias":
        return ("alias", "both")
    if target == "canonical":
        return ("canonical", "both")
    return STOP_LIST_TARGETS


def _ensure_not_stoplisted(
    session: Session,
    profile: TerminologyProfile,
    *,
    value: str,
    target: str,
    entity_name: str,
) -> None:
    normalized_value = normalize_value(value)
    target_values = _stop_list_targets_for(target)

    global_entry = session.scalar(
        select(GovernanceGlobalStopListEntry).where(
            GovernanceGlobalStopListEntry.normalized_value == normalized_value,
            GovernanceGlobalStopListEntry.target.in_(target_values),
            GovernanceGlobalStopListEntry.is_active.is_(True),
        )
    )
    if global_entry is not None:
        detail = f"{entity_name} is blocked by global stop list: {value}"
        if global_entry.reason:
            detail = f"{detail}. Reason: {global_entry.reason}"
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)

    profile_entry = session.scalar(
        select(GovernanceStopListEntry).where(
            GovernanceStopListEntry.profile_id == profile.id,
            GovernanceStopListEntry.normalized_value == normalized_value,
            GovernanceStopListEntry.target.in_(target_values),
            GovernanceStopListEntry.is_active.is_(True),
        )
    )
    if profile_entry is None:
        return
    detail = (
        f"{entity_name} is blocked by stop list for profile {profile.name!r}: "
        f"{value}"
    )
    if profile_entry.reason:
        detail = f"{detail}. Reason: {profile_entry.reason}"
    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


def _get_profile_or_404(session: Session, profile_name: str) -> TerminologyProfile:
    try:
        return get_profile(session, profile_name)
    except GovernanceCliError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


def _get_alias_or_404(
    session: Session, term: CanonicalTerm, alias_id: int
) -> TermAlias:
    alias = session.scalar(
        select(TermAlias).where(
            TermAlias.id == alias_id,
            TermAlias.term_id == term.id,
            TermAlias.profile_id == term.profile_id,
        )
    )
    if alias is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Alias not found for canonical term {term.canonical_value!r}: {alias_id}",
        )
    return alias


def _pending_suggestions_for_batch(
    *,
    session: Session,
    profile: TerminologyProfile,
    suggestion_ids: list[int] | None,
) -> list[GovernanceSuggestion]:
    query = select(GovernanceSuggestion).where(
        GovernanceSuggestion.profile_id == profile.id,
        GovernanceSuggestion.status == "pending",
    )
    requested_ids: list[int] | None = None
    if suggestion_ids is not None:
        requested_ids = list(dict.fromkeys(suggestion_ids))
        query = query.where(GovernanceSuggestion.id.in_(requested_ids))

    suggestions = list(
        session.scalars(
            query.order_by(
                GovernanceSuggestion.suggestion_type.desc(),
                GovernanceSuggestion.id,
            )
        )
    )
    if requested_ids is not None:
        found_ids = {suggestion.id for suggestion in suggestions}
        missing_ids = [
            suggestion_id
            for suggestion_id in requested_ids
            if suggestion_id not in found_ids
        ]
        if missing_ids:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=(
                    f"Pending suggestions not found for profile {profile.name!r}: "
                    f"{missing_ids}"
                ),
            )
    return suggestions


def _ordered_suggestions_for_apply(
    suggestions: list[GovernanceSuggestion],
) -> list[GovernanceSuggestion]:
    """Apply canonical-term proposals before alias proposals in one batch."""

    return sorted(
        suggestions,
        key=lambda suggestion: (
            0 if suggestion.suggestion_type == "canonical_term" else 1,
            suggestion.id,
        ),
    )


def _ensure_batch_suggestions_are_applyable(
    suggestions: list[GovernanceSuggestion],
) -> None:
    blocked_ids: list[int] = []
    for suggestion in suggestions:
        summary = suggestion.validation_summary_json or {}
        if isinstance(summary, dict) and summary.get("status") == "blocked":
            blocked_ids.append(suggestion.id)
    if blocked_ids:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Proposal batch contains blocked suggestions. "
                f"Review or reject them before applying: {blocked_ids}"
            ),
        )


def _get_suggestion_or_404(
    session: Session, profile: TerminologyProfile, suggestion_id: int
) -> GovernanceSuggestion:
    suggestion = session.scalar(
        select(GovernanceSuggestion).where(
            GovernanceSuggestion.id == suggestion_id,
            GovernanceSuggestion.profile_id == profile.id,
        )
    )
    if suggestion is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Suggestion not found for profile {profile.name!r}: {suggestion_id}",
        )
    return suggestion


def _approve_alias_suggestion(
    session: Session, profile: TerminologyProfile, suggestion: GovernanceSuggestion
) -> None:
    if suggestion.alias_value is None or suggestion.normalized_alias is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Alias suggestion is missing alias_value.",
        )

    _ensure_not_stoplisted(
        session,
        profile,
        value=suggestion.alias_value,
        target="alias",
        entity_name="Alias suggestion",
    )

    try:
        term = get_term(session, profile, suggestion.canonical_value)
    except GovernanceCliError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    existing_alias = session.scalar(
        select(TermAlias).where(
            TermAlias.profile_id == profile.id,
            TermAlias.normalized_alias == suggestion.normalized_alias,
        )
    )
    if existing_alias is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Alias already exists in profile {profile.name!r}: {suggestion.alias_value}",
        )

    alias = TermAlias(
        profile=profile,
        term=term,
        alias_value=suggestion.alias_value,
        confidence=suggestion.confidence,
        status="active",
        notes=suggestion.context,
    )
    session.add(alias)
    session.flush()
    suggestion.alias_id = alias.id


def _approve_canonical_term_suggestion(
    session: Session, profile: TerminologyProfile, suggestion: GovernanceSuggestion
) -> None:
    _ensure_not_stoplisted(
        session,
        profile,
        value=suggestion.canonical_value,
        target="canonical",
        entity_name="Canonical term suggestion",
    )

    existing_term = session.scalar(
        select(CanonicalTerm).where(
            CanonicalTerm.profile_id == profile.id,
            CanonicalTerm.normalized_value == suggestion.normalized_canonical,
        )
    )
    if existing_term is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Canonical term already exists in profile {profile.name!r}: "
                f"{suggestion.canonical_value}"
            ),
        )

    term = CanonicalTerm(
        profile=profile,
        canonical_value=suggestion.canonical_value,
        slot=suggestion.slot,
        description=suggestion.description,
        status="active",
    )
    session.add(term)
    session.flush()
    suggestion.term_id = term.id


def _ensure_pending_suggestion(suggestion: GovernanceSuggestion) -> None:
    if suggestion.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Suggestion is not pending: {suggestion.status}",
        )


def _validate_status(value: str, allowed: tuple[str, ...], entity_name: str) -> None:
    if value not in allowed:
        allowed_values = ", ".join(allowed)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Invalid {entity_name} status: {value}. Allowed values: {allowed_values}",
        )


def _integrity_conflict(exc: IntegrityError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=f"Database integrity error: {exc.orig}",
    )


def _profile_response(profile: TerminologyProfile) -> ProfileResponse:
    return ProfileResponse(
        id=profile.id,
        name=profile.name,
        normalized_name=profile.normalized_name,
        description=profile.description,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


def _term_response(term: CanonicalTerm) -> TermResponse:
    return TermResponse(
        id=term.id,
        canonical_value=term.canonical_value,
        normalized_value=term.normalized_value,
        slot=term.slot,
        status=term.status,
        description=term.description,
        aliases=[_alias_response(alias) for alias in term.aliases],
        created_at=term.created_at,
        updated_at=term.updated_at,
    )


def _suggestion_response(suggestion: GovernanceSuggestion) -> SuggestionResponse:
    return SuggestionResponse(
        id=suggestion.id,
        profile_id=suggestion.profile_id,
        term_id=suggestion.term_id,
        alias_id=suggestion.alias_id,
        binding_id=suggestion.binding_id,
        suggestion_type=suggestion.suggestion_type,
        canonical_value=suggestion.canonical_value,
        normalized_canonical=suggestion.normalized_canonical,
        alias_value=suggestion.alias_value,
        normalized_alias=suggestion.normalized_alias,
        slot=suggestion.slot,
        description=suggestion.description,
        confidence=suggestion.confidence,
        source=suggestion.source,
        context=suggestion.context,
        proposal_source_type=suggestion.proposal_source_type,
        proposal_source_name=suggestion.proposal_source_name,
        idempotency_key=suggestion.idempotency_key,
        source_payload=suggestion.source_payload_json,
        validation_summary=suggestion.validation_summary_json,
        status=suggestion.status,
        created_by=suggestion.created_by,
        reviewed_by=suggestion.reviewed_by,
        review_comment=suggestion.review_comment,
        reviewed_at=suggestion.reviewed_at,
        evidence_snapshot=suggestion.evidence_snapshot,
        evidence_checked_by=suggestion.evidence_checked_by,
        evidence_checked_at=suggestion.evidence_checked_at,
        created_at=suggestion.created_at,
        updated_at=suggestion.updated_at,
    )


def _global_stop_list_response(
    entry: GovernanceGlobalStopListEntry,
) -> GlobalStopListEntryResponse:
    return GlobalStopListEntryResponse(
        id=entry.id,
        value=entry.value,
        normalized_value=entry.normalized_value,
        target=entry.target,
        reason=entry.reason,
        is_active=entry.is_active,
        created_at=entry.created_at,
        updated_at=entry.updated_at,
    )


def _stop_list_response(entry: GovernanceStopListEntry) -> StopListEntryResponse:
    return StopListEntryResponse(
        id=entry.id,
        profile_id=entry.profile_id,
        value=entry.value,
        normalized_value=entry.normalized_value,
        target=entry.target,
        reason=entry.reason,
        is_active=entry.is_active,
        created_at=entry.created_at,
        updated_at=entry.updated_at,
    )


def _elasticsearch_binding_response(
    binding: ElasticsearchBinding,
) -> ElasticsearchBindingResponse:
    return ElasticsearchBindingResponse(
        id=binding.id,
        profile_id=binding.profile_id,
        profile_name=binding.profile.name,
        name=binding.name,
        normalized_name=binding.normalized_name,
        description=binding.description,
        provider=binding.provider,
        index_name=binding.index_name,
        text_fields=list(binding.text_fields),
        target_field=binding.target_field,
        filter_field=binding.filter_field,
        filter_value=binding.filter_value,
        timestamp_field=binding.timestamp_field,
        time_window_days=binding.time_window_days,
        mode=binding.mode,
        write_strategy=binding.write_strategy,
        is_enabled=binding.is_enabled,
        last_successful_snapshot_version=binding.last_successful_snapshot_version,
        last_successful_snapshot_at=binding.last_successful_snapshot_at,
        last_successful_job_id=binding.last_successful_job_id,
        pending_snapshot_version=binding.pending_snapshot_version,
        snapshot_status=binding_snapshot_status(binding),
        created_at=binding.created_at,
        updated_at=binding.updated_at,
    )


def _alias_response(alias: TermAlias) -> AliasResponse:
    return AliasResponse(
        id=alias.id,
        alias_value=alias.alias_value,
        normalized_alias=alias.normalized_alias,
        status=alias.status,
        confidence=alias.confidence,
        notes=alias.notes,
        created_at=alias.created_at,
        updated_at=alias.updated_at,
    )
