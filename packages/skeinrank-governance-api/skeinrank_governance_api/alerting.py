"""Read-only alerting helpers for degraded SkeinRank governance state.

The module intentionally generates alert events and hook payload previews, but it
never delivers webhooks. Delivery can be handled by an external operator script,
CI job, or future integration that explicitly opts into sending notifications.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .schemas import (
    AlertingEvent,
    AlertingHookPreview,
    AlertingReportResponse,
    ServiceInfo,
)

ALERTING_REPORT_SCHEMA_VERSION = "skeinrank.alerting_report.v1"
ALERTING_HOOK_PAYLOAD_SCHEMA_VERSION = "skeinrank.alerting_hook_payload.v1"
ALERTING_PLAN_SCHEMA_VERSION = "skeinrank.alerting_plan.v1"

_OK_TROUBLESHOOTING_STATUSES = {"ok", "disabled", "not_configured"}
_CRITICAL_TROUBLESHOOTING_CHECKS = {"database", "schema"}
_CRITICAL_ISSUE_SEVERITIES = {"critical", "high"}


def build_alerting_report(
    *,
    service: ServiceInfo | dict[str, Any] | None = None,
    environment: str = "unknown",
    request_id: str | None = None,
    troubleshooting_report: Any | None = None,
    isolation_report: dict[str, Any] | None = None,
    generated_at: datetime | None = None,
) -> AlertingReportResponse:
    """Build a side-effect-free alerting report from degraded-state inputs.

    The function accepts pydantic models or dictionaries. It does not call
    external systems, mutate state, or deliver webhook notifications.
    """

    generated_at = generated_at or datetime.now(timezone.utc)
    service_info = _coerce_service(service, troubleshooting_report)
    events: list[AlertingEvent] = []
    degraded_sources: list[str] = []

    troubleshooting = (
        _to_dict(troubleshooting_report) if troubleshooting_report else None
    )
    if troubleshooting:
        troubleshooting_status = str(troubleshooting.get("status") or "unknown")
        if troubleshooting_status not in {"ok", "unknown"}:
            degraded_sources.append("troubleshooting")
        events.extend(_events_from_troubleshooting(troubleshooting))
    else:
        events.append(
            AlertingEvent(
                id="missing-troubleshooting-report",
                severity="warning",
                source="alerting",
                signal="missing_troubleshooting_report",
                message="Troubleshooting report was not provided; degraded-state coverage is partial.",
                details={"input": "troubleshooting_report"},
                recommended_action="Generate GET /v1/ops/troubleshooting/report or call the alerting HTTP endpoint.",
            )
        )

    if isolation_report is not None:
        isolation_status = str(isolation_report.get("status") or "unknown")
        if isolation_status != "ok":
            degraded_sources.append("profile_isolation")
        events.extend(_events_from_isolation(isolation_report))

    severity = _max_severity(events)
    status = "ok" if not events else "degraded"
    hook_payload = build_alert_hook_payload(
        service=service_info,
        environment=environment,
        status=status,
        severity=severity,
        generated_at=generated_at,
        events=events,
        request_id=request_id,
    )
    recommendations = _recommendations(events=events, isolation_report=isolation_report)

    return AlertingReportResponse(
        schema_version=ALERTING_REPORT_SCHEMA_VERSION,
        status=status,
        severity=severity,
        generated_at=generated_at,
        service=service_info,
        environment=environment,
        request_id=request_id,
        summary={
            "events_total": len(events),
            "critical_events": sum(
                1 for event in events if event.severity == "critical"
            ),
            "warning_events": sum(1 for event in events if event.severity == "warning"),
            "info_events": sum(1 for event in events if event.severity == "info"),
            "degraded_sources": sorted(set(degraded_sources)),
        },
        events=events,
        hooks={
            "webhook_json": AlertingHookPreview(
                configured=False,
                delivery_enabled=False,
                payload=hook_payload,
                note="Payload preview only. SkeinRank does not send webhooks from this endpoint.",
            )
        },
        recommendations=recommendations,
        safety={
            "read_only": True,
            "database_mutation_enabled": False,
            "runtime_mutation_enabled": False,
            "openrouter_calls": False,
            "elasticsearch_calls": False,
            "webhook_delivery_enabled": False,
            "secrets_included": False,
        },
    )


def build_alert_hook_payload(
    *,
    service: ServiceInfo,
    environment: str,
    status: str,
    severity: str,
    generated_at: datetime,
    events: list[AlertingEvent],
    request_id: str | None = None,
) -> dict[str, Any]:
    """Return a sanitized webhook-style payload preview."""

    title = (
        "SkeinRank degraded-state alert"
        if status != "ok"
        else "SkeinRank degraded-state check passed"
    )
    return {
        "schema_version": ALERTING_HOOK_PAYLOAD_SCHEMA_VERSION,
        "title": title,
        "status": status,
        "severity": severity,
        "service": service.model_dump(mode="json"),
        "environment": environment,
        "generated_at": generated_at.isoformat(),
        "request_id": request_id,
        "events_total": len(events),
        "events": [event.model_dump(mode="json") for event in events[:20]],
        "truncated": len(events) > 20,
    }


def build_alerting_plan() -> dict[str, Any]:
    """Return an offline plan for operators and docs/tests."""

    return {
        "schema_version": ALERTING_PLAN_SCHEMA_VERSION,
        "status": "planned",
        "inputs": [
            "GET /v1/ops/troubleshooting/report",
            "GET /v1/governance/isolation-checks",
            "optional saved troubleshooting/isolation JSON files for CLI use",
        ],
        "outputs": [
            "GET /v1/ops/alerts/report",
            "skeinrank.alerting_report.v1",
            "skeinrank.alerting_hook_payload.v1 preview",
        ],
        "alert_sources": [
            "database",
            "schema",
            "elasticsearch",
            "observability",
            "profile_isolation",
        ],
        "safety": {
            "read_only": True,
            "webhook_delivery_enabled": False,
            "openrouter_calls": False,
            "elasticsearch_calls": False,
            "database_mutation_enabled": False,
            "runtime_mutation_enabled": False,
        },
    }


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for offline alerting report previews."""

    parser = argparse.ArgumentParser(
        prog="python -m skeinrank_governance_api.alerting",
        description="Generate read-only SkeinRank degraded-state alert reports.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("plan", help="Print the alerting report plan.")

    report_parser = subparsers.add_parser(
        "report", help="Generate an alerting report from saved JSON inputs."
    )
    report_parser.add_argument("--troubleshooting-report", type=Path)
    report_parser.add_argument("--isolation-report", type=Path)
    report_parser.add_argument("--environment", default="offline")
    report_parser.add_argument("--out", type=Path)
    report_parser.add_argument(
        "--strict",
        action="store_true",
        help="Return exit code 1 when alert status is degraded.",
    )

    show_parser = subparsers.add_parser("show", help="Pretty-print a saved report.")
    show_parser.add_argument("--file", required=True, type=Path)

    args = parser.parse_args(argv)
    if args.command == "plan":
        print(json.dumps(build_alerting_plan(), indent=2, ensure_ascii=False))
        return 0
    if args.command == "show":
        payload = _load_json_file(args.file)
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0
    if args.command == "report":
        troubleshooting_report = (
            _load_json_file(args.troubleshooting_report)
            if args.troubleshooting_report
            else None
        )
        isolation_report = (
            _load_json_file(args.isolation_report) if args.isolation_report else None
        )
        service = _coerce_service(None, troubleshooting_report)
        report = build_alerting_report(
            service=service,
            environment=args.environment,
            troubleshooting_report=troubleshooting_report,
            isolation_report=isolation_report,
        )
        payload = report.model_dump(mode="json")
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 1 if args.strict and report.status != "ok" else 0
    parser.error(f"Unknown command: {args.command}")
    return 2


def _events_from_troubleshooting(report: dict[str, Any]) -> list[AlertingEvent]:
    events: list[AlertingEvent] = []
    for check in report.get("checks") or []:
        status = str(check.get("status") or "unknown")
        name = str(check.get("name") or "unknown")
        if status in _OK_TROUBLESHOOTING_STATUSES:
            continue
        severity = "critical" if name in _CRITICAL_TROUBLESHOOTING_CHECKS else "warning"
        events.append(
            AlertingEvent(
                id=f"troubleshooting-{name}-{status}",
                severity=severity,
                source="troubleshooting",
                signal=name,
                message=str(check.get("message") or f"{name} status is {status}"),
                details={
                    "status": status,
                    "details": check.get("details") or {},
                },
                recommended_action=_recommended_action_for_troubleshooting(
                    name, status
                ),
            )
        )
    return events


def _events_from_isolation(report: dict[str, Any]) -> list[AlertingEvent]:
    events: list[AlertingEvent] = []
    for check in report.get("checks") or []:
        status = str(check.get("status") or "unknown")
        if status == "ok":
            continue
        sampled_issues = check.get("sampled_issues") or []
        severity = "warning"
        for issue in sampled_issues:
            issue_severity = str(issue.get("severity") or "").lower()
            if issue_severity in _CRITICAL_ISSUE_SEVERITIES:
                severity = "critical"
                break
        name = str(check.get("name") or "profile_isolation")
        events.append(
            AlertingEvent(
                id=f"profile-isolation-{name}-{status}",
                severity=severity,
                source="profile_isolation",
                signal=name,
                message=str(check.get("message") or f"{name} status is {status}"),
                details={
                    "status": status,
                    "issues_count": check.get("issues_count", 0),
                    "sampled_issues": sampled_issues[:5],
                },
                recommended_action="Review profile/binding alignment and repair orphaned or cross-profile rows before production pilot runs.",
            )
        )
    return events


def _max_severity(events: list[AlertingEvent]) -> str:
    if any(event.severity == "critical" for event in events):
        return "critical"
    if any(event.severity == "warning" for event in events):
        return "warning"
    return "info"


def _recommendations(
    *, events: list[AlertingEvent], isolation_report: dict[str, Any] | None
) -> list[str]:
    if not events:
        return [
            "No degraded-state alert events were generated.",
            "Keep support bundles and backup/restore drill artifacts available before pilot runs.",
        ]
    recommendations = [
        "Do not enable autonomous apply while degraded-state alerts are present.",
        "Attach the troubleshooting report and support bundle when escalating operator issues.",
    ]
    if any(event.severity == "critical" for event in events):
        recommendations.insert(
            0,
            "Resolve critical database/schema/isolation alerts before continuing the pilot.",
        )
    if isolation_report is not None and isolation_report.get("status") != "ok":
        recommendations.append(
            "Run GET /v1/governance/isolation-checks again after repairing profile/binding state."
        )
    return recommendations


def _recommended_action_for_troubleshooting(name: str, status: str) -> str:
    if name == "database":
        return "Check database URL, credentials, network access, and migration state."
    if name == "schema":
        return "Run migration/schema health checks before continuing."
    if name == "elasticsearch":
        return "Check Elasticsearch/OpenSearch URL, credentials, and index availability, or disable the integration for offline pilots."
    if name == "observability":
        return "Enable structured logs/metrics before production pilot runs."
    return f"Inspect the {name} troubleshooting check; current status is {status}."


def _coerce_service(
    service: ServiceInfo | dict[str, Any] | None,
    troubleshooting_report: Any | None = None,
) -> ServiceInfo:
    if isinstance(service, ServiceInfo):
        return service
    if isinstance(service, dict):
        return ServiceInfo(
            name=str(service.get("name") or "skeinrank-governance-api"),
            version=str(service.get("version") or "unknown"),
        )
    troubleshooting = _to_dict(troubleshooting_report) if troubleshooting_report else {}
    troubleshooting_service = (
        troubleshooting.get("service") if isinstance(troubleshooting, dict) else None
    )
    if isinstance(troubleshooting_service, dict):
        return ServiceInfo(
            name=str(troubleshooting_service.get("name") or "skeinrank-governance-api"),
            version=str(troubleshooting_service.get("version") or "unknown"),
        )
    return ServiceInfo(name="skeinrank-governance-api", version="unknown")


def _to_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return dict(value)


def _load_json_file(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
