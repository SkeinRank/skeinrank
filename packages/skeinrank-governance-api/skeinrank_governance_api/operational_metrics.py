"""Operational metrics refresh helpers for health and agent tracking state."""

from __future__ import annotations

from collections.abc import Mapping

from fastapi import FastAPI
from skeinrank_governance.models import (
    AGENT_CANDIDATE_OBSERVATION_STATUSES,
    AGENT_DOCUMENT_VISIT_STATUSES,
    AGENT_LLM_REVIEW_STATUSES,
    AGENT_PROPOSAL_ATTEMPT_STATUSES,
    AGENT_RUN_STATUSES,
    AgentCandidateObservation,
    AgentDocumentVisit,
    AgentEvidenceWindow,
    AgentLlmReview,
    AgentProposalAttempt,
    AgentRun,
)
from sqlalchemy import func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .elasticsearch import ElasticsearchDiscoveryClient, ElasticsearchDiscoveryError
from .observability.metrics import (
    current_time,
    elapsed_seconds,
    record_operational_metrics_refresh,
    set_agent_evidence_windows_current,
    set_agent_tracking_metric,
    set_operational_health_metrics,
)
from .schema_health import check_schema_health


def refresh_operational_metrics(app: FastAPI) -> None:
    """Refresh Prometheus gauges derived from DB health and persisted agent state.

    This function is intentionally best-effort. A metrics scrape must remain
    available even when the database, schema, or Elasticsearch dependency is
    degraded, so refresh errors are recorded as metrics and swallowed.
    """

    started_at = current_time()
    try:
        config = app.state.config
        engine: Engine = app.state.governance_engine
        session_factory: sessionmaker[Session] = app.state.governance_session_factory

        database_ok = _database_up(engine)
        schema = check_schema_health(engine, config=config) if database_ok else None
        elasticsearch_ok, elasticsearch_configured = _elasticsearch_status(config)

        set_operational_health_metrics(
            database_ok=database_ok,
            schema_ok=bool(schema and schema.ok),
            schema_current_matches_head=bool(schema and schema.current_matches_head),
            schema_missing_tables=len(schema.missing_tables) if schema else 0,
            alembic_multiple_heads=bool(schema and schema.multiple_heads),
            elasticsearch_ok=elasticsearch_ok,
            elasticsearch_configured=elasticsearch_configured,
        )

        if database_ok and schema is not None and not schema.missing_tables:
            _refresh_agent_tracking_metrics(session_factory)
        record_operational_metrics_refresh(
            status="succeeded", duration_seconds=elapsed_seconds(started_at)
        )
    except Exception:  # pragma: no cover - defensive metrics endpoint guard
        record_operational_metrics_refresh(
            status="failed", duration_seconds=elapsed_seconds(started_at)
        )


def _database_up(engine: Engine) -> bool:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def _elasticsearch_status(config) -> tuple[bool, bool]:
    client = ElasticsearchDiscoveryClient(config)
    if not client.is_configured:
        return False, False
    try:
        client.cluster_info()
        return True, True
    except ElasticsearchDiscoveryError:
        return False, True


def _refresh_agent_tracking_metrics(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        set_agent_tracking_metric(
            metric_name="skeinrank_agent_runs_current",
            status_values=AGENT_RUN_STATUSES,
            counts=_count_by_status(session, AgentRun.status),
        )
        set_agent_tracking_metric(
            metric_name="skeinrank_agent_document_visits_current",
            status_values=AGENT_DOCUMENT_VISIT_STATUSES,
            counts=_count_by_status(session, AgentDocumentVisit.visit_status),
        )
        set_agent_tracking_metric(
            metric_name="skeinrank_agent_candidate_observations_current",
            status_values=AGENT_CANDIDATE_OBSERVATION_STATUSES,
            counts=_count_by_status(
                session, AgentCandidateObservation.observation_status
            ),
        )
        set_agent_tracking_metric(
            metric_name="skeinrank_agent_llm_reviews_current",
            status_values=AGENT_LLM_REVIEW_STATUSES,
            counts=_count_by_status(session, AgentLlmReview.review_status),
        )
        set_agent_tracking_metric(
            metric_name="skeinrank_agent_proposal_attempts_current",
            status_values=AGENT_PROPOSAL_ATTEMPT_STATUSES,
            counts=_count_by_status(session, AgentProposalAttempt.attempt_status),
        )
        set_agent_evidence_windows_current(_count_rows(session, AgentEvidenceWindow))


def _count_by_status(session: Session, status_column) -> Mapping[str, int]:
    rows = session.execute(
        select(status_column, func.count()).group_by(status_column)
    ).all()
    return {str(status): int(count) for status, count in rows}


def _count_rows(session: Session, model) -> int:
    return int(session.scalar(select(func.count()).select_from(model)) or 0)
