"""DB-backed agent run registry helpers."""

from __future__ import annotations

from uuid import uuid4

from skeinrank_governance.models import (
    AGENT_RUN_STATUSES,
    AGENT_RUN_TRIGGER_TYPES,
    AgentRun,
    ElasticsearchBinding,
    TerminologyProfile,
    normalize_profile_name,
    utc_now,
)
from sqlalchemy import Select, select
from sqlalchemy.orm import Session

FINAL_AGENT_RUN_STATUSES = {"succeeded", "failed", "cancelled", "needs_review"}


class AgentRunRegistryError(ValueError):
    """Raised when an agent run registry command is invalid."""


def create_agent_run(
    session: Session,
    *,
    run_id: str | None = None,
    agent_name: str = "openrouter_alias_scout",
    agent_version: str | None = None,
    status: str = "queued",
    trigger_type: str = "manual",
    profile_name: str | None = None,
    binding_id: int | None = None,
    openrouter_model: str | None = None,
    prompt_version: str | None = None,
    workflow_engine: str | None = None,
    config_hash: str | None = None,
    artifacts_uri: str | None = None,
    report_uri: str | None = None,
    summary_json: dict[str, object] | None = None,
    error_message: str | None = None,
    requested_by: str | None = None,
) -> AgentRun:
    """Create a run registry row without committing the session."""

    normalized_status = _validate_status(status)
    normalized_trigger = _validate_trigger_type(trigger_type)
    profile = _resolve_profile(session, profile_name)
    binding = _resolve_binding(session, binding_id)
    if profile is not None and binding is not None and binding.profile_id != profile.id:
        raise AgentRunRegistryError(
            "Binding belongs to a different profile than the requested agent run."
        )
    if profile is None and binding is not None:
        profile = binding.profile

    agent_run = AgentRun(
        run_id=(run_id or f"agent-run-{uuid4().hex}"),
        agent_name=agent_name,
        agent_version=agent_version,
        status=normalized_status,
        trigger_type=normalized_trigger,
        profile=profile,
        profile_name=profile.name if profile is not None else profile_name,
        normalized_profile_name=(
            profile.normalized_name
            if profile is not None
            else normalize_profile_name(profile_name)
            if profile_name
            else None
        ),
        binding=binding,
        openrouter_model=openrouter_model,
        prompt_version=prompt_version,
        workflow_engine=workflow_engine,
        config_hash=config_hash,
        artifacts_uri=artifacts_uri,
        report_uri=report_uri,
        summary_json=summary_json or {},
        error_message=error_message,
        requested_by=requested_by,
        started_at=utc_now() if normalized_status == "running" else None,
        finished_at=(
            utc_now() if normalized_status in FINAL_AGENT_RUN_STATUSES else None
        ),
    )
    session.add(agent_run)
    return agent_run


def update_agent_run(
    agent_run: AgentRun,
    *,
    status: str | None = None,
    artifacts_uri: str | None = None,
    report_uri: str | None = None,
    summary_json: dict[str, object] | None = None,
    error_message: str | None = None,
    started_at_set: bool = False,
    finished_at_set: bool = False,
) -> AgentRun:
    """Update mutable run state without committing the session."""

    if status is not None:
        normalized_status = _validate_status(status)
        agent_run.status = normalized_status
        if normalized_status == "running" and agent_run.started_at is None:
            agent_run.started_at = utc_now()
        if (
            normalized_status in FINAL_AGENT_RUN_STATUSES
            and agent_run.finished_at is None
        ):
            agent_run.finished_at = utc_now()
    if artifacts_uri is not None:
        agent_run.artifacts_uri = artifacts_uri
    if report_uri is not None:
        agent_run.report_uri = report_uri
    if summary_json is not None:
        agent_run.summary_json = summary_json
    if error_message is not None:
        agent_run.error_message = error_message
    if started_at_set and agent_run.started_at is None:
        agent_run.started_at = utc_now()
    if finished_at_set and agent_run.finished_at is None:
        agent_run.finished_at = utc_now()
    return agent_run


def get_agent_run_by_run_id(session: Session, run_id: str) -> AgentRun | None:
    """Return an agent run by stable external run id."""

    return session.scalar(select(AgentRun).where(AgentRun.run_id == run_id))


def list_agent_runs(
    session: Session,
    *,
    status: str | None = None,
    agent_name: str | None = None,
    profile_name: str | None = None,
    binding_id: int | None = None,
    limit: int = 50,
) -> list[AgentRun]:
    """List agent runs using safe, bounded filters."""

    statement: Select[tuple[AgentRun]] = select(AgentRun)
    if status is not None:
        statement = statement.where(AgentRun.status == _validate_status(status))
    if agent_name:
        statement = statement.where(AgentRun.agent_name == agent_name)
    if profile_name:
        statement = statement.where(
            AgentRun.normalized_profile_name == normalize_profile_name(profile_name)
        )
    if binding_id is not None:
        statement = statement.where(AgentRun.binding_id == binding_id)
    statement = statement.order_by(AgentRun.created_at.desc()).limit(
        max(1, min(limit, 200))
    )
    return list(session.scalars(statement))


def _validate_status(status: str) -> str:
    normalized = status.strip().lower()
    if normalized not in AGENT_RUN_STATUSES:
        raise AgentRunRegistryError(
            "Invalid agent run status "
            f"{status!r}. Expected one of {list(AGENT_RUN_STATUSES)!r}."
        )
    return normalized


def _validate_trigger_type(trigger_type: str) -> str:
    normalized = trigger_type.strip().lower()
    if normalized not in AGENT_RUN_TRIGGER_TYPES:
        raise AgentRunRegistryError(
            "Invalid agent run trigger_type "
            f"{trigger_type!r}. Expected one of {list(AGENT_RUN_TRIGGER_TYPES)!r}."
        )
    return normalized


def _resolve_profile(
    session: Session, profile_name: str | None
) -> TerminologyProfile | None:
    if not profile_name:
        return None
    normalized = normalize_profile_name(profile_name)
    profile = session.scalar(
        select(TerminologyProfile).where(
            TerminologyProfile.normalized_name == normalized
        )
    )
    if profile is None:
        raise AgentRunRegistryError(f"Profile not found: {profile_name}")
    return profile


def _resolve_binding(
    session: Session, binding_id: int | None
) -> ElasticsearchBinding | None:
    if binding_id is None:
        return None
    binding = session.get(ElasticsearchBinding, binding_id)
    if binding is None:
        raise AgentRunRegistryError(f"Elasticsearch binding not found: {binding_id}")
    return binding
