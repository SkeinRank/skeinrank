"""FastAPI control-plane API for SkeinRank terminology governance."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - import-time typing only
    from .app import create_app as create_app
    from .config import GovernanceApiConfig as GovernanceApiConfig

__all__ = ["GovernanceApiConfig", "create_app"]


def __getattr__(name: str) -> Any:
    """Lazily expose public API objects without importing the app at package load.

    Keeping this package initializer light prevents ``python -m`` entrypoints such
    as ``skeinrank_governance_api.migrations`` from importing route modules before
    the target module is executed.
    """

    if name == "GovernanceApiConfig":
        from .config import GovernanceApiConfig

        return GovernanceApiConfig
    if name == "create_app":
        from .app import create_app

        return create_app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
