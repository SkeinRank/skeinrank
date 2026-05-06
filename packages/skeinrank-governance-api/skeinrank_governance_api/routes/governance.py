"""Terminology governance REST endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response, status
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
    SUGGESTION_SOURCES,
    SUGGESTION_STATUSES,
    TERM_STATUSES,
    CanonicalTerm,
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
from ..schemas import (
    AliasCreateRequest,
    AliasResponse,
    AliasUpdateRequest,
    ProfileCreateRequest,
    ProfileResponse,
    ProfileUpdateRequest,
    RuntimeSnapshotResponse,
    SnapshotExportRequest,
    SuggestionCreateRequest,
    SuggestionResponse,
    SuggestionReviewRequest,
    TermCreateRequest,
    TermResponse,
    TermUpdateRequest,
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
    """List alias suggestions for a terminology profile."""

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
    current_user: AuthContext = Depends(
        require_roles("admin", "moderator", "contributor")
    ),
    session: Session = Depends(get_session),
) -> SuggestionResponse:
    """Create a pending alias suggestion without mutating active aliases."""

    profile = _get_profile_or_404(session, profile_name)
    _validate_status(request.source, SUGGESTION_SOURCES, "suggestion source")

    suggestion = GovernanceSuggestion(
        profile=profile,
        canonical_value=request.canonical_value,
        alias_value=request.alias_value,
        slot=request.slot,
        confidence=request.confidence,
        source=request.source,
        context=request.context,
        status="pending",
        created_by=current_user.username,
    )
    session.add(suggestion)
    try:
        session.commit()
        session.refresh(suggestion)
        return _suggestion_response(suggestion)
    except IntegrityError as exc:
        session.rollback()
        raise _integrity_conflict(exc) from exc


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
    suggestion.status = "approved"
    suggestion.reviewed_by = reviewer.username
    suggestion.review_comment = request.review_comment
    suggestion.reviewed_at = utc_now()

    try:
        session.commit()
        session.refresh(suggestion)
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
    return _suggestion_response(suggestion)


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
        alias_id=suggestion.alias_id,
        canonical_value=suggestion.canonical_value,
        normalized_canonical=suggestion.normalized_canonical,
        alias_value=suggestion.alias_value,
        normalized_alias=suggestion.normalized_alias,
        slot=suggestion.slot,
        confidence=suggestion.confidence,
        source=suggestion.source,
        context=suggestion.context,
        status=suggestion.status,
        created_by=suggestion.created_by,
        reviewed_by=suggestion.reviewed_by,
        review_comment=suggestion.review_comment,
        reviewed_at=suggestion.reviewed_at,
        created_at=suggestion.created_at,
        updated_at=suggestion.updated_at,
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
