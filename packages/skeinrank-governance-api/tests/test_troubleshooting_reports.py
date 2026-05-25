from __future__ import annotations

from fastapi.testclient import TestClient
from skeinrank_governance_api import GovernanceApiConfig, create_app
from skeinrank_governance_api.troubleshooting import generate_troubleshooting_report


def test_troubleshooting_report_endpoint_returns_sanitized_ops_report(tmp_path):
    app = create_app(
        GovernanceApiConfig(
            database_url=f"sqlite:///{tmp_path / 'governance.db'}",
            create_tables_on_startup=True,
            service_version="test",
            access_log_enabled=False,
        )
    )

    response = TestClient(app).get(
        "/v1/ops/troubleshooting/report",
        headers={"X-Request-ID": "trouble-1"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["service"] == {
        "name": "skeinrank-governance-api",
        "version": "test",
    }
    assert payload["request_id"] == "trouble-1"
    assert payload["config"]["database_url"].startswith("sqlite:///")
    assert payload["config"]["metrics_enabled"] is True
    assert payload["config"]["elasticsearch_configured"] is False
    checks = {check["name"]: check for check in payload["checks"]}
    assert checks["database"]["status"] == "ok"
    assert checks["schema"]["status"] == "degraded"
    assert checks["elasticsearch"]["status"] == "not_configured"
    assert checks["observability"]["status"] == "ok"
    assert "agent_runs" in payload["counts"]
    assert "governance_suggestions" in payload["counts"]
    assert any("Alembic" in item for item in payload["recommendations"])


def test_troubleshooting_report_redacts_database_credentials(tmp_path):
    config = GovernanceApiConfig(
        database_url="postgresql+psycopg://user:secret@localhost:5432/skeinrank",
        create_tables_on_startup=False,
        service_version="test",
    )
    # Reuse a real SQLite app engine so the report can be generated without a
    # running Postgres instance. The config URL is only included in sanitized
    # report metadata.
    app = create_app(
        GovernanceApiConfig(
            database_url=f"sqlite:///{tmp_path / 'governance.db'}",
            create_tables_on_startup=True,
            service_version="test",
        )
    )

    report = generate_troubleshooting_report(
        config=config,
        engine=app.state.governance_engine,
        session_factory=app.state.governance_session_factory,
    )

    assert (
        report.config.database_url
        == "postgresql+psycopg://***@localhost:5432/skeinrank"
    )
    database_check = next(check for check in report.checks if check.name == "database")
    assert (
        database_check.details["url"]
        == "postgresql+psycopg://***@localhost:5432/skeinrank"
    )
