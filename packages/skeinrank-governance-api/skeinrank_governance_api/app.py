"""FastAPI app factory for the SkeinRank governance API."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import GovernanceApiConfig
from .dependencies import configure_database
from .observability import (
    RequestObservabilityMiddleware,
    configure_logging,
    set_build_info,
)
from .routes.auth import router as auth_router
from .routes.console import router as console_router
from .routes.governance import router as governance_router
from .routes.health import router as health_router
from .routes.metrics import metrics_response
from .routes.metrics import router as metrics_router
from .routes.search import router as search_router
from .routes.text import router as text_router


def create_app(config: GovernanceApiConfig | None = None) -> FastAPI:
    """Create the governance API application."""

    config = config or GovernanceApiConfig.from_env()
    config.validate_production_security()
    configure_logging(config)
    set_build_info(service=config.service_name, version=config.service_version)
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
            expose_headers=[config.request_id_header],
        )
    app.add_middleware(
        RequestObservabilityMiddleware,
        enabled=config.observability_enabled,
        access_log_enabled=config.access_log_enabled,
        request_id_header=config.request_id_header,
    )
    configure_database(app, config)
    app.include_router(health_router)
    if config.metrics_enabled:
        app.include_router(metrics_router)
        if config.metrics_path != "/metrics":
            app.add_api_route(
                config.metrics_path,
                metrics_response,
                methods=["GET"],
                include_in_schema=False,
            )
    app.include_router(auth_router)
    app.include_router(text_router)
    app.include_router(search_router)
    app.include_router(governance_router)
    app.include_router(console_router)
    return app
