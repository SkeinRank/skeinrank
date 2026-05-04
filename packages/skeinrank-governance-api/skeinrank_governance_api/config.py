"""Configuration for the SkeinRank governance API."""

from __future__ import annotations

import os
from dataclasses import dataclass
from importlib import metadata

DATABASE_URL_ENV = "SKEINRANK_GOVERNANCE_DATABASE_URL"
API_DATABASE_URL_ENV = "SKEINRANK_GOVERNANCE_API_DATABASE_URL"
CREATE_TABLES_ENV = "SKEINRANK_GOVERNANCE_API_CREATE_TABLES"
DEFAULT_DATABASE_URL = "sqlite:///skeinrank_governance.db"
SERVICE_NAME = "skeinrank-governance-api"


def _bool_from_env(value: str | None, *, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class GovernanceApiConfig:
    """Runtime configuration for the governance API package."""

    database_url: str = DEFAULT_DATABASE_URL
    create_tables_on_startup: bool = False
    service_name: str = SERVICE_NAME
    service_version: str = "0.1.0"

    @classmethod
    def from_env(cls) -> "GovernanceApiConfig":
        """Build API configuration from environment variables."""

        database_url = (
            os.getenv(API_DATABASE_URL_ENV)
            or os.getenv(DATABASE_URL_ENV)
            or DEFAULT_DATABASE_URL
        )
        return cls(
            database_url=database_url,
            create_tables_on_startup=_bool_from_env(os.getenv(CREATE_TABLES_ENV)),
            service_version=_package_version(),
        )


def _package_version() -> str:
    try:
        return metadata.version(SERVICE_NAME)
    except metadata.PackageNotFoundError:
        return "0.1.0"
