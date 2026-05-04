"""Terminology governance REST endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from skeinrank_governance.cli import (
    GovernanceCliError,
    add_alias,
    add_term,
    create_profile,
    get_profile,
    get_term,
)
from skeinrank_governance.models import (
    CanonicalTerm,
    TermAlias,
    TerminologyProfile,
)
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..dependencies import get_session
from ..schemas import (
    AliasCreateRequest,
    AliasResponse,
    ProfileCreateRequest,
    ProfileResponse,
    TermCreateRequest,
    TermResponse,
)

router = APIRouter(prefix="/v1/governance", tags=["governance"])


@router.get("/profiles", response_model=list[ProfileResponse])
def list_profiles(session: Session = Depends(get_session)) -> list[ProfileResponse]:
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
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Database integrity error: {exc.orig}",
        )


@router.get(
    "/profiles/{profile_name}/terms",
    response_model=list[TermResponse],
)
def list_profile_terms(
    profile_name: str,
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
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Database integrity error: {exc.orig}",
        )


@router.post(
    "/profiles/{profile_name}/terms/{canonical_value}/aliases",
    response_model=AliasResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_term_alias(
    profile_name: str,
    canonical_value: str,
    request: AliasCreateRequest,
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
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Database integrity error: {exc.orig}",
        )


@router.get(
    "/profiles/{profile_name}/terms/{canonical_value}",
    response_model=TermResponse,
)
def get_profile_term(
    profile_name: str,
    canonical_value: str,
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


def _get_profile_or_404(session: Session, profile_name: str) -> TerminologyProfile:
    try:
        return get_profile(session, profile_name)
    except GovernanceCliError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


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
