"""Celery task definitions for SkeinRank governance workers."""

from __future__ import annotations

from .job_runner import (
    run_elasticsearch_enrichment_chunk,
    run_elasticsearch_enrichment_job,
)
from .worker import MissingCeleryApp, celery_app

if isinstance(celery_app, MissingCeleryApp):  # pragma: no cover - import guard
    raise RuntimeError(MissingCeleryApp.missing_reason)


@celery_app.task(name="skeinrank_governance_api.run_elasticsearch_enrichment_job")
def run_elasticsearch_enrichment_job_task(job_id: int) -> dict:
    """Prepare one queued Elasticsearch enrichment job and enqueue chunks."""

    return run_elasticsearch_enrichment_job(job_id=job_id)


@celery_app.task(name="skeinrank_governance_api.run_elasticsearch_enrichment_chunk")
def run_elasticsearch_enrichment_chunk_task(
    job_id: int, chunk_index: int, offset: int, limit: int
) -> dict:
    """Run one bounded Elasticsearch enrichment chunk."""

    return run_elasticsearch_enrichment_chunk(
        job_id=job_id,
        chunk_index=chunk_index,
        offset=offset,
        limit=limit,
    )
