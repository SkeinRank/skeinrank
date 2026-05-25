"""Troubleshooting report helpers for SkeinRank governance operations."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from typing import Any

from skeinrank_governance.models import (
    AgentCandidateObservation,
    AgentDocumentVisit,
    AgentEvidenceWindow,
    AgentLlmReview,
    AgentProposalAttempt,
    AgentRun,
    CanonicalTerm,
    ElasticsearchBinding,
    GovernanceSuggestion,
    ProfileSnapshot,
    TermAlias,
    TerminologyProfile,
)
from sqlalchemy import func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .config import GovernanceApiConfig
from .dependencies import create_engine_for_config
from .elasticsearch import ElasticsearchDiscoveryClient, ElasticsearchDiscoveryError
from .schema_health import check_schema_health
from .schemas import (
    ServiceInfo,
    TroubleshootingCheck,
    TroubleshootingReportResponse,
    TroubleshootingRuntimeConfig,
)

CORE_TABLE_COUNT_MODELS = (
    TerminologyProfile,
    CanonicalTerm,
    TermAlias,
    ElasticsearchBinding,
    GovernanceSuggestion,
    ProfileSnapshot,
    AgentRun,
    AgentDocumentVisit,
    AgentCandidateObservation,
    AgentEvidenceWindow,
    AgentLlmReview,
    AgentProposalAttempt,
)


def generate_troubleshooting_report(
    *,
    config: GovernanceApiConfig,
    engine: Engine,
    session_factory: sessionmaker[Session],
    request_id: str | None = None,
) -> TroubleshootingReportResponse:
    """Build a read-only troubleshooting report for operators.

    The report intentionally avoids secrets and mutating operations. It can be
    served over HTTP or generated from the CLI against the configured DB URL.
    """

    checks: list[TroubleshootingCheck] = []
    database_ok, database_message = _database_check(engine)
    checks.append(
        TroubleshootingCheck(
            name="database",
            status="ok" if database_ok else "degraded",
            message=database_message,
            details={"url": _safe_url(config.database_url)},
        )
    )

    schema_ok = False
    if database_ok:
        schema_health = check_schema_health(engine, config=config)
        schema_ok = schema_health.ok
        checks.append(
            TroubleshootingCheck(
                name="schema",
                status="ok" if schema_health.ok else "degraded",
                message="schema matches Alembic head"
                if schema_health.ok
                else "schema does not match Alembic head or metadata",
                details={
                    "alembic_version_present": schema_health.alembic_version_present,
                    "current_revision": schema_health.current_revision,
                    "head_revision": schema_health.head_revision,
                    "current_matches_head": schema_health.current_matches_head,
                    "multiple_heads": schema_health.multiple_heads,
                    "missing_tables": schema_health.missing_tables,
                    "expected_tables_count": schema_health.expected_tables_count,
                    "database_tables_count": schema_health.database_tables_count,
                    "error": schema_health.error,
                },
            )
        )
    else:
        checks.append(
            TroubleshootingCheck(
                name="schema",
                status="unknown",
                message="database unavailable; schema check skipped",
            )
        )

    elasticsearch_status, elasticsearch_details = _elasticsearch_check(config)
    checks.append(
        TroubleshootingCheck(
            name="elasticsearch",
            status=elasticsearch_status,
            message=elasticsearch_details.get("message"),
            details={
                key: value
                for key, value in elasticsearch_details.items()
                if key != "message"
            },
        )
    )

    checks.append(
        TroubleshootingCheck(
            name="observability",
            status="ok" if config.observability_enabled else "disabled",
            message="request logs and metrics are enabled"
            if config.observability_enabled
            else "observability middleware is disabled",
            details={
                "log_format": config.log_format,
                "log_level": config.log_level,
                "access_log_enabled": config.access_log_enabled,
                "metrics_enabled": config.metrics_enabled,
                "metrics_path": config.metrics_path,
                "tracing_enabled": config.tracing_enabled,
            },
        )
    )

    counts: dict[str, int | None] = {}
    if database_ok:
        counts = _table_counts(session_factory)
    recommendations = _recommendations(
        database_ok=database_ok,
        schema_ok=schema_ok,
        config=config,
        checks=checks,
    )
    non_degraded_statuses = {"ok", "disabled", "not_configured"}
    overall_status = (
        "ok"
        if all(check.status in non_degraded_statuses for check in checks)
        else "degraded"
    )
    return TroubleshootingReportResponse(
        status=overall_status,
        generated_at=datetime.now(timezone.utc),
        service=ServiceInfo(name=config.service_name, version=config.service_version),
        environment=config.deployment_environment,
        request_id=request_id,
        config=TroubleshootingRuntimeConfig(
            database_url=_safe_url(config.database_url),
            create_tables_on_startup=config.create_tables_on_startup,
            auth_enabled=config.auth_enabled,
            production_security_enabled=config.production_security_enabled,
            observability_enabled=config.observability_enabled,
            log_format=config.log_format,
            log_level=config.log_level,
            metrics_enabled=config.metrics_enabled,
            metrics_path=config.metrics_path,
            tracing_enabled=config.tracing_enabled,
            elasticsearch_configured=bool(config.elasticsearch_url),
            enrichment_jobs_backend=config.enrichment_jobs_backend,
            celery_task_queue=config.celery_task_queue,
        ),
        checks=checks,
        counts=counts,
        recommendations=recommendations,
    )


def main(argv: list[str] | None = None) -> int:
    """Generate troubleshooting reports from the command line."""

    parser = argparse.ArgumentParser(
        prog="python -m skeinrank_governance_api.troubleshooting",
        description="Generate read-only SkeinRank governance troubleshooting reports.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    report_parser = subparsers.add_parser("report", help="Print a JSON report.")
    report_parser.add_argument(
        "--strict",
        action="store_true",
        help="Return exit code 1 when the report status is degraded.",
    )
    args = parser.parse_args(argv)

    if args.command != "report":  # pragma: no cover - argparse enforces commands
        parser.error(f"Unknown troubleshooting command: {args.command}")

    config = GovernanceApiConfig.from_env()
    engine = create_engine_for_config(config)
    from skeinrank_governance import create_session_factory

    session_factory = create_session_factory(engine)
    try:
        report = generate_troubleshooting_report(
            config=config,
            engine=engine,
            session_factory=session_factory,
        )
        print(json.dumps(report.model_dump(mode="json"), indent=2, ensure_ascii=False))
        return 1 if args.strict and report.status != "ok" else 0
    finally:
        engine.dispose()


def _database_check(engine: Engine) -> tuple[bool, str]:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True, "database connection succeeded"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def _elasticsearch_check(config: GovernanceApiConfig) -> tuple[str, dict[str, Any]]:
    client = ElasticsearchDiscoveryClient(config)
    if not client.is_configured:
        return (
            "not_configured",
            {"configured": False, "message": "Elasticsearch is not configured"},
        )
    try:
        info = client.cluster_info()
    except ElasticsearchDiscoveryError as exc:
        return (
            "degraded",
            {
                "configured": True,
                "url": _safe_url(client.url),
                "message": f"{type(exc).__name__}: {exc}",
            },
        )
    version = info.get("version") if isinstance(info.get("version"), dict) else {}
    return (
        "ok",
        {
            "configured": True,
            "url": _safe_url(client.url),
            "cluster": str(info.get("cluster_name") or info.get("name") or ""),
            "version": str(version.get("number") or "")
            if isinstance(version, dict)
            else None,
            "message": "Elasticsearch connection succeeded",
        },
    )


def _table_counts(session_factory: sessionmaker[Session]) -> dict[str, int | None]:
    counts: dict[str, int | None] = {}
    with session_factory() as session:
        for model in CORE_TABLE_COUNT_MODELS:
            table_name = str(model.__tablename__)
            try:
                counts[table_name] = int(
                    session.scalar(select(func.count()).select_from(model)) or 0
                )
            except Exception:
                session.rollback()
                counts[table_name] = None
    return counts


def _recommendations(
    *,
    database_ok: bool,
    schema_ok: bool,
    config: GovernanceApiConfig,
    checks: list[TroubleshootingCheck],
) -> list[str]:
    recommendations: list[str] = []
    if not database_ok:
        recommendations.append(
            "Check SKEINRANK_GOVERNANCE_API_DATABASE_URL and database connectivity."
        )
    elif not schema_ok:
        recommendations.append(
            "Run python -m skeinrank_governance_api.migrations upgrade head and check."
        )
    if config.create_tables_on_startup:
        recommendations.append(
            "Disable CREATE_TABLES in production-like runs and use Alembic migrations."
        )
    if config.log_format != "json" and config.deployment_environment in {
        "production",
        "staging",
    }:
        recommendations.append(
            "Use SKEINRANK_GOVERNANCE_API_LOG_FORMAT=json for production log ingestion."
        )
    if not config.metrics_enabled:
        recommendations.append("Enable Prometheus metrics for operational monitoring.")
    if any(
        check.name == "elasticsearch" and check.status == "degraded" for check in checks
    ):
        recommendations.append(
            "Check Elasticsearch URL, credentials, network path, and timeout settings."
        )
    return recommendations


def _safe_url(url: str | None) -> str | None:
    if not url or "://" not in url:
        return url
    scheme, rest = url.split("://", 1)
    if "@" not in rest:
        return url
    return f"{scheme}://***@{rest.rsplit('@', 1)[1]}"


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    raise SystemExit(main())
