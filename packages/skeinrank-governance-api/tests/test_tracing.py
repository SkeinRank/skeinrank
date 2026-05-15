from __future__ import annotations

from skeinrank_governance_api.config import GovernanceApiConfig
from skeinrank_governance_api.observability.tracing import (
    configure_tracing,
    start_span,
    trace_query_text,
    tracing_status,
)


def test_tracing_is_disabled_by_default():
    config = GovernanceApiConfig(service_version="test")

    status = configure_tracing(config)

    assert status.enabled is False
    assert status.available is False
    assert status.reason == "tracing disabled by configuration"


def test_start_span_is_noop_when_tracing_is_unavailable():
    config = GovernanceApiConfig(service_version="test", tracing_enabled=False)
    configure_tracing(config)

    with start_span("unit.test", {"skeinrank.test": "value"}) as span:
        assert span is None


def test_query_text_is_redacted_by_default():
    config = GovernanceApiConfig(service_version="test", otel_capture_query_text=False)

    assert trace_query_text(config, "k8s pg timeout") == {
        "skeinrank.query.redacted": "true"
    }


def test_query_text_can_be_captured_when_explicitly_enabled():
    config = GovernanceApiConfig(service_version="test", otel_capture_query_text=True)

    assert trace_query_text(config, "k8s pg timeout") == {
        "skeinrank.query.text": "k8s pg timeout"
    }


def test_tracing_status_reflects_runtime_state():
    config = GovernanceApiConfig(
        service_version="test",
        tracing_enabled=True,
        otel_traces_exporter="none",
    )

    configure_tracing(config)
    status = tracing_status(config)

    assert status.enabled is True
    assert status.available is False
    assert status.exporter == "none"
