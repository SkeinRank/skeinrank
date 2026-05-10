"""Background execution helpers for Elasticsearch enrichment jobs."""

from __future__ import annotations

from typing import Any

from skeinrank_governance.models import ElasticsearchEnrichmentJob, utc_now
from sqlalchemy import select

from .config import GovernanceApiConfig
from .dependencies import create_engine_for_config
from .elasticsearch import ElasticsearchDiscoveryClient, ElasticsearchDiscoveryError


def run_elasticsearch_enrichment_job(
    *, job_id: int, config: GovernanceApiConfig | None = None
) -> dict[str, Any]:
    """Run one queued Elasticsearch enrichment job and persist its status.

    This function is used by the Celery task process. It creates its own DB
    engine/session from environment-derived config so workers can run as separate
    processes or containers from the FastAPI server.
    """

    config = config or GovernanceApiConfig.from_env()
    engine = create_engine_for_config(config)
    try:
        from skeinrank_governance import create_session_factory

        session_factory = create_session_factory(engine)
        with session_factory() as session:
            job = session.scalar(
                select(ElasticsearchEnrichmentJob).where(
                    ElasticsearchEnrichmentJob.id == job_id
                )
            )
            if job is None:
                raise ElasticsearchDiscoveryError(
                    f"Elasticsearch enrichment job not found: {job_id}"
                )
            if job.status not in {"queued", "running"}:
                return {
                    "job_id": job_id,
                    "status": job.status,
                    "skipped": True,
                    "reason": "Job is no longer queued or running.",
                }

            job.status = "running"
            if job.started_at is None:
                job.started_at = utc_now()
            session.commit()
            session.refresh(job)

            try:
                client = ElasticsearchDiscoveryClient(config)
                if not client.is_configured:
                    raise ElasticsearchDiscoveryError(
                        "Elasticsearch URL is not configured."
                    )

                # Import lazily to avoid coupling FastAPI route registration to worker startup.
                from .routes.governance import _execute_elasticsearch_enrichment_job

                max_documents = _job_max_documents(job)
                result = _execute_elasticsearch_enrichment_job(
                    client=client,
                    session=session,
                    binding=job.binding,
                    job=job,
                    max_documents=max_documents,
                )
            except ElasticsearchDiscoveryError as exc:
                job.status = "failed"
                job.error_message = str(exc)
                job.finished_at = utc_now()
                session.commit()
                session.refresh(job)
                return {"job_id": job_id, "status": "failed", "error": str(exc)}

            result = {**result, "job_backend": "celery"}
            job.status = "succeeded"
            job.documents_seen = int(result.get("documents_seen", 0))
            job.documents_enriched = int(result.get("documents_enriched", 0))
            job.documents_failed = int(result.get("documents_failed", 0))
            job.result_json = result
            job.error_message = None
            job.finished_at = utc_now()
            session.commit()
            session.refresh(job)
            return {"job_id": job_id, "status": "succeeded", "result": result}
    finally:
        engine.dispose()


def _job_max_documents(job: ElasticsearchEnrichmentJob) -> int:
    result_json = job.result_json or {}
    max_documents = result_json.get("max_documents")
    if isinstance(max_documents, int) and max_documents > 0:
        return max_documents
    return 1000
