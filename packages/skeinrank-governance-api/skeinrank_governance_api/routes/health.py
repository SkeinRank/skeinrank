"""Health endpoints for the governance API."""

from __future__ import annotations

from fastapi import APIRouter, Request
from sqlalchemy import text
from sqlalchemy.engine import Engine

from ..schemas import DatabaseHealth, HealthzResponse, ServiceInfo

router = APIRouter(tags=["health"])


@router.get("/healthz", response_model=HealthzResponse)
def healthz(request: Request) -> HealthzResponse:
    """Return service and database connectivity status."""

    engine: Engine = request.app.state.governance_engine
    config = request.app.state.config
    database = _check_database(engine, url=config.database_url)
    return HealthzResponse(
        status="ok" if database.ok else "degraded",
        service=ServiceInfo(
            name=config.service_name,
            version=config.service_version,
        ),
        database=database,
    )


def _check_database(engine: Engine, *, url: str) -> DatabaseHealth:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return DatabaseHealth(ok=True, url=_safe_url(url))
    except Exception as exc:
        return DatabaseHealth(
            ok=False,
            url=_safe_url(url),
            error=f"{type(exc).__name__}: {exc}",
        )


def _safe_url(url: str) -> str:
    if "://" not in url:
        return url
    scheme, rest = url.split("://", 1)
    if "@" not in rest:
        return url
    return f"{scheme}://***@{rest.rsplit('@', 1)[1]}"
