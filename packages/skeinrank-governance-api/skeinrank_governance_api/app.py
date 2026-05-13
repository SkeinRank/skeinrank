"""FastAPI app factory for the SkeinRank governance API."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import GovernanceApiConfig
from .dependencies import configure_database
from .routes.auth import router as auth_router
from .routes.console import router as console_router
from .routes.governance import router as governance_router
from .routes.health import router as health_router
from .routes.search import router as search_router
from .routes.text import router as text_router


def create_app(config: GovernanceApiConfig | None = None) -> FastAPI:
    """Create the governance API application."""

    config = config or GovernanceApiConfig.from_env()
    app = FastAPI(
        title="SkeinRank Governance API",
        description="HTTP control-plane API for SkeinRank terminology governance.",
        version=config.service_version,
    )
    app.state.config = config
    if config.cors_allow_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(config.cors_allow_origins),
            allow_methods=["*"],
            allow_headers=["*"],
        )
    configure_database(app, config)
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(text_router)
    app.include_router(search_router)
    app.include_router(governance_router)
    app.include_router(console_router)
    return app
