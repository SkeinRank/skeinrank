"""Product dashboard summary endpoint for the governance console."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from skeinrank_governance.models import (
    CanonicalTerm,
    ElasticsearchBinding,
    ElasticsearchEnrichmentJob,
    TermAlias,
    TerminologyProfile,
)
from sqlalchemy import func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from ..auth import AuthContext, require_roles
from ..dependencies import get_session
from ..elasticsearch import ElasticsearchDiscoveryClient, ElasticsearchDiscoveryError
from ..schemas import (
    DashboardBindingSummary,
    DashboardCounts,
    DashboardReadinessItem,
    DashboardRecentJob,
    DashboardSetupChecklist,
    DashboardSummaryResponse,
)

router = APIRouter(
    prefix="/v1/dashboard",
    tags=["dashboard"],
)

_RUNNING_JOB_STATUSES = {"queued", "running", "cancel_requested"}
_CELERY_READINESS_TIMEOUT_SECONDS = 1.5


@router.get("/summary", response_model=DashboardSummaryResponse)
def get_dashboard_summary(
    request: Request,
    _current_user: AuthContext = Depends(
        require_roles("admin", "moderator", "contributor")
    ),
    session: Session = Depends(get_session),
) -> DashboardSummaryResponse:
    """Return a compact product-state summary for the UI home page."""

    bindings = list(
        session.scalars(
            select(ElasticsearchBinding)
            .join(TerminologyProfile)
            .order_by(
                ElasticsearchBinding.is_enabled.desc(),
                ElasticsearchBinding.normalized_name,
            )
        )
    )
    latest_jobs_by_binding = _latest_jobs_by_binding(session, bindings)
    binding_summaries = [
        _binding_summary(binding, latest_jobs_by_binding.get(binding.id))
        for binding in bindings
    ]
    recent_jobs = [
        _recent_job_response(job)
        for job in session.scalars(
            select(ElasticsearchEnrichmentJob)
            .join(ElasticsearchBinding)
            .order_by(
                ElasticsearchEnrichmentJob.created_at.desc(),
                ElasticsearchEnrichmentJob.id.desc(),
            )
            .limit(5)
        )
    ]

    profile_count = _count(session, TerminologyProfile.id)
    canonical_term_count = _count(session, CanonicalTerm.id)
    alias_count = _count(session, TermAlias.id)
    running_jobs_count = _count_jobs_by_status(session, _RUNNING_JOB_STATUSES)
    failed_jobs_count = _count_jobs_by_status(session, {"failed"})
    succeeded_jobs_count = _count_jobs_by_status(session, {"succeeded"})

    ready_bindings_count = sum(
        1 for binding in binding_summaries if binding.status == "ready"
    )
    stale_bindings_count = sum(
        1 for binding in binding_summaries if binding.status == "stale"
    )
    updating_bindings_count = sum(
        1 for binding in binding_summaries if binding.status == "updating"
    )
    failed_bindings_count = sum(
        1 for binding in binding_summaries if binding.status == "failed"
    )
    never_enriched_bindings_count = sum(
        1 for binding in binding_summaries if binding.status == "never_enriched"
    )

    config = request.app.state.config
    readiness = {
        "database": _database_readiness(
            request.app.state.governance_engine,
            url=config.database_url,
        ),
        "elasticsearch": _elasticsearch_readiness(ElasticsearchDiscoveryClient(config)),
        "rabbitmq": _rabbitmq_readiness(config),
        "worker": _worker_readiness(config),
        "auth": DashboardReadinessItem(
            status="enabled" if config.auth_enabled else "disabled",
            configured=True,
            message="Authentication is enabled."
            if config.auth_enabled
            else "Authentication is disabled for local development.",
        ),
    }

    return DashboardSummaryResponse(
        readiness=readiness,
        counts=DashboardCounts(
            profiles=profile_count,
            canonical_terms=canonical_term_count,
            aliases=alias_count,
            bindings=len(binding_summaries),
            ready_bindings=ready_bindings_count,
            stale_bindings=stale_bindings_count,
            updating_bindings=updating_bindings_count,
            failed_bindings=failed_bindings_count,
            never_enriched_bindings=never_enriched_bindings_count,
            running_jobs=running_jobs_count,
            failed_jobs=failed_jobs_count,
        ),
        setup=DashboardSetupChecklist(
            has_profile=profile_count > 0,
            has_terms=canonical_term_count > 0,
            has_binding=len(binding_summaries) > 0,
            has_successful_enrichment=succeeded_jobs_count > 0,
            has_runtime_snapshot=ready_bindings_count > 0,
        ),
        bindings=binding_summaries,
        recent_jobs=recent_jobs,
    )


def _count(session: Session, column) -> int:
    return int(session.scalar(select(func.count(column))) or 0)


def _count_jobs_by_status(session: Session, statuses: set[str]) -> int:
    return int(
        session.scalar(
            select(func.count(ElasticsearchEnrichmentJob.id)).where(
                ElasticsearchEnrichmentJob.status.in_(tuple(statuses))
            )
        )
        or 0
    )


def _latest_jobs_by_binding(
    session: Session,
    bindings: list[ElasticsearchBinding],
) -> dict[int, ElasticsearchEnrichmentJob]:
    binding_ids = [binding.id for binding in bindings]
    if not binding_ids:
        return {}

    jobs = list(
        session.scalars(
            select(ElasticsearchEnrichmentJob)
            .where(ElasticsearchEnrichmentJob.binding_id.in_(binding_ids))
            .order_by(
                ElasticsearchEnrichmentJob.binding_id,
                ElasticsearchEnrichmentJob.created_at.desc(),
                ElasticsearchEnrichmentJob.id.desc(),
            )
        )
    )
    latest: dict[int, ElasticsearchEnrichmentJob] = {}
    for job in jobs:
        latest.setdefault(job.binding_id, job)
    return latest


def _binding_summary(
    binding: ElasticsearchBinding,
    latest_job: ElasticsearchEnrichmentJob | None,
) -> DashboardBindingSummary:
    return DashboardBindingSummary(
        id=binding.id,
        name=binding.name,
        profile_name=binding.profile.name,
        index_name=binding.index_name,
        is_enabled=binding.is_enabled,
        status=_binding_status(binding, latest_job),
        snapshot_version=binding.last_successful_snapshot_version,
        pending_snapshot_version=binding.pending_snapshot_version,
        last_successful_job_id=binding.last_successful_job_id,
        latest_job=_recent_job_response(latest_job) if latest_job else None,
        updated_at=binding.updated_at,
    )


def _binding_status(
    binding: ElasticsearchBinding,
    latest_job: ElasticsearchEnrichmentJob | None,
) -> str:
    if not binding.is_enabled:
        return "disabled"
    if latest_job and latest_job.status in _RUNNING_JOB_STATUSES:
        return "updating"
    if latest_job and latest_job.status == "failed":
        return "failed"
    if binding.pending_snapshot_version and binding.last_successful_snapshot_version:
        return "stale"
    if binding.pending_snapshot_version:
        return "updating"
    if binding.last_successful_snapshot_version:
        return "ready"
    return "never_enriched"


def _recent_job_response(job: ElasticsearchEnrichmentJob) -> DashboardRecentJob:
    return DashboardRecentJob(
        id=job.id,
        binding_id=job.binding_id,
        binding_name=job.binding.name,
        profile_name=job.profile.name,
        status=job.status,
        source_index=job.source_index,
        target_index=job.target_index,
        alias_name=job.alias_name,
        snapshot_version=job.snapshot_version,
        documents_seen=job.documents_seen,
        documents_enriched=job.documents_enriched,
        documents_failed=job.documents_failed,
        error_message=job.error_message,
        started_at=job.started_at,
        finished_at=job.finished_at,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


def _database_readiness(engine: Engine, *, url: str) -> DashboardReadinessItem:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return DashboardReadinessItem(
            status="ok",
            configured=True,
            message="Database is reachable.",
            url=_safe_url(url),
        )
    except Exception as exc:
        return DashboardReadinessItem(
            status="degraded",
            configured=True,
            message=f"{type(exc).__name__}: {exc}",
            url=_safe_url(url),
        )


def _elasticsearch_readiness(
    client: ElasticsearchDiscoveryClient,
) -> DashboardReadinessItem:
    if not client.is_configured:
        return DashboardReadinessItem(
            status="not_configured",
            configured=False,
            message="Elasticsearch URL is not configured.",
        )
    try:
        info = client.cluster_info()
    except ElasticsearchDiscoveryError as exc:
        return DashboardReadinessItem(
            status="degraded",
            configured=True,
            message=str(exc),
            url=_safe_url(client.url),
        )

    version = info.get("version") if isinstance(info, dict) else None
    version_number = version.get("number") if isinstance(version, dict) else None
    cluster_name = info.get("cluster_name") if isinstance(info, dict) else None
    return DashboardReadinessItem(
        status="ok",
        configured=True,
        message="Elasticsearch is reachable.",
        url=_safe_url(client.url),
        name=str(cluster_name) if cluster_name else None,
        version=str(version_number) if version_number else None,
    )


def _rabbitmq_readiness(config) -> DashboardReadinessItem:
    if config.enrichment_jobs_backend != "celery":
        return DashboardReadinessItem(
            status="not_required",
            configured=False,
            message="Synchronous enrichment backend is active.",
        )

    try:
        _check_celery_broker(
            config.celery_broker_url,
            timeout_seconds=_CELERY_READINESS_TIMEOUT_SECONDS,
        )
    except Exception as exc:
        return DashboardReadinessItem(
            status="degraded",
            configured=True,
            message=f"{type(exc).__name__}: {exc}",
            url=_safe_url(config.celery_broker_url),
        )

    return DashboardReadinessItem(
        status="ok",
        configured=True,
        message="RabbitMQ broker is reachable for Celery enrichment jobs.",
        url=_safe_url(config.celery_broker_url),
    )


def _worker_readiness(config) -> DashboardReadinessItem:
    if config.enrichment_jobs_backend != "celery":
        return DashboardReadinessItem(
            status="not_required",
            configured=False,
            message="Worker is not required for synchronous enrichment jobs.",
        )

    try:
        ping_response = _ping_celery_workers(
            config.celery_broker_url,
            timeout_seconds=_CELERY_READINESS_TIMEOUT_SECONDS,
        )
    except Exception as exc:
        return DashboardReadinessItem(
            status="degraded",
            configured=True,
            message=f"{type(exc).__name__}: {exc}",
            url=_safe_url(config.celery_broker_url),
        )

    if not ping_response:
        return DashboardReadinessItem(
            status="degraded",
            configured=True,
            message="No Celery enrichment workers responded to ping.",
            url=_safe_url(config.celery_broker_url),
        )

    worker_count = len(ping_response)
    worker_label = "worker" if worker_count == 1 else "workers"
    return DashboardReadinessItem(
        status="ok",
        configured=True,
        message=f"{worker_count} Celery enrichment {worker_label} responded to ping.",
        url=_safe_url(config.celery_broker_url),
        name=", ".join(sorted(str(name) for name in ping_response.keys())),
    )


def _check_celery_broker(url: str, *, timeout_seconds: float) -> None:
    try:
        from kombu import Connection
    except ImportError as exc:  # pragma: no cover - celery dependency supplies kombu
        raise RuntimeError("kombu is not installed") from exc

    with Connection(url, connect_timeout=timeout_seconds) as connection:
        connection.connect()


def _ping_celery_workers(
    url: str,
    *,
    timeout_seconds: float,
) -> dict[str, object] | None:
    try:
        from celery import Celery
    except ImportError as exc:  # pragma: no cover - optional worker dependency guard
        raise RuntimeError("celery is not installed") from exc

    app = Celery("skeinrank_governance_dashboard", broker=url)
    app.conf.update(
        broker_connection_timeout=timeout_seconds,
        broker_transport_options={"socket_timeout": timeout_seconds},
    )
    try:
        inspector = app.control.inspect(timeout=timeout_seconds)
        response = inspector.ping()
    finally:
        close_app = getattr(app, "close", None)
        if close_app:
            close_app()
    return response


def _safe_url(url: str | None) -> str | None:
    if not url or "://" not in url:
        return url
    scheme, rest = url.split("://", 1)
    if "@" not in rest:
        return url
    return f"{scheme}://***@{rest.rsplit('@', 1)[1]}"
