"""Optional OpenTelemetry tracing helpers for the governance API and worker.

The integration is intentionally dependency-optional. If OpenTelemetry packages are
not installed, all helpers degrade to no-op context managers so the core API keeps
working in minimal environments.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from ..config import GovernanceApiConfig
from .context import get_request_id

logger = logging.getLogger("skeinrank_governance_api.observability.tracing")

_TRACE_PROVIDER_CONFIGURED = False
_TRACE_AVAILABLE = False
_TRACE_STATUS = "disabled"
_TRACE_REASON: str | None = None
_TRACER: Any = None


@dataclass(frozen=True)
class TracingStatus:
    """Runtime status for the optional tracing integration."""

    enabled: bool
    available: bool
    exporter: str
    service_name: str
    reason: str | None = None


def configure_tracing(config: GovernanceApiConfig) -> TracingStatus:
    """Configure OpenTelemetry tracing if it is enabled and available.

    The function never raises when OpenTelemetry packages are missing. This keeps
    the default development and CI flows dependency-light while allowing
    deployments to enable tracing by installing the standard OTEL packages.
    """

    global \
        _TRACE_AVAILABLE, \
        _TRACE_PROVIDER_CONFIGURED, \
        _TRACE_REASON, \
        _TRACE_STATUS, \
        _TRACER

    if not config.observability_enabled or not config.tracing_enabled:
        _TRACE_AVAILABLE = False
        _TRACE_REASON = "tracing disabled by configuration"
        _TRACE_STATUS = "disabled"
        _TRACER = None
        return TracingStatus(
            enabled=False,
            available=False,
            exporter=config.otel_traces_exporter,
            service_name=config.otel_service_name,
            reason=_TRACE_REASON,
        )

    if config.otel_traces_exporter == "none":
        _TRACE_AVAILABLE = False
        _TRACE_REASON = "tracing exporter is set to none"
        _TRACE_STATUS = "disabled"
        _TRACER = None
        return TracingStatus(
            enabled=True,
            available=False,
            exporter=config.otel_traces_exporter,
            service_name=config.otel_service_name,
            reason=_TRACE_REASON,
        )

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import (
            BatchSpanProcessor,
            ConsoleSpanExporter,
        )
        from opentelemetry.sdk.trace.sampling import TraceIdRatioBased
    except ImportError as exc:  # pragma: no cover - depends on optional packages
        _TRACE_AVAILABLE = False
        _TRACE_REASON = f"OpenTelemetry SDK is not installed: {exc}"
        _TRACE_STATUS = "unavailable"
        _TRACER = None
        logger.warning(
            "OpenTelemetry tracing requested but dependencies are not installed",
            extra={"otel_error": str(exc)},
        )
        return TracingStatus(
            enabled=True,
            available=False,
            exporter=config.otel_traces_exporter,
            service_name=config.otel_service_name,
            reason=_TRACE_REASON,
        )

    try:
        if not _TRACE_PROVIDER_CONFIGURED:
            resource = Resource.create(
                {
                    "service.name": config.otel_service_name,
                    "service.version": config.service_version,
                    "deployment.environment": config.deployment_environment,
                }
            )
            provider = TracerProvider(
                resource=resource,
                sampler=TraceIdRatioBased(config.otel_sampling_ratio),
            )
            exporter = _build_exporter(config, ConsoleSpanExporter=ConsoleSpanExporter)
            if exporter is not None:
                provider.add_span_processor(BatchSpanProcessor(exporter))
            trace.set_tracer_provider(provider)
            _TRACE_PROVIDER_CONFIGURED = True
        _TRACER = trace.get_tracer(config.otel_service_name, config.service_version)
        _TRACE_AVAILABLE = True
        _TRACE_REASON = None
        _TRACE_STATUS = "ready"
        return TracingStatus(
            enabled=True,
            available=True,
            exporter=config.otel_traces_exporter,
            service_name=config.otel_service_name,
        )
    except Exception as exc:  # pragma: no cover - defensive runtime guard
        _TRACE_AVAILABLE = False
        _TRACE_REASON = str(exc)
        _TRACE_STATUS = "unavailable"
        _TRACER = None
        logger.warning(
            "OpenTelemetry tracing could not be configured",
            extra={"otel_error": str(exc)},
        )
        return TracingStatus(
            enabled=True,
            available=False,
            exporter=config.otel_traces_exporter,
            service_name=config.otel_service_name,
            reason=_TRACE_REASON,
        )


def tracing_status(config: GovernanceApiConfig) -> TracingStatus:
    """Return the current tracing runtime status."""

    return TracingStatus(
        enabled=config.tracing_enabled,
        available=_TRACE_AVAILABLE,
        exporter=config.otel_traces_exporter,
        service_name=config.otel_service_name,
        reason=_TRACE_REASON,
    )


@contextmanager
def start_span(name: str, attributes: Mapping[str, Any] | None = None) -> Iterator[Any]:
    """Start an OpenTelemetry span or a no-op span when tracing is unavailable."""

    if not _TRACE_AVAILABLE or _TRACER is None:
        yield None
        return

    safe_attributes = _span_attributes(attributes)
    request_id = get_request_id()
    if request_id:
        safe_attributes.setdefault("skeinrank.request_id", request_id)
    with _TRACER.start_as_current_span(name) as span:
        for key, value in safe_attributes.items():
            span.set_attribute(key, value)
        try:
            yield span
        except Exception as exc:
            record_exception(exc)
            raise


def add_span_attributes(attributes: Mapping[str, Any] | None) -> None:
    """Attach attributes to the current span when tracing is active."""

    if not _TRACE_AVAILABLE or not attributes:
        return
    try:
        from opentelemetry import trace
    except ImportError:  # pragma: no cover - optional dependency
        return
    span = trace.get_current_span()
    for key, value in _span_attributes(attributes).items():
        span.set_attribute(key, value)


def record_exception(exc: BaseException) -> None:
    """Record an exception on the active span when tracing is active."""

    if not _TRACE_AVAILABLE:
        return
    try:
        from opentelemetry import trace
        from opentelemetry.trace import Status, StatusCode
    except ImportError:  # pragma: no cover - optional dependency
        return
    span = trace.get_current_span()
    span.record_exception(exc)
    span.set_status(Status(StatusCode.ERROR, str(exc)))


def trace_query_text(config: GovernanceApiConfig, query: str) -> dict[str, str]:
    """Return safe query attributes according to privacy settings."""

    if not config.otel_capture_query_text:
        return {"skeinrank.query.redacted": "true"}
    return {"skeinrank.query.text": query}


def _build_exporter(config: GovernanceApiConfig, *, ConsoleSpanExporter: Any) -> Any:
    if config.otel_traces_exporter == "console":
        return ConsoleSpanExporter()
    if config.otel_traces_exporter == "otlp":
        endpoint = config.otel_exporter_otlp_endpoint
        if not endpoint:
            raise ValueError("OTLP exporter requires an OTLP endpoint")
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                OTLPSpanExporter,
            )

            return OTLPSpanExporter(endpoint=endpoint)
        except ImportError:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import (  # type: ignore[no-redef]
                OTLPSpanExporter,
            )

            return OTLPSpanExporter(endpoint=endpoint)
    return None


def _span_attributes(attributes: Mapping[str, Any] | None) -> dict[str, Any]:
    if not attributes:
        return {}
    return {
        key: _attribute_value(value)
        for key, value in attributes.items()
        if value is not None and _attribute_value(value) is not None
    }


def _attribute_value(value: Any) -> Any:
    if isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, (list, tuple)):
        normalized = [_attribute_value(item) for item in value]
        return [item for item in normalized if item is not None]
    return str(value)
