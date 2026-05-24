"""DB-backed agent document visit tracking helpers."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from skeinrank_governance.models import (
    AGENT_DOCUMENT_VISIT_STATUSES,
    AgentDocumentVisit,
)
from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from .agent_run_registry import get_agent_run_by_run_id

SCAN_REQUIRED_STATUSES = {"new_document", "content_changed", "context_changed", "error"}


class AgentDocumentVisitError(ValueError):
    """Raised when a document visit command is invalid."""


def compute_content_hash(value: str | bytes | dict[str, Any] | list[Any]) -> str:
    """Return a stable SHA-256 hash for a document payload or text."""

    return _hash_value(value)


def compute_processing_context_hash(
    *,
    agent_name: str,
    agent_version: str | None = None,
    prompt_version: str | None = None,
    openrouter_model: str | None = None,
    config_hash: str | None = None,
    profile_name: str | None = None,
    binding_id: int | None = None,
) -> str:
    """Return a stable hash for the processing context that affects scanning."""

    return _hash_value(
        {
            "agent_name": agent_name,
            "agent_version": agent_version,
            "prompt_version": prompt_version,
            "openrouter_model": openrouter_model,
            "config_hash": config_hash,
            "profile_name": profile_name,
            "binding_id": binding_id,
        }
    )


def record_document_visit(
    session: Session,
    *,
    run_id: str,
    source_id: str,
    content_hash: str | None = None,
    content: str | bytes | dict[str, Any] | list[Any] | None = None,
    processing_context_hash: str | None = None,
    external_document_id: str | None = None,
    source_type: str = "document",
    index_name: str | None = None,
    agent_version: str | None = None,
    prompt_version: str | None = None,
    openrouter_model: str | None = None,
    metadata_json: dict[str, Any] | None = None,
    evidence_windows_found: int = 0,
    error_message: str | None = None,
    force_rescan: bool = False,
) -> AgentDocumentVisit:
    """Create one document visit row and decide whether the document should scan."""

    if not source_id.strip():
        raise AgentDocumentVisitError("source_id must not be empty.")
    agent_run = get_agent_run_by_run_id(session, run_id)
    if agent_run is None:
        raise AgentDocumentVisitError(f"Agent run not found: {run_id}")
    normalized_content_hash = _resolve_content_hash(content_hash, content)
    normalized_context_hash = (
        processing_context_hash
        or compute_processing_context_hash(
            agent_name=agent_run.agent_name,
            agent_version=agent_version
            if agent_version is not None
            else agent_run.agent_version,
            prompt_version=prompt_version
            if prompt_version is not None
            else agent_run.prompt_version,
            openrouter_model=(
                openrouter_model
                if openrouter_model is not None
                else agent_run.openrouter_model
            ),
            config_hash=agent_run.config_hash,
            profile_name=agent_run.profile_name,
            binding_id=agent_run.binding_id,
        )
    )
    previous = find_latest_visit_for_source(
        session,
        source_id=source_id,
        profile_id=agent_run.profile_id,
        binding_id=agent_run.binding_id,
        exclude_run_id=run_id,
    )
    visit_status = _classify_visit(
        previous=previous,
        content_hash=normalized_content_hash,
        processing_context_hash=normalized_context_hash,
        error_message=error_message,
    )
    should_scan = force_rescan or visit_status in SCAN_REQUIRED_STATUSES
    visit = AgentDocumentVisit(
        agent_run=agent_run,
        run_id=agent_run.run_id,
        profile_id=agent_run.profile_id,
        binding_id=agent_run.binding_id,
        source_id=source_id.strip(),
        external_document_id=external_document_id,
        source_type=source_type.strip() or "document",
        index_name=index_name,
        content_hash=normalized_content_hash,
        processing_context_hash=normalized_context_hash,
        agent_name=agent_run.agent_name,
        agent_version=agent_version
        if agent_version is not None
        else agent_run.agent_version,
        prompt_version=prompt_version
        if prompt_version is not None
        else agent_run.prompt_version,
        openrouter_model=openrouter_model
        if openrouter_model is not None
        else agent_run.openrouter_model,
        visit_status=visit_status,
        should_scan=should_scan,
        evidence_windows_found=max(0, evidence_windows_found),
        metadata_json=metadata_json or {},
        error_message=error_message,
    )
    session.add(visit)
    return visit


def list_document_visits(
    session: Session,
    *,
    run_id: str,
    visit_status: str | None = None,
    should_scan: bool | None = None,
    limit: int = 100,
) -> list[AgentDocumentVisit]:
    """List document visits for one run."""

    agent_run = get_agent_run_by_run_id(session, run_id)
    if agent_run is None:
        raise AgentDocumentVisitError(f"Agent run not found: {run_id}")
    statement: Select[tuple[AgentDocumentVisit]] = select(AgentDocumentVisit).where(
        AgentDocumentVisit.agent_run_id == agent_run.id
    )
    if visit_status is not None:
        statement = statement.where(
            AgentDocumentVisit.visit_status == _validate_visit_status(visit_status)
        )
    if should_scan is not None:
        statement = statement.where(AgentDocumentVisit.should_scan.is_(should_scan))
    statement = statement.order_by(
        AgentDocumentVisit.created_at.desc(), AgentDocumentVisit.id.desc()
    ).limit(max(1, min(limit, 500)))
    return list(session.scalars(statement))


def find_latest_visit_for_source(
    session: Session,
    *,
    source_id: str,
    profile_id: int | None,
    binding_id: int | None,
    exclude_run_id: str | None = None,
) -> AgentDocumentVisit | None:
    """Return the newest previous visit for the same source identity."""

    statement = select(AgentDocumentVisit).where(
        AgentDocumentVisit.source_id == source_id
    )
    if profile_id is None:
        statement = statement.where(AgentDocumentVisit.profile_id.is_(None))
    else:
        statement = statement.where(AgentDocumentVisit.profile_id == profile_id)
    if binding_id is None:
        statement = statement.where(AgentDocumentVisit.binding_id.is_(None))
    else:
        statement = statement.where(AgentDocumentVisit.binding_id == binding_id)
    if exclude_run_id is not None:
        statement = statement.where(AgentDocumentVisit.run_id != exclude_run_id)
    statement = statement.order_by(
        AgentDocumentVisit.created_at.desc(), AgentDocumentVisit.id.desc()
    ).limit(1)
    return session.scalar(statement)


def _classify_visit(
    *,
    previous: AgentDocumentVisit | None,
    content_hash: str,
    processing_context_hash: str,
    error_message: str | None,
) -> str:
    if error_message:
        return "error"
    if previous is None:
        return "new_document"
    if previous.content_hash != content_hash:
        return "content_changed"
    if previous.processing_context_hash != processing_context_hash:
        return "context_changed"
    return "unchanged_seen"


def _resolve_content_hash(
    content_hash: str | None,
    content: str | bytes | dict[str, Any] | list[Any] | None,
) -> str:
    if content_hash:
        normalized = content_hash.strip().lower()
        if len(normalized) < 12:
            raise AgentDocumentVisitError(
                "content_hash must be at least 12 characters."
            )
        return normalized
    if content is None:
        raise AgentDocumentVisitError(
            "Either content_hash or content must be provided."
        )
    return compute_content_hash(content)


def _validate_visit_status(visit_status: str) -> str:
    normalized = visit_status.strip().lower()
    if normalized not in AGENT_DOCUMENT_VISIT_STATUSES:
        raise AgentDocumentVisitError(
            "Invalid document visit status "
            f"{visit_status!r}. Expected one of {list(AGENT_DOCUMENT_VISIT_STATUSES)!r}."
        )
    return normalized


def _hash_value(value: str | bytes | dict[str, Any] | list[Any]) -> str:
    if isinstance(value, bytes):
        raw = value
    elif isinstance(value, str):
        raw = value.encode("utf-8")
    else:
        raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()
