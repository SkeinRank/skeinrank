"""FastAPI middleware for request observability."""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from .context import reset_request_id, set_request_id
from .metrics import record_http_exception, record_http_request
from .tracing import start_span

logger = logging.getLogger("skeinrank_governance_api.observability.http")


class RequestObservabilityMiddleware(BaseHTTPMiddleware):
    """Attach request ids and emit structured access logs."""

    def __init__(
        self,
        app,
        *,
        enabled: bool,
        access_log_enabled: bool,
        request_id_header: str,
    ) -> None:
        super().__init__(app)
        self.enabled = enabled
        self.access_log_enabled = access_log_enabled
        self.request_id_header = request_id_header

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if not self.enabled:
            return await call_next(request)

        request_id = _request_id_from_headers(request, self.request_id_header)
        request.state.request_id = request_id
        context_token = set_request_id(request_id)
        started_at = time.perf_counter()
        span_attributes = {
            "http.request.method": request.method,
            "url.path": request.url.path,
            "url.scheme": request.url.scheme,
            "skeinrank.request_id": request_id,
            "client.address": _client_host(request),
        }
        try:
            with start_span("http.request", span_attributes) as span:
                response = await call_next(request)
                if span is not None:
                    span.set_attribute(
                        "http.response.status_code", response.status_code
                    )
        except Exception:
            duration_ms = _duration_ms(started_at)
            record_http_exception(method=request.method, path=request.url.path)
            record_http_request(
                method=request.method,
                path=request.url.path,
                status_code=500,
                duration_seconds=duration_ms / 1000,
            )
            logger.exception(
                "Unhandled request exception",
                extra={
                    "request_id": request_id,
                    "http_method": request.method,
                    "http_path": request.url.path,
                    "http_status_code": 500,
                    "duration_ms": duration_ms,
                    "client_host": _client_host(request),
                },
            )
            raise
        finally:
            reset_request_id(context_token)

        response.headers[self.request_id_header] = request_id
        duration_ms = _duration_ms(started_at)
        record_http_request(
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_seconds=duration_ms / 1000,
        )
        if self.access_log_enabled:
            logger.info(
                "HTTP request completed",
                extra={
                    "request_id": request_id,
                    "http_method": request.method,
                    "http_path": request.url.path,
                    "http_status_code": response.status_code,
                    "duration_ms": duration_ms,
                    "client_host": _client_host(request),
                },
            )
        return response


def _request_id_from_headers(request: Request, header_name: str) -> str:
    raw_value = request.headers.get(header_name)
    value = (raw_value or "").strip()
    return value if value else uuid4().hex


def _duration_ms(started_at: float) -> float:
    return round((time.perf_counter() - started_at) * 1000, 3)


def _client_host(request: Request) -> str | None:
    return request.client.host if request.client else None
