"""Configuration for the SkeinRank governance API."""

from __future__ import annotations

import os
from dataclasses import dataclass
from importlib import metadata

DATABASE_URL_ENV = "SKEINRANK_GOVERNANCE_DATABASE_URL"
API_DATABASE_URL_ENV = "SKEINRANK_GOVERNANCE_API_DATABASE_URL"
CREATE_TABLES_ENV = "SKEINRANK_GOVERNANCE_API_CREATE_TABLES"
DEPLOYMENT_ENV_ENV = "SKEINRANK_GOVERNANCE_API_ENV"
GLOBAL_DEPLOYMENT_ENV_ENV = "SKEINRANK_ENV"
PRODUCTION_SECURITY_ENABLED_ENV = "SKEINRANK_GOVERNANCE_API_PRODUCTION_SECURITY_ENABLED"
CORS_ORIGINS_ENV = "SKEINRANK_GOVERNANCE_API_CORS_ORIGINS"
AUTH_ENABLED_ENV = "SKEINRANK_GOVERNANCE_API_AUTH_ENABLED"
BOOTSTRAP_ADMIN_ENV = "SKEINRANK_GOVERNANCE_API_BOOTSTRAP_ADMIN"
ADMIN_USERNAME_ENV = "SKEINRANK_GOVERNANCE_API_ADMIN_USERNAME"
ADMIN_PASSWORD_ENV = "SKEINRANK_GOVERNANCE_API_ADMIN_PASSWORD"
ADMIN_DISPLAY_NAME_ENV = "SKEINRANK_GOVERNANCE_API_ADMIN_DISPLAY_NAME"
TOKEN_TTL_HOURS_ENV = "SKEINRANK_GOVERNANCE_API_TOKEN_TTL_HOURS"
API_ELASTICSEARCH_URL_ENV = "SKEINRANK_GOVERNANCE_API_ELASTICSEARCH_URL"
ELASTICSEARCH_URL_ENV = "SKEINRANK_ELASTICSEARCH_URL"
API_ELASTICSEARCH_USERNAME_ENV = "SKEINRANK_GOVERNANCE_API_ELASTICSEARCH_USERNAME"
ELASTICSEARCH_USERNAME_ENV = "SKEINRANK_ELASTICSEARCH_USERNAME"
API_ELASTICSEARCH_PASSWORD_ENV = "SKEINRANK_GOVERNANCE_API_ELASTICSEARCH_PASSWORD"
ELASTICSEARCH_PASSWORD_ENV = "SKEINRANK_ELASTICSEARCH_PASSWORD"
API_ELASTICSEARCH_API_KEY_ENV = "SKEINRANK_GOVERNANCE_API_ELASTICSEARCH_API_KEY"
ELASTICSEARCH_API_KEY_ENV = "SKEINRANK_ELASTICSEARCH_API_KEY"
API_ELASTICSEARCH_TIMEOUT_SECONDS_ENV = (
    "SKEINRANK_GOVERNANCE_API_ELASTICSEARCH_TIMEOUT_SECONDS"
)
ELASTICSEARCH_TIMEOUT_SECONDS_ENV = "SKEINRANK_ELASTICSEARCH_TIMEOUT_SECONDS"
DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_DEPLOYMENT_ENV = "development"
DEFAULT_TOKEN_TTL_HOURS = 24
DEFAULT_ELASTICSEARCH_TIMEOUT_SECONDS = 5
API_ENRICHMENT_JOBS_BACKEND_ENV = "SKEINRANK_GOVERNANCE_API_ENRICHMENT_JOBS_BACKEND"
ENRICHMENT_JOBS_BACKEND_ENV = "SKEINRANK_ENRICHMENT_JOBS_BACKEND"
API_CELERY_BROKER_URL_ENV = "SKEINRANK_GOVERNANCE_API_CELERY_BROKER_URL"
CELERY_BROKER_URL_ENV = "SKEINRANK_CELERY_BROKER_URL"
API_CELERY_TASK_QUEUE_ENV = "SKEINRANK_GOVERNANCE_API_CELERY_TASK_QUEUE"
CELERY_TASK_QUEUE_ENV = "SKEINRANK_CELERY_TASK_QUEUE"
API_ENRICHMENT_CHUNK_SIZE_ENV = "SKEINRANK_GOVERNANCE_API_ENRICHMENT_CHUNK_SIZE"
ENRICHMENT_CHUNK_SIZE_ENV = "SKEINRANK_ENRICHMENT_CHUNK_SIZE"
DEFAULT_ENRICHMENT_JOBS_BACKEND = "sync"
DEFAULT_CELERY_BROKER_URL = "amqp://guest:guest@localhost:5672//"
DEFAULT_CELERY_TASK_QUEUE = "skeinrank.enrichment"
DEFAULT_ENRICHMENT_CHUNK_SIZE = 500
DEFAULT_DATABASE_URL = "sqlite:///skeinrank_governance.db"
DEFAULT_CORS_ORIGINS = ("http://127.0.0.1:5173", "http://localhost:5173")

