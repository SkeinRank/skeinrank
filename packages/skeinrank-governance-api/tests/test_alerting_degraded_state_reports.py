from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient
from skeinrank_governance_api import GovernanceApiConfig, create_app
from skeinrank_governance_api.alerting import (
    ALERTING_HOOK_PAYLOAD_SCHEMA_VERSION,
    ALERTING_REPORT_SCHEMA_VERSION,
    build_alerting_report,
)
from skeinrank_governance_api.alerting import main as alerting_main

REPO_ROOT = Path(__file__).resolve().parents[3]


def _read(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def _clean_troubleshooting_report() -> dict:
    return {
        "status": "ok",
        "generated_at": "2026-01-01T00:00:00+00:00",
        "service": {"name": "skeinrank-governance-api", "version": "test"},
        "environment": "test",
        "checks": [
            {"name": "database", "status": "ok", "message": "database ok"},
            {"name": "schema", "status": "ok", "message": "schema ok"},
            {
                "name": "elasticsearch",
                "status": "not_configured",
                "message": "Elasticsearch not configured",
            },
            {"name": "observability", "status": "ok", "message": "logs ok"},
        ],
        "counts": {},
        "recommendations": [],
    }


def _clean_isolation_report() -> dict:
    return {
        "schema_version": "skeinrank.profile_isolation.v1",
        "status": "ok",
        "summary": {"issues_total": 0},
        "checks": [],
        "safety": {"read_only": True},
    }


def test_alerting_report_is_ok_for_clean_inputs() -> None:
    report = build_alerting_report(
        service={"name": "skeinrank-governance-api", "version": "test"},
        environment="test",
        troubleshooting_report=_clean_troubleshooting_report(),
        isolation_report=_clean_isolation_report(),
        generated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )

    assert report.schema_version == ALERTING_REPORT_SCHEMA_VERSION
    assert report.status == "ok"
    assert report.severity == "info"
    assert report.summary["events_total"] == 0
    assert report.events == []
    assert report.hooks["webhook_json"].delivery_enabled is False
    assert (
        report.hooks["webhook_json"].payload["schema_version"]
        == ALERTING_HOOK_PAYLOAD_SCHEMA_VERSION
    )
    assert report.safety["webhook_delivery_enabled"] is False


def test_alerting_report_escalates_database_and_isolation_degraded_state() -> None:
    troubleshooting = _clean_troubleshooting_report()
    troubleshooting["status"] = "degraded"
    troubleshooting["checks"][0] = {
        "name": "database",
        "status": "degraded",
        "message": "database connection failed",
        "details": {"url": "sqlite:///***"},
    }
    isolation = {
        "schema_version": "skeinrank.profile_isolation.v1",
        "status": "degraded",
        "summary": {"issues_total": 1},
        "checks": [
            {
                "name": "binding_profile_alignment",
                "status": "failed",
                "message": "Some bindings reference missing profiles.",
                "issues_count": 1,
                "sampled_issues": [
                    {
                        "entity": "elasticsearch_binding",
                        "entity_id": "1",
                        "severity": "high",
                        "message": "Binding references a missing profile.",
                    }
                ],
            }
        ],
    }

    report = build_alerting_report(
        environment="pilot",
        troubleshooting_report=troubleshooting,
        isolation_report=isolation,
        generated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )

    assert report.status == "degraded"
    assert report.severity == "critical"
    assert report.summary["critical_events"] == 2
    event_ids = {event.id for event in report.events}
    assert "troubleshooting-database-degraded" in event_ids
    assert "profile-isolation-binding_profile_alignment-failed" in event_ids
    payload = report.hooks["webhook_json"].payload
    assert payload["status"] == "degraded"
    assert payload["severity"] == "critical"
    assert payload["events_total"] == 2


def test_alerting_endpoint_returns_read_only_degraded_state_report(tmp_path) -> None:
    app = create_app(
        GovernanceApiConfig(
            database_url=f"sqlite:///{tmp_path / 'governance.db'}",
            create_tables_on_startup=True,
            service_version="test",
        )
    )
    client = TestClient(app)

    response = client.get("/v1/ops/alerts/report")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["schema_version"] == ALERTING_REPORT_SCHEMA_VERSION
    assert payload["service"]["name"] == "skeinrank-governance-api"
    assert payload["hooks"]["webhook_json"]["delivery_enabled"] is False
    assert payload["safety"] == {
        "read_only": True,
        "database_mutation_enabled": False,
        "runtime_mutation_enabled": False,
        "openrouter_calls": False,
        "elasticsearch_calls": False,
        "webhook_delivery_enabled": False,
        "secrets_included": False,
    }


def test_alerting_cli_plan_report_and_show(tmp_path: Path, capsys) -> None:
    troubleshooting_path = tmp_path / "troubleshooting.json"
    isolation_path = tmp_path / "isolation.json"
    out_path = tmp_path / "alerting-report.json"
    troubleshooting_path.write_text(
        json.dumps(_clean_troubleshooting_report()), encoding="utf-8"
    )
    isolation_path.write_text(json.dumps(_clean_isolation_report()), encoding="utf-8")

    assert alerting_main(["plan"]) == 0
    assert '"schema_version": "skeinrank.alerting_plan.v1"' in capsys.readouterr().out

    assert (
        alerting_main(
            [
                "report",
                "--troubleshooting-report",
                str(troubleshooting_path),
                "--isolation-report",
                str(isolation_path),
                "--environment",
                "test",
                "--out",
                str(out_path),
            ]
        )
        == 0
    )
    report_stdout = capsys.readouterr().out
    assert '"schema_version": "skeinrank.alerting_report.v1"' in report_stdout
    assert out_path.exists()

    assert alerting_main(["show", "--file", str(out_path)]) == 0
    assert '"status": "ok"' in capsys.readouterr().out


def test_alerting_docs_reference_real_endpoint_cli_and_targets() -> None:
    guide = _read("docs/deployment/alerting-hooks-degraded-state-reports.md")
    api_docs = _read("docs/api/governance-api.md")
    makefile = _read("Makefile")
    pyproject = _read("packages/skeinrank-governance-api/pyproject.toml")
    docs_readme = _read("docs/README.md")
    package_readme = _read("packages/skeinrank-governance-api/README.md")

    assert "GET /v1/ops/alerts/report" in guide
    assert "GET /v1/ops/alerts/report" in api_docs
    assert "skeinrank-governance-alerting" in pyproject
    assert "skeinrank_governance_api.alerting" in guide
    assert "deployment/alerting-hooks-degraded-state-reports.md" in docs_readme
    assert "alerting report" in package_readme.lower()
    for target in [
        "alerts-report-plan",
        "alerts-report-generate",
        "alerts-report-show",
        "alerts-report-clean",
    ]:
        assert f"{target}:" in makefile
        assert f"make {target}" in guide or target == "alerts-report-clean"
