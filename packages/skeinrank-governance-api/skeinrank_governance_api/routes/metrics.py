"""Prometheus metrics endpoint for the governance API."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response

from ..observability.metrics import render_prometheus_metrics

router = APIRouter(tags=["observability"])


@router.get("/metrics", include_in_schema=False)
def metrics(request: Request) -> Response:
    """Return Prometheus text exposition metrics from the default path."""

    return metrics_response(request)


def metrics_response(request: Request) -> Response:
    """Return Prometheus text exposition metrics."""

    config = request.app.state.config
    if not config.metrics_enabled:
        return Response(
            content="metrics disabled\n",
            media_type="text/plain; version=0.0.4; charset=utf-8",
            status_code=404,
        )
    return Response(
        content=render_prometheus_metrics(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )
