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
    """Dispatch an enrichment job to the configured asynchronous backend.

    The governance API keeps ``sync`` as the default backend for local/dev use.
    When ``celery`` is configured, this helper imports the Celery task lazily so
    normal API startup and tests do not require a running RabbitMQ broker.
    """

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

    delay = getattr(run_elasticsearch_enrichment_job_task, "delay", None)
    if delay is None:
        raise EnrichmentJobQueueError(
            "Celery is not installed. Install the governance API worker dependencies "
            "before using SKEINRANK_GOVERNANCE_API_ENRICHMENT_JOBS_BACKEND=celery."
        )

    task = delay(job_id)
    return EnqueuedTask(
        task_id=getattr(task, "id", None), queue=config.celery_task_queue
    )
