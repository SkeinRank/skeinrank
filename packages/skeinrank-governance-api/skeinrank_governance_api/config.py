"""Configuration for the SkeinRank governance API."""

from __future__ import annotations

import os
from dataclasses import dataclass
from importlib import metadata

DATABASE_URL_ENV = "SKEINRANK_GOVERNANCE_DATABASE_URL"
API_DATABASE_URL_ENV = "SKEINRANK_GOVERNANCE_API_DATABASE_URL"
CREATE_TABLES_ENV = "SKEINRANK_GOVERNANCE_API_CREATE_TABLES"
CORS_ORIGINS_ENV = "SKEINRANK_GOVERNANCE_API_CORS_ORIGINS"
AUTH_ENABLED_ENV = "SKEINRANK_GOVERNANCE_API_AUTH_ENABLED"
BOOTSTRAP_ADMIN_ENV = "SKEINRANK_GOVERNANCE_API_BOOTSTRAP_ADMIN"
ADMIN_USERNAME_ENV = "SKEINRANK_GOVERNANCE_API_ADMIN_USERNAME"
ADMIN_PASSWORD_ENV = "SKEINRANK_GOVERNANCE_API_ADMIN_PASSWORD"
ADMIN_DISPLAY_NAME_ENV = "SKEINRANK_GOVERNANCE_API_ADMIN_DISPLAY_NAME"
TOKEN_TTL_HOURS_ENV = "SKEINRANK_GOVERNANCE_API_TOKEN_TTL_HOURS"
DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_TOKEN_TTL_HOURS = 24
DEFAULT_DATABASE_URL = "sqlite:///skeinrank_governance.db"
DEFAULT_CORS_ORIGINS = ("http://127.0.0.1:5173", "http://localhost:5173")
SERVICE_NAME = "skeinrank-governance-api"


def _bool_from_env(value: str | None, *, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int_from_env(value: str | None, *, default: int) -> int:
    if value is None:
        return default
    try:
        parsed = int(value.strip())
    except ValueError:
        return default
    return parsed if parsed > 0 else default


def _tuple_from_csv(value: str | None, *, default: tuple[str, ...]) -> tuple[str, ...]:
    if value is None:
        return default
    origins = tuple(origin.strip() for origin in value.split(",") if origin.strip())
    return origins


@dataclass(frozen=True)
class GovernanceApiConfig:
    """Runtime configuration for the governance API package."""

    database_url: str = DEFAULT_DATABASE_URL
    create_tables_on_startup: bool = False
    cors_allow_origins: tuple[str, ...] = DEFAULT_CORS_ORIGINS
    auth_enabled: bool = False
    bootstrap_admin: bool = False
    admin_username: str = DEFAULT_ADMIN_USERNAME
    admin_password: str | None = None
    admin_display_name: str | None = None
    token_ttl_hours: int = DEFAULT_TOKEN_TTL_HOURS
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
            cors_allow_origins=_tuple_from_csv(
                os.getenv(CORS_ORIGINS_ENV),
                default=DEFAULT_CORS_ORIGINS,
            ),
            auth_enabled=_bool_from_env(os.getenv(AUTH_ENABLED_ENV)),
            bootstrap_admin=_bool_from_env(os.getenv(BOOTSTRAP_ADMIN_ENV)),
            admin_username=os.getenv(ADMIN_USERNAME_ENV, DEFAULT_ADMIN_USERNAME),
            admin_password=os.getenv(ADMIN_PASSWORD_ENV),
            admin_display_name=os.getenv(ADMIN_DISPLAY_NAME_ENV),
            token_ttl_hours=_int_from_env(
                os.getenv(TOKEN_TTL_HOURS_ENV),
                default=DEFAULT_TOKEN_TTL_HOURS,
            ),
            service_version=_package_version(),
        )


def _package_version() -> str:
    try:
        return metadata.version(SERVICE_NAME)
    except metadata.PackageNotFoundError:
        return "0.1.0"
