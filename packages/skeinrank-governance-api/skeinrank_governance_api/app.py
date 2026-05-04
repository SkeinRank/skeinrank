"""FastAPI app factory for the SkeinRank governance API."""

from __future__ import annotations

from fastapi import FastAPI

from .config import GovernanceApiConfig
from .dependencies import configure_database
from .routes.health import router as health_router


def create_app(config: GovernanceApiConfig | None = None) -> FastAPI:
    """Create the governance API application."""

    config = config or GovernanceApiConfig.from_env()
    app = FastAPI(
        title="SkeinRank Governance API",
        description="HTTP control-plane API for SkeinRank terminology governance.",
        version=config.service_version,
    )
    app.state.config = config
    configure_database(app, config)
    app.include_router(health_router)
    return app
