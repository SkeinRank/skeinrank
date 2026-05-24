"""Agent run registry endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from skeinrank_governance.models import AgentRun
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..agent_run_registry import (
    AgentRunRegistryError,
    create_agent_run,
    get_agent_run_by_run_id,
    list_agent_runs,
    update_agent_run,
)
from ..auth import AuthContext, require_roles
from ..dependencies import get_session
from ..schemas import AgentRunCreateRequest, AgentRunResponse, AgentRunUpdateRequest

router = APIRouter(prefix="/v1/agents", tags=["agents"])


@router.post(
    "/runs",
    response_model=AgentRunResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_agent_run_endpoint(
    request: AgentRunCreateRequest,
    current_user: AuthContext = Depends(
        require_roles("admin", "moderator", "contributor")
    ),
    session: Session = Depends(get_session),
) -> AgentRunResponse:
    """Register one agent workflow run without executing the agent."""

    try:
        agent_run = create_agent_run(
            session,
            run_id=request.run_id,
            agent_name=request.agent_name,
            agent_version=request.agent_version,
            status=request.status,
            trigger_type=request.trigger_type,
            profile_name=request.profile_name,
            binding_id=request.binding_id,
            openrouter_model=request.openrouter_model,
            prompt_version=request.prompt_version,
            workflow_engine=request.workflow_engine,
            config_hash=request.config_hash,
            artifacts_uri=request.artifacts_uri,
            report_uri=request.report_uri,
            summary_json=request.summary,
            error_message=request.error_message,
            requested_by=request.requested_by or current_user.username,
        )
        session.commit()
        session.refresh(agent_run)
        return _agent_run_response(agent_run)
    except AgentRunRegistryError as exc:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Agent run already exists for this run_id.",
        ) from exc


@router.get("/runs", response_model=list[AgentRunResponse])
def list_agent_runs_endpoint(
    status_filter: str | None = Query(default=None, alias="status"),
    agent_name: str | None = None,
    profile_name: str | None = None,
    binding_id: int | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    _current_user: AuthContext = Depends(
        require_roles("admin", "moderator", "contributor")
    ),
    session: Session = Depends(get_session),
) -> list[AgentRunResponse]:
    """List registered agent runs."""

    try:
        runs = list_agent_runs(
            session,
            status=status_filter,
            agent_name=agent_name,
            profile_name=profile_name,
            binding_id=binding_id,
            limit=limit,
        )
    except AgentRunRegistryError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return [_agent_run_response(agent_run) for agent_run in runs]


@router.get("/runs/{run_id}", response_model=AgentRunResponse)
def get_agent_run_endpoint(
    run_id: str,
    _current_user: AuthContext = Depends(
        require_roles("admin", "moderator", "contributor")
    ),
    session: Session = Depends(get_session),
) -> AgentRunResponse:
    """Return one registered agent run by stable run id."""

    agent_run = get_agent_run_by_run_id(session, run_id)
    if agent_run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Agent run not found"
        )
    return _agent_run_response(agent_run)


@router.patch("/runs/{run_id}", response_model=AgentRunResponse)
def update_agent_run_endpoint(
    run_id: str,
    request: AgentRunUpdateRequest,
    _current_user: AuthContext = Depends(
        require_roles("admin", "moderator", "contributor")
    ),
    session: Session = Depends(get_session),
) -> AgentRunResponse:
    """Update lifecycle metadata for one registered agent run."""

    agent_run = get_agent_run_by_run_id(session, run_id)
    if agent_run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Agent run not found"
        )
    try:
        update_agent_run(
            agent_run,
            status=request.status,
            artifacts_uri=request.artifacts_uri,
            report_uri=request.report_uri,
            summary_json=request.summary,
            error_message=request.error_message,
            started_at_set=request.mark_started,
            finished_at_set=request.mark_finished,
        )
        session.commit()
        session.refresh(agent_run)
        return _agent_run_response(agent_run)
    except AgentRunRegistryError as exc:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


def _agent_run_response(agent_run: AgentRun) -> AgentRunResponse:
    return AgentRunResponse(
        id=agent_run.id,
        run_id=agent_run.run_id,
        agent_name=agent_run.agent_name,
        agent_version=agent_run.agent_version,
        status=agent_run.status,
        trigger_type=agent_run.trigger_type,
        profile_name=agent_run.profile_name,
        normalized_profile_name=agent_run.normalized_profile_name,
        binding_id=agent_run.binding_id,
        openrouter_model=agent_run.openrouter_model,
        prompt_version=agent_run.prompt_version,
        workflow_engine=agent_run.workflow_engine,
        config_hash=agent_run.config_hash,
        artifacts_uri=agent_run.artifacts_uri,
        report_uri=agent_run.report_uri,
        summary=agent_run.summary_json or {},
        error_message=agent_run.error_message,
        requested_by=agent_run.requested_by,
        started_at=agent_run.started_at,
        finished_at=agent_run.finished_at,
        created_at=agent_run.created_at,
        updated_at=agent_run.updated_at,
    )