API_OBSERVABILITY_ENABLED_ENV = "SKEINRANK_GOVERNANCE_API_OBSERVABILITY_ENABLED"
OBSERVABILITY_ENABLED_ENV = "SKEINRANK_OBSERVABILITY_ENABLED"
API_LOG_FORMAT_ENV = "SKEINRANK_GOVERNANCE_API_LOG_FORMAT"
LOG_FORMAT_ENV = "SKEINRANK_LOG_FORMAT"
API_LOG_LEVEL_ENV = "SKEINRANK_GOVERNANCE_API_LOG_LEVEL"
LOG_LEVEL_ENV = "SKEINRANK_LOG_LEVEL"
API_ACCESS_LOG_ENABLED_ENV = "SKEINRANK_GOVERNANCE_API_ACCESS_LOG_ENABLED"
ACCESS_LOG_ENABLED_ENV = "SKEINRANK_ACCESS_LOG_ENABLED"
API_REQUEST_ID_HEADER_ENV = "SKEINRANK_GOVERNANCE_API_REQUEST_ID_HEADER"
REQUEST_ID_HEADER_ENV = "SKEINRANK_REQUEST_ID_HEADER"
API_METRICS_ENABLED_ENV = "SKEINRANK_GOVERNANCE_API_METRICS_ENABLED"
METRICS_ENABLED_ENV = "SKEINRANK_METRICS_ENABLED"
API_METRICS_PATH_ENV = "SKEINRANK_GOVERNANCE_API_METRICS_PATH"
METRICS_PATH_ENV = "SKEINRANK_METRICS_PATH"
DEFAULT_LOG_FORMAT = "plain"
DEFAULT_LOG_LEVEL = "info"
DEFAULT_REQUEST_ID_HEADER = "X-Request-ID"
DEFAULT_METRICS_PATH = "/metrics"
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
    deployment_environment: str = DEFAULT_DEPLOYMENT_ENV
    production_security_enabled: bool = True
    cors_allow_origins: tuple[str, ...] = DEFAULT_CORS_ORIGINS
    auth_enabled: bool = False
    bootstrap_admin: bool = False
    admin_username: str = DEFAULT_ADMIN_USERNAME
    admin_password: str | None = None
    admin_display_name: str | None = None
    token_ttl_hours: int = DEFAULT_TOKEN_TTL_HOURS
    service_name: str = SERVICE_NAME
    service_version: str = "0.1.0"
    elasticsearch_url: str | None = None
    elasticsearch_username: str | None = None
    elasticsearch_password: str | None = None
    elasticsearch_api_key: str | None = None
    elasticsearch_timeout_seconds: int = DEFAULT_ELASTICSEARCH_TIMEOUT_SECONDS
    enrichment_jobs_backend: str = DEFAULT_ENRICHMENT_JOBS_BACKEND
    celery_broker_url: str = DEFAULT_CELERY_BROKER_URL
    celery_task_queue: str = DEFAULT_CELERY_TASK_QUEUE
    enrichment_chunk_size: int = DEFAULT_ENRICHMENT_CHUNK_SIZE

    observability_enabled: bool = True
    log_format: str = DEFAULT_LOG_FORMAT
    log_level: str = DEFAULT_LOG_LEVEL
    access_log_enabled: bool = True
    request_id_header: str = DEFAULT_REQUEST_ID_HEADER
    metrics_enabled: bool = True
    metrics_path: str = DEFAULT_METRICS_PATH

    @classmethod
    def from_env(cls) -> "GovernanceApiConfig":
        """Build API configuration from environment variables."""

        database_url = (
            os.getenv(API_DATABASE_URL_ENV)
            or os.getenv(DATABASE_URL_ENV)
            or DEFAULT_DATABASE_URL
        )
        deployment_environment = (
            (
                os.getenv(DEPLOYMENT_ENV_ENV)
                or os.getenv(GLOBAL_DEPLOYMENT_ENV_ENV)
                or DEFAULT_DEPLOYMENT_ENV
            )
            .strip()
            .lower()
        )
        return cls(
            database_url=database_url,
            create_tables_on_startup=_bool_from_env(os.getenv(CREATE_TABLES_ENV)),
            deployment_environment=deployment_environment,
            production_security_enabled=_bool_from_env(
                os.getenv(PRODUCTION_SECURITY_ENABLED_ENV), default=True
            ),
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
            elasticsearch_url=(
                os.getenv(API_ELASTICSEARCH_URL_ENV) or os.getenv(ELASTICSEARCH_URL_ENV)
            ),
            elasticsearch_username=(
                os.getenv(API_ELASTICSEARCH_USERNAME_ENV)
                or os.getenv(ELASTICSEARCH_USERNAME_ENV)
            ),
            elasticsearch_password=(
                os.getenv(API_ELASTICSEARCH_PASSWORD_ENV)
                or os.getenv(ELASTICSEARCH_PASSWORD_ENV)
            ),
            elasticsearch_api_key=(
                os.getenv(API_ELASTICSEARCH_API_KEY_ENV)
                or os.getenv(ELASTICSEARCH_API_KEY_ENV)
            ),
            elasticsearch_timeout_seconds=_int_from_env(
                os.getenv(API_ELASTICSEARCH_TIMEOUT_SECONDS_ENV)
                or os.getenv(ELASTICSEARCH_TIMEOUT_SECONDS_ENV),
                default=DEFAULT_ELASTICSEARCH_TIMEOUT_SECONDS,
            ),
            enrichment_jobs_backend=_enrichment_backend_from_env(
                os.getenv(API_ENRICHMENT_JOBS_BACKEND_ENV)
                or os.getenv(ENRICHMENT_JOBS_BACKEND_ENV)
            ),
            celery_broker_url=(
                os.getenv(API_CELERY_BROKER_URL_ENV)
                or os.getenv(CELERY_BROKER_URL_ENV)
                or DEFAULT_CELERY_BROKER_URL
            ),
            celery_task_queue=(
                os.getenv(API_CELERY_TASK_QUEUE_ENV)
                or os.getenv(CELERY_TASK_QUEUE_ENV)
                or DEFAULT_CELERY_TASK_QUEUE
            ),
            enrichment_chunk_size=_int_from_env(
                os.getenv(API_ENRICHMENT_CHUNK_SIZE_ENV)
                or os.getenv(ENRICHMENT_CHUNK_SIZE_ENV),
                default=DEFAULT_ENRICHMENT_CHUNK_SIZE,
            ),
            observability_enabled=_bool_from_env(
                os.getenv(API_OBSERVABILITY_ENABLED_ENV)
                or os.getenv(OBSERVABILITY_ENABLED_ENV),
                default=True,
            ),
            log_format=_log_format_from_env(
                os.getenv(API_LOG_FORMAT_ENV) or os.getenv(LOG_FORMAT_ENV)
            ),
            log_level=_log_level_from_env(
                os.getenv(API_LOG_LEVEL_ENV) or os.getenv(LOG_LEVEL_ENV)
            ),
            access_log_enabled=_bool_from_env(
                os.getenv(API_ACCESS_LOG_ENABLED_ENV)
                or os.getenv(ACCESS_LOG_ENABLED_ENV),
                default=True,
            ),
            request_id_header=(
                os.getenv(API_REQUEST_ID_HEADER_ENV)
                or os.getenv(REQUEST_ID_HEADER_ENV)
                or DEFAULT_REQUEST_ID_HEADER
            ).strip()
            or DEFAULT_REQUEST_ID_HEADER,
            metrics_enabled=_bool_from_env(
                os.getenv(API_METRICS_ENABLED_ENV) or os.getenv(METRICS_ENABLED_ENV),
                default=True,
            ),
            metrics_path=_metrics_path_from_env(
                os.getenv(API_METRICS_PATH_ENV) or os.getenv(METRICS_PATH_ENV)
            ),
        )

    @property
    def is_production(self) -> bool:
        """Return whether the API is running in a production deployment profile."""

        return self.deployment_environment in {"prod", "production"}

    def validate_production_security(self) -> None:
        """Validate production-only security guardrails.

        Development and test deployments keep the existing permissive defaults.
        When ``SKEINRANK_ENV`` or ``SKEINRANK_GOVERNANCE_API_ENV`` is set to
        ``production``, the API should fail fast on unsafe defaults instead of
        starting with a misleading production label.
        """

        if not self.is_production or not self.production_security_enabled:
            return

        problems: list[str] = []
        if not self.auth_enabled:
            problems.append("auth must be enabled in production")
        if self.database_url.startswith("sqlite:"):
            problems.append("SQLite database URLs are not allowed in production")
        if self.create_tables_on_startup:
            problems.append(
                "automatic table creation is not allowed in production; run migrations explicitly"
            )
        if self.bootstrap_admin:
            if not self.admin_password:
                problems.append(
                    "bootstrap admin requires SKEINRANK_GOVERNANCE_API_ADMIN_PASSWORD"
                )
            elif _is_unsafe_default_secret(self.admin_password):
                problems.append("bootstrap admin password uses an unsafe default value")
        if "*" in self.cors_allow_origins:
            problems.append("wildcard CORS origins are not allowed in production")
        if self.enrichment_jobs_backend == "celery" and _has_unsafe_broker_secret(
            self.celery_broker_url
        ):
            problems.append("Celery broker URL uses unsafe default credentials")
        if not self.elasticsearch_url:
            problems.append("Elasticsearch URL must be configured in production")

        if problems:
            details = "; ".join(problems)
            raise ValueError(f"Unsafe SkeinRank production configuration: {details}")


