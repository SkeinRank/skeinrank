"""Celery task definitions for SkeinRank governance workers."""

from __future__ import annotations

from .job_runner import (
    run_elasticsearch_enrichment_chunk,
    run_elasticsearch_enrichment_job,
)
from .observability import start_span
from .worker import MissingCeleryApp, celery_app

if isinstance(celery_app, MissingCeleryApp):  # pragma: no cover - import guard
    raise RuntimeError(MissingCeleryApp.missing_reason)


@celery_app.task(name="skeinrank_governance_api.run_elasticsearch_enrichment_job")
def run_elasticsearch_enrichment_job_task(job_id: int) -> dict:
    """Prepare one queued Elasticsearch enrichment job and enqueue chunks."""

    with start_span(
        "celery.run_elasticsearch_enrichment_job",
        {"skeinrank.job_id": job_id},
    ):
        return run_elasticsearch_enrichment_job(job_id=job_id)


@celery_app.task(name="skeinrank_governance_api.run_elasticsearch_enrichment_chunk")
def run_elasticsearch_enrichment_chunk_task(
    job_id: int, chunk_index: int, offset: int, limit: int
) -> dict:
    """Run one bounded Elasticsearch enrichment chunk."""

    with start_span(
        "celery.run_elasticsearch_enrichment_chunk",
        {
            "skeinrank.job_id": job_id,
            "skeinrank.chunk_index": chunk_index,
            "skeinrank.chunk_offset": offset,
            "skeinrank.chunk_limit": limit,
        },
    ):
        return run_elasticsearch_enrichment_chunk(
            job_id=job_id,
            chunk_index=chunk_index,
            offset=offset,
            limit=limit,
        )
