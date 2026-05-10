"""Queue dispatch helpers for Elasticsearch enrichment jobs."""

from __future__ import annotations

from dataclasses import dataclass

from .config import GovernanceApiConfig


@dataclass(frozen=True)
class EnqueuedTask:
    """Metadata returned after an enrichment job is dispatched to a worker queue."""

    task_id: str | None
    queue: str


class EnrichmentJobQueueError(RuntimeError):
    """Raised when an enrichment job cannot be dispatched to the configured queue."""


def enqueue_elasticsearch_enrichment_job(
    *, config: GovernanceApiConfig, job_id: int
) -> EnqueuedTask:
    """Dispatch an enrichment job coordinator task to the configured backend."""

    if config.enrichment_jobs_backend != "celery":
        raise EnrichmentJobQueueError(
            f"Unsupported enrichment jobs backend: {config.enrichment_jobs_backend}"
        )

    try:
        from .tasks import run_elasticsearch_enrichment_job_task
    except RuntimeError as exc:
        raise EnrichmentJobQueueError(str(exc)) from exc
    except ImportError as exc:  # pragma: no cover - defensive for partial installs
        raise EnrichmentJobQueueError(str(exc)) from exc

    return _enqueue_celery_task(
        run_elasticsearch_enrichment_job_task,
        config=config,
        args=(job_id,),
    )


def enqueue_elasticsearch_enrichment_chunk(
    *,
    config: GovernanceApiConfig,
    job_id: int,
    chunk_index: int,
    offset: int,
    limit: int,
) -> EnqueuedTask:
    """Dispatch one bounded enrichment chunk task to Celery/RabbitMQ."""

    if config.enrichment_jobs_backend != "celery":
        raise EnrichmentJobQueueError(
            f"Unsupported enrichment jobs backend: {config.enrichment_jobs_backend}"
        )

    try:
        from .tasks import run_elasticsearch_enrichment_chunk_task
    except RuntimeError as exc:
        raise EnrichmentJobQueueError(str(exc)) from exc
    except ImportError as exc:  # pragma: no cover - defensive for partial installs
        raise EnrichmentJobQueueError(str(exc)) from exc

    return _enqueue_celery_task(
        run_elasticsearch_enrichment_chunk_task,
        config=config,
        args=(job_id, chunk_index, offset, limit),
    )


def _enqueue_celery_task(
    task, *, config: GovernanceApiConfig, args: tuple
) -> EnqueuedTask:
    apply_async = getattr(task, "apply_async", None)
    delay = getattr(task, "delay", None)
    if apply_async is None and delay is None:
        raise EnrichmentJobQueueError(
            "Celery is not installed. Install the governance API worker dependencies "
            "before using SKEINRANK_GOVERNANCE_API_ENRICHMENT_JOBS_BACKEND=celery."
        )

    if apply_async is not None:
        async_result = apply_async(args=args, queue=config.celery_task_queue)
    else:  # pragma: no cover - compatibility fallback
        async_result = delay(*args)
    return EnqueuedTask(
        task_id=getattr(async_result, "id", None), queue=config.celery_task_queue
    )
