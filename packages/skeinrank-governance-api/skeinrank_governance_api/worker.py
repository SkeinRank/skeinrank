"""Celery app factory for SkeinRank governance background workers."""

from __future__ import annotations

from typing import Any

from .config import GovernanceApiConfig
from .observability import configure_logging, configure_tracing


class MissingCeleryApp:
    """Small stub used when Celery is not installed in sync-only environments."""

    missing_reason = (
        "Celery is not installed. Install the worker dependencies before starting "
        "skeinrank-governance-worker or celery -A skeinrank_governance_api.worker:celery_app."
    )

    def task(self, *_args: Any, **_kwargs: Any):
        def decorator(func):
            return func

        return decorator


def create_celery_app(config: GovernanceApiConfig | None = None):
    """Create and configure the Celery application used by workers."""

    try:
        from celery import Celery
    except ImportError as exc:  # pragma: no cover - depends on optional dependency
        raise RuntimeError(MissingCeleryApp.missing_reason) from exc

    config = config or GovernanceApiConfig.from_env()
    configure_logging(config)
    configure_tracing(config)
    app = Celery(
        "skeinrank_governance_api",
        broker=config.celery_broker_url,
        include=["skeinrank_governance_api.tasks"],
    )
    app.conf.update(
        task_default_queue=config.celery_task_queue,
        task_ignore_result=True,
        worker_prefetch_multiplier=1,
        task_acks_late=True,
    )
    return app


try:
    celery_app = create_celery_app()
except RuntimeError:
    celery_app = MissingCeleryApp()
