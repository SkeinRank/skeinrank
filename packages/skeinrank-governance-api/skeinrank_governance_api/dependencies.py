"""FastAPI dependencies for governance database access."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from fastapi import Request
from skeinrank_governance import (
    create_all,
    create_governance_engine,
    create_session_factory,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .config import GovernanceApiConfig


def create_engine_for_config(config: GovernanceApiConfig) -> Engine:
    """Create an engine suitable for the configured governance database URL."""

    kwargs: dict[str, Any] = {}
    if config.database_url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    return create_governance_engine(config.database_url, **kwargs)


def configure_database(app: Any, config: GovernanceApiConfig) -> None:
    """Attach engine and session factory to the FastAPI app state."""

    engine = create_engine_for_config(config)
    if config.create_tables_on_startup:
        create_all(engine)
    app.state.governance_engine = engine
    app.state.governance_session_factory = create_session_factory(engine)


def get_engine(request: Request) -> Engine:
    """Return the configured governance SQLAlchemy engine."""

    return request.app.state.governance_engine


def get_session(request: Request) -> Iterator[Session]:
    """Yield a SQLAlchemy session bound to the governance database."""

    session_factory: sessionmaker[Session] = (
        request.app.state.governance_session_factory
    )
    with session_factory() as session:
        yield session