def _metrics_path_from_env(value: str | None) -> str:
    if value is None:
        return DEFAULT_METRICS_PATH
    normalized = value.strip()
    if not normalized:
        return DEFAULT_METRICS_PATH
    return normalized if normalized.startswith("/") else f"/{normalized}"


def _log_format_from_env(value: str | None) -> str:
    if value is None:
        return DEFAULT_LOG_FORMAT
    normalized = value.strip().lower()
    return normalized if normalized in {"plain", "json"} else DEFAULT_LOG_FORMAT


def _log_level_from_env(value: str | None) -> str:
    if value is None:
        return DEFAULT_LOG_LEVEL
    normalized = value.strip().lower()
    return (
        normalized
        if normalized in {"debug", "info", "warning", "error", "critical"}
        else DEFAULT_LOG_LEVEL
    )


def _enrichment_backend_from_env(value: str | None) -> str:
    if value is None:
        return DEFAULT_ENRICHMENT_JOBS_BACKEND
    backend = value.strip().lower()
    return backend if backend in {"sync", "celery"} else DEFAULT_ENRICHMENT_JOBS_BACKEND


_UNSAFE_DEFAULT_SECRETS = {
    "",
    "admin",
    "change-me",
    "changeme",
    "password",
    "secret",
    "skeinrank",
    "skeinrank_dev_password",
    "guest",
}


def _is_unsafe_default_secret(value: str | None) -> bool:
    if value is None:
        return True
    return value.strip().lower() in _UNSAFE_DEFAULT_SECRETS


def _has_unsafe_broker_secret(url: str) -> bool:
    normalized = url.strip().lower()
    return (
        "guest:guest@" in normalized
        or "skeinrank:skeinrank_dev_password@" in normalized
        or ":change-me@" in normalized
    )


def _package_version() -> str:
    try:
        return metadata.version(SERVICE_NAME)
    except metadata.PackageNotFoundError:
        return "0.1.0"
