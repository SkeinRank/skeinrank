"""Operational troubleshooting report endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request

from ..alerting import build_alerting_report
from ..auth import AuthContext, require_roles, require_scopes
from ..observability.context import get_request_id
from ..observability.logging import structured_log
from ..profile_isolation import build_profile_isolation_report
from ..schemas import AlertingReportResponse, TroubleshootingReportResponse
from ..troubleshooting import generate_troubleshooting_report

router = APIRouter(prefix="/v1/ops", tags=["ops"])
logger = logging.getLogger("skeinrank_governance_api.ops.troubleshooting")


@router.get(
    "/troubleshooting/report",
    response_model=TroubleshootingReportResponse,
)
def get_troubleshooting_report(
    request: Request,
    current_user: AuthContext = Depends(require_roles("admin")),
    _scope: AuthContext = Depends(require_scopes("ops:reports:read")),
) -> TroubleshootingReportResponse:
    """Return a read-only diagnostic report for operators."""

    report = generate_troubleshooting_report(
        config=request.app.state.config,
        engine=request.app.state.governance_engine,
        session_factory=request.app.state.governance_session_factory,
        request_id=get_request_id(),
    )
    structured_log(
        logger,
        logging.INFO,
        "Troubleshooting report generated",
        event="ops.troubleshooting.report.generated",
        outcome="succeeded" if report.status == "ok" else "degraded",
        request_id=get_request_id(),
        report_status=report.status,
        requested_by=current_user.username,
        auth_type=current_user.auth_type,
    )
    return report


@router.get(
    "/alerts/report",
    response_model=AlertingReportResponse,
)
def get_alerting_report(
    request: Request,
    current_user: AuthContext = Depends(require_roles("admin")),
    _scope: AuthContext = Depends(require_scopes("ops:reports:read")),
) -> AlertingReportResponse:
    """Return a read-only degraded-state alert report for operators."""

    troubleshooting_report = generate_troubleshooting_report(
        config=request.app.state.config,
        engine=request.app.state.governance_engine,
        session_factory=request.app.state.governance_session_factory,
        request_id=get_request_id(),
    )
    with request.app.state.governance_session_factory() as session:
        isolation_report = build_profile_isolation_report(session)

    report = build_alerting_report(
        service=troubleshooting_report.service,
        environment=troubleshooting_report.environment,
        request_id=get_request_id(),
        troubleshooting_report=troubleshooting_report,
        isolation_report=isolation_report,
    )
    structured_log(
        logger,
        logging.INFO,
        "Alerting report generated",
        event="ops.alerting.report.generated",
        outcome="succeeded" if report.status == "ok" else "degraded",
        request_id=get_request_id(),
        report_status=report.status,
        severity=report.severity,
        events_total=report.summary.get("events_total"),
        requested_by=current_user.username,
        auth_type=current_user.auth_type,
    )
    return report
