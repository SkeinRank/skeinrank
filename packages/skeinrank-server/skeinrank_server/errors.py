from __future__ import annotations


class ServiceError(RuntimeError):
    """Base server error."""


class BadRequest(ServiceError):
    pass


class UpstreamError(ServiceError):
    pass


class CoreUnavailable(ServiceError):
    pass
