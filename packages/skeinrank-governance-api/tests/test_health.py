from __future__ import annotations

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from skeinrank_governance_api import GovernanceApiConfig, create_app
from skeinrank_governance_api.dependencies import get_session
from skeinrank_governance_api.routes.health import _safe_url
from sqlalchemy import text
from sqlalchemy.orm import Session


def test_healthz_returns_database_status(tmp_path):
    app = create_app(
        GovernanceApiConfig(
            database_url=f"sqlite:///{tmp_path / 'governance.db'}",
            create_tables_on_startup=True,
            service_version="test",
        )
    )

    response = TestClient(app).get("/healthz")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["service"] == {
        "name": "skeinrank-governance-api",
        "version": "test",
    }
    assert payload["database"]["ok"] is True
    assert payload["database"]["url"].startswith("sqlite:///")


def test_livez_returns_process_status(tmp_path):
    app = create_app(
        GovernanceApiConfig(
            database_url=f"sqlite:///{tmp_path / 'governance.db'}",
            create_tables_on_startup=True,
            service_version="test",
        )
    )

    response = TestClient(app).get("/livez")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": {"name": "skeinrank-governance-api", "version": "test"},
    }


def test_readyz_reports_database_and_unconfigured_elasticsearch(tmp_path):
    app = create_app(
        GovernanceApiConfig(
            database_url=f"sqlite:///{tmp_path / 'governance.db'}",
            create_tables_on_startup=True,
            service_version="test",
        )
    )

    response = TestClient(app).get("/readyz")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["database"]["ok"] is True
    assert payload["elasticsearch"] == {
        "ok": False,
        "configured": False,
        "url": None,
        "name": None,
        "version": None,
        "error": None,
    }


def test_database_url_redaction_helper_hides_credentials():
    assert (
        _safe_url("postgresql+psycopg://user:secret@localhost:5432/skeinrank")
        == "postgresql+psycopg://***@localhost:5432/skeinrank"
    )


def test_session_dependency_can_execute_sql(tmp_path):
    app: FastAPI = create_app(
        GovernanceApiConfig(
            database_url=f"sqlite:///{tmp_path / 'governance.db'}",
            create_tables_on_startup=True,
            service_version="test",
        )
    )

    @app.get("/session-check")
    def session_check(session: Session = Depends(get_session)) -> dict[str, int]:
        value = session.execute(text("SELECT 1")).scalar_one()
        return {"value": int(value)}

    response = TestClient(app).get("/session-check")

    assert response.status_code == 200
    assert response.json() == {"value": 1}
