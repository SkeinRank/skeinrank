from __future__ import annotations

import json
import logging

from fastapi import FastAPI
from fastapi.testclient import TestClient
from skeinrank_governance_api import GovernanceApiConfig, create_app
from skeinrank_governance_api.observability import JsonLogFormatter, get_request_id


def test_request_id_header_is_preserved(tmp_path):
    app = create_app(
        GovernanceApiConfig(
            database_url=f"sqlite:///{tmp_path / 'governance.db'}",
            create_tables_on_startup=True,
            service_version="test",
            access_log_enabled=False,
        )
    )

    response = TestClient(app).get("/livez", headers={"X-Request-ID": "req-123"})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "req-123"


def test_request_id_header_is_generated(tmp_path):
    app = create_app(
        GovernanceApiConfig(
            database_url=f"sqlite:///{tmp_path / 'governance.db'}",
            create_tables_on_startup=True,
            service_version="test",
            access_log_enabled=False,
        )
    )

    response = TestClient(app).get("/livez")

    assert response.status_code == 200
    assert response.headers["X-Request-ID"]


def test_request_id_context_is_available_to_handlers(tmp_path):
    app: FastAPI = create_app(
        GovernanceApiConfig(
            database_url=f"sqlite:///{tmp_path / 'governance.db'}",
            create_tables_on_startup=True,
            service_version="test",
            access_log_enabled=False,
        )
    )

    @app.get("/request-id-check")
    def request_id_check() -> dict[str, str | None]:
        return {"request_id": get_request_id()}

    response = TestClient(app).get(
        "/request-id-check", headers={"X-Request-ID": "ctx-456"}
    )

    assert response.status_code == 200
    assert response.json() == {"request_id": "ctx-456"}


def test_observability_can_be_disabled(tmp_path):
    app = create_app(
        GovernanceApiConfig(
            database_url=f"sqlite:///{tmp_path / 'governance.db'}",
            create_tables_on_startup=True,
            service_version="test",
            observability_enabled=False,
        )
    )

    response = TestClient(app).get("/livez")

    assert response.status_code == 200
    assert "X-Request-ID" not in response.headers


def test_json_log_formatter_includes_service_and_extra_fields():
    formatter = JsonLogFormatter(
        service_name="skeinrank-governance-api", service_version="test"
    )
    record = logging.LogRecord(
        name="skeinrank.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello",
        args=(),
        exc_info=None,
    )
    record.request_id = "req-json"
    record.binding_id = 7

    payload = json.loads(formatter.format(record))

    assert payload["message"] == "hello"
    assert payload["request_id"] == "req-json"
    assert payload["binding_id"] == 7
    assert payload["service"] == {
        "name": "skeinrank-governance-api",
        "version": "test",
    }


def test_metrics_endpoint_exports_prometheus_text(tmp_path):
    from skeinrank_governance_api.observability.metrics import registry

    registry.reset()
    app = create_app(
        GovernanceApiConfig(
            database_url=f"sqlite:///{tmp_path / 'governance.db'}",
            create_tables_on_startup=True,
            service_version="test",
            access_log_enabled=False,
        )
    )
    client = TestClient(app)

    livez_response = client.get("/livez", headers={"X-Request-ID": "metrics-1"})
    metrics_response = client.get("/metrics")

    assert livez_response.status_code == 200
    assert metrics_response.status_code == 200
    assert metrics_response.headers["content-type"].startswith("text/plain")
    body = metrics_response.text
    assert "# HELP skeinrank_http_requests_total" in body
    assert (
        'skeinrank_build_info{service="skeinrank-governance-api",version="test"} 1'
        in body
    )
    assert (
        'skeinrank_http_requests_total{method="GET",path="/livez",status_code="200"} 1'
        in body
    )


def test_metrics_endpoint_can_be_disabled(tmp_path):
    app = create_app(
        GovernanceApiConfig(
            database_url=f"sqlite:///{tmp_path / 'governance.db'}",
            create_tables_on_startup=True,
            service_version="test",
            metrics_enabled=False,
        )
    )

    response = TestClient(app).get("/metrics")

    assert response.status_code == 404


def test_custom_metrics_path_can_be_configured(tmp_path):
    app = create_app(
        GovernanceApiConfig(
            database_url=f"sqlite:///{tmp_path / 'governance.db'}",
            create_tables_on_startup=True,
            service_version="test",
            metrics_path="/internal/metrics",
        )
    )

    response = TestClient(app).get("/internal/metrics")

    assert response.status_code == 200
    assert "skeinrank_build_info" in response.text
