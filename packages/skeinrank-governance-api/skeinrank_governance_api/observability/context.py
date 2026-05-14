"""Request-scoped observability context helpers."""

from __future__ import annotations

from contextvars import ContextVar, Token

_REQUEST_ID: ContextVar[str | None] = ContextVar("skeinrank_request_id", default=None)


def get_request_id() -> str | None:
    """Return the current request id, if one is bound to this context."""

    return _REQUEST_ID.get()


def set_request_id(request_id: str | None) -> Token[str | None]:
    """Bind a request id to the current context and return the reset token."""

    return _REQUEST_ID.set(request_id)


def reset_request_id(token: Token[str | None]) -> None:
    """Reset the request id context using a token returned by ``set_request_id``."""

    _REQUEST_ID.reset(token)
