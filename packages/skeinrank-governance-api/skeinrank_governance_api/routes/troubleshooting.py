"""Operational troubleshooting report endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request

from ..auth import AuthContext, require_roles, require_scopes
from ..observability.context import get_request_id
from ..observability.logging import structured_log
from ..schemas import TroubleshootingReportResponse
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
