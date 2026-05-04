"""Database helpers for SkeinRank terminology governance."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy import MetaData, create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

NAMING_CONVENTION: Mapping[str, str] = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Declarative base shared by governance models and Alembic."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def create_governance_engine(database_url: str, **kwargs: Any) -> Engine:
    """Create a SQLAlchemy engine for governance storage.

    Parameters are intentionally thin wrappers around ``sqlalchemy.create_engine``
    so tests can use SQLite while production deployments can use PostgreSQL.
    """

    return create_engine(database_url, future=True, **kwargs)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Create a session factory with stable defaults for CLI/admin tools."""

    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


def create_all(engine: Engine) -> None:
    """Create all governance tables for lightweight local tests or demos.

    Production deployments should prefer Alembic migrations.
    """

    Base.metadata.create_all(engine)
