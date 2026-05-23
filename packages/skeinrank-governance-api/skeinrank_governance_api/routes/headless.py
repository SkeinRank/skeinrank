"""Headless API facade for dictionary migration workflows.

These routes expose the stable dictionary spec through automation-friendly
endpoints while reusing the existing console migration implementation.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from skeinrank_governance.models import ElasticsearchBinding
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..auth import AuthContext, require_roles, require_scopes
from ..dependencies import get_session
from ..runtime_snapshots import build_runtime_snapshot_artifact
from ..schemas import (
    ConsoleDictionaryExportResponse,
    ConsoleDictionaryPayload,
    ConsoleDictionaryReport,
)
from .console import (
    _apply_console_dictionary,
    _build_console_dictionary_report,
    export_console_dictionary,
)

router = APIRouter(prefix="/v1/headless", tags=["headless"])


@router.post(
    "/dictionaries/validate",
    response_model=ConsoleDictionaryReport,
)
def validate_headless_dictionary(
    request: ConsoleDictionaryPayload,
    _current_user: AuthContext = Depends(
        require_roles("admin", "moderator", "contributor")
    ),
    _scope: AuthContext = Depends(require_scopes("migration:validate")),
    session: Session = Depends(get_session),
) -> ConsoleDictionaryReport:
    """Validate a dictionary spec v1 payload without writing to the database."""

    return _build_console_dictionary_report(session, request, applied=False)


@router.post(
    "/dictionaries/apply",
    response_model=ConsoleDictionaryReport,
)
def apply_headless_dictionary(
    request: ConsoleDictionaryPayload,
    current_user: AuthContext = Depends(require_roles("admin", "moderator")),
    _scope: AuthContext = Depends(require_scopes("migration:apply")),
    session: Session = Depends(get_session),
) -> ConsoleDictionaryReport:
    """Validate and apply a dictionary spec v1 payload in one transaction."""

    report = _build_console_dictionary_report(session, request, applied=False)
    if report.errors:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "message": "Dictionary apply validation failed.",
                "report": report.model_dump(mode="json"),
            },
        )
    if report.profile_exists is False and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admin users can create profiles during headless apply.",
        )

    try:
        applied_report = _apply_console_dictionary(session, request, current_user)
        session.commit()
        return applied_report
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Database integrity error: {exc.orig}",
        ) from exc


@router.get(
    "/dictionaries/export",
    response_model=ConsoleDictionaryExportResponse,
)
def export_headless_dictionary(
    profile_name: str = Query(..., min_length=1, max_length=128),
    include_global_stop_list: bool = Query(default=True),
    current_user: AuthContext = Depends(
        require_roles("admin", "moderator", "contributor")
    ),
    scope: AuthContext = Depends(require_scopes("migration:export")),
    session: Session = Depends(get_session),
) -> ConsoleDictionaryExportResponse:
    """Export a profile dictionary in the stable dictionary spec v1 shape."""

    return export_console_dictionary(
        profile_name=profile_name,
        include_global_stop_list=include_global_stop_list,
        _current_user=current_user,
        _scope=scope,
        session=session,
    )


@router.get("/snapshots/export")
def export_headless_snapshot_artifact(
    binding_id: int = Query(..., ge=1),
    source: str = Query(
        default="latest",
        pattern="^(latest|runtime)$",
        description="Use latest profile state or the binding-pinned runtime snapshot.",
    ),
    snapshot_version: str | None = Query(default=None, min_length=1, max_length=128),
    description: str | None = Query(default=None, max_length=512),
    _current_user: AuthContext = Depends(
        require_roles("admin", "moderator", "contributor")
    ),
    _scope: AuthContext = Depends(require_scopes("migration:export")),
    session: Session = Depends(get_session),
) -> dict:
    """Export a portable binding-scoped runtime snapshot artifact.

    The artifact is intended for headless workers, GitOps commits, and object
    storage. ``source=latest`` builds from the current profile state.
    ``source=runtime`` exports the binding-pinned runtime snapshot and fails when
    the binding has not published one yet.
    """

    binding = session.scalar(
        select(ElasticsearchBinding).where(ElasticsearchBinding.id == binding_id)
    )
    if binding is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Elasticsearch binding not found: {binding_id}",
        )
    try:
        return build_runtime_snapshot_artifact(
            session,
            binding,
            source=source,
            snapshot_version=snapshot_version,
            description=description,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
