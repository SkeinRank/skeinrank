"""Terminology governance REST endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Response, status
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
    TERM_STATUSES,
    CanonicalTerm,
    TermAlias,
    TerminologyProfile,
    normalize_profile_name,
    normalize_value,
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
