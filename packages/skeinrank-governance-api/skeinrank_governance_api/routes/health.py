"""Health and readiness endpoints for the governance API."""

from __future__ import annotations

from fastapi import APIRouter, Request
from sqlalchemy import text
from sqlalchemy.engine import Engine

from ..elasticsearch import ElasticsearchDiscoveryClient, ElasticsearchDiscoveryError
from ..schema_health import check_schema_health
from ..schemas import (
    DatabaseHealth,
    ExternalDependencyHealth,
    HealthzResponse,
    LivezResponse,
    ReadyzResponse,
    SchemaHealth,
    ServiceInfo,
)

router = APIRouter(tags=["health"])


@router.get("/livez", response_model=LivezResponse)
def livez(request: Request) -> LivezResponse:
    """Return process liveness without checking external dependencies."""

    config = request.app.state.config
    return LivezResponse(
        status="ok",
        service=_service_info(config),
    )


@router.get("/healthz", response_model=HealthzResponse)
def healthz(request: Request) -> HealthzResponse:
    """Return service, database connectivity, and schema migration status."""

    engine: Engine = request.app.state.governance_engine
    config = request.app.state.config
    database = _check_database(engine, url=config.database_url)
    schema = check_schema_health(engine, config=config) if database.ok else None
    return HealthzResponse(
        status="ok" if database.ok else "degraded",
        service=_service_info(config),
        database=database,
        schema_health=schema or _unavailable_schema_health(),
    )


@router.get("/readyz", response_model=ReadyzResponse)
def readyz(request: Request) -> ReadyzResponse:
    """Return readiness status for database, schema, and search dependency."""

    engine: Engine = request.app.state.governance_engine
    config = request.app.state.config
    database = _check_database(engine, url=config.database_url)
    schema = check_schema_health(engine, config=config) if database.ok else None
    elasticsearch = _check_elasticsearch(ElasticsearchDiscoveryClient(config))
    ready = (
        database.ok
        and bool(schema and schema.ok)
        and (elasticsearch.ok or not elasticsearch.configured)
    )
    return ReadyzResponse(
        status="ok" if ready else "degraded",
        service=_service_info(config),
        database=database,
        schema_health=schema or _unavailable_schema_health(),
        elasticsearch=elasticsearch,
    )


@router.get("/schema/health", response_model=SchemaHealth)
def schema_health(request: Request) -> SchemaHealth:
    """Return read-only Alembic and metadata health for the governance schema."""

    engine: Engine = request.app.state.governance_engine
    config = request.app.state.config
    return check_schema_health(engine, config=config)


def _service_info(config) -> ServiceInfo:
    return ServiceInfo(
        name=config.service_name,
        version=config.service_version,
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


def _check_elasticsearch(
    client: ElasticsearchDiscoveryClient,
) -> ExternalDependencyHealth:
    if not client.is_configured:
        return ExternalDependencyHealth(ok=False, configured=False)
    try:
        info = client.cluster_info()
        version = info.get("version") if isinstance(info.get("version"), dict) else {}
        return ExternalDependencyHealth(
            ok=True,
            configured=True,
            url=_safe_url(client.url),
            name=str(info.get("cluster_name") or info.get("name") or ""),
            version=str(version.get("number") or "")
            if isinstance(version, dict)
            else None,
        )
    except ElasticsearchDiscoveryError as exc:
        return ExternalDependencyHealth(
            ok=False,
            configured=True,
            url=_safe_url(client.url),
            error=f"{type(exc).__name__}: {exc}",
        )


def _safe_url(url: str) -> str:
    if "://" not in url:
        return url
    scheme, rest = url.split("://", 1)
    if "@" not in rest:
        return url
    return f"{scheme}://***@{rest.rsplit('@', 1)[1]}"


def _unavailable_schema_health() -> SchemaHealth:
    return SchemaHealth(
        ok=False,
        alembic_version_present=False,
        current_revision=None,
        current_revisions=[],
        head_revision=None,
        migration_heads=[],
        current_matches_head=False,
        multiple_heads=False,
        missing_tables=[],
        expected_tables_count=0,
        database_tables_count=0,
        error="database_unavailable",
    )
