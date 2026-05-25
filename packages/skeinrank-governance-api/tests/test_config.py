from __future__ import annotations

from skeinrank_governance_api.config import GovernanceApiConfig


def test_config_prefers_api_database_env(monkeypatch):
    monkeypatch.setenv("SKEINRANK_GOVERNANCE_DATABASE_URL", "sqlite:///base.db")
    monkeypatch.setenv("SKEINRANK_GOVERNANCE_API_DATABASE_URL", "sqlite:///api.db")
    monkeypatch.setenv("SKEINRANK_GOVERNANCE_API_CREATE_TABLES", "true")

    config = GovernanceApiConfig.from_env()

    assert config.database_url == "sqlite:///api.db"
    assert config.create_tables_on_startup is True


def test_config_falls_back_to_governance_database_env(monkeypatch):
    monkeypatch.delenv("SKEINRANK_GOVERNANCE_API_DATABASE_URL", raising=False)
    monkeypatch.setenv("SKEINRANK_GOVERNANCE_DATABASE_URL", "sqlite:///base.db")

    config = GovernanceApiConfig.from_env()

    assert config.database_url == "sqlite:///base.db"


def test_config_parses_cors_origins_from_env(monkeypatch):
    monkeypatch.setenv(
        "SKEINRANK_GOVERNANCE_API_CORS_ORIGINS",
        "http://127.0.0.1:5173, http://localhost:5173",
    )

    config = GovernanceApiConfig.from_env()

    assert config.cors_allow_origins == (
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    )


def test_config_parses_auth_env(monkeypatch):
    monkeypatch.setenv("SKEINRANK_GOVERNANCE_API_AUTH_ENABLED", "true")
    monkeypatch.setenv("SKEINRANK_GOVERNANCE_API_BOOTSTRAP_ADMIN", "1")
    monkeypatch.setenv("SKEINRANK_GOVERNANCE_API_ADMIN_USERNAME", "root")
    monkeypatch.setenv("SKEINRANK_GOVERNANCE_API_ADMIN_PASSWORD", "secret")
    monkeypatch.setenv("SKEINRANK_GOVERNANCE_API_ADMIN_DISPLAY_NAME", "Root User")
    monkeypatch.setenv("SKEINRANK_GOVERNANCE_API_TOKEN_TTL_HOURS", "12")

    config = GovernanceApiConfig.from_env()

    assert config.auth_enabled is True
    assert config.bootstrap_admin is True
    assert config.admin_username == "root"
    assert config.admin_password == "secret"
    assert config.admin_display_name == "Root User"
    assert config.token_ttl_hours == 12


def test_config_parses_elasticsearch_env(monkeypatch):
    monkeypatch.delenv("SKEINRANK_GOVERNANCE_API_ELASTICSEARCH_URL", raising=False)
    monkeypatch.delenv("SKEINRANK_GOVERNANCE_API_ELASTICSEARCH_API_KEY", raising=False)
    monkeypatch.setenv("SKEINRANK_ELASTICSEARCH_URL", "http://localhost:9200")
    monkeypatch.setenv("SKEINRANK_GOVERNANCE_API_ELASTICSEARCH_USERNAME", "elastic")
    monkeypatch.setenv("SKEINRANK_GOVERNANCE_API_ELASTICSEARCH_PASSWORD", "secret")
    monkeypatch.setenv("SKEINRANK_GOVERNANCE_API_ELASTICSEARCH_TIMEOUT_SECONDS", "9")

    config = GovernanceApiConfig.from_env()

    assert config.elasticsearch_url == "http://localhost:9200"
    assert config.elasticsearch_username == "elastic"
    assert config.elasticsearch_password == "secret"
    assert config.elasticsearch_timeout_seconds == 9


def test_config_parses_enrichment_worker_env(monkeypatch):
    monkeypatch.delenv(
        "SKEINRANK_GOVERNANCE_API_ENRICHMENT_JOBS_BACKEND", raising=False
    )
    monkeypatch.delenv("SKEINRANK_GOVERNANCE_API_CELERY_BROKER_URL", raising=False)
    monkeypatch.delenv("SKEINRANK_GOVERNANCE_API_CELERY_TASK_QUEUE", raising=False)
    monkeypatch.delenv("SKEINRANK_GOVERNANCE_API_ENRICHMENT_CHUNK_SIZE", raising=False)
    monkeypatch.setenv("SKEINRANK_ENRICHMENT_JOBS_BACKEND", "celery")
    monkeypatch.setenv(
        "SKEINRANK_CELERY_BROKER_URL", "amqp://guest:guest@rabbitmq:5672//"
    )
    monkeypatch.setenv("SKEINRANK_CELERY_TASK_QUEUE", "skeinrank.custom")
    monkeypatch.setenv("SKEINRANK_ENRICHMENT_CHUNK_SIZE", "250")

    config = GovernanceApiConfig.from_env()

    assert config.enrichment_jobs_backend == "celery"
    assert config.celery_broker_url == "amqp://guest:guest@rabbitmq:5672//"
    assert config.celery_task_queue == "skeinrank.custom"
    assert config.enrichment_chunk_size == 250


def test_config_defaults_unknown_enrichment_backend_to_sync(monkeypatch):
    monkeypatch.setenv("SKEINRANK_GOVERNANCE_API_ENRICHMENT_JOBS_BACKEND", "unknown")

    config = GovernanceApiConfig.from_env()

    assert config.enrichment_jobs_backend == "sync"


def test_config_parses_deployment_environment(monkeypatch):
    monkeypatch.setenv("SKEINRANK_ENV", "production")
    monkeypatch.setenv("SKEINRANK_GOVERNANCE_API_PRODUCTION_SECURITY_ENABLED", "false")

    config = GovernanceApiConfig.from_env()

    assert config.deployment_environment == "production"
    assert config.is_production is True
    assert config.production_security_enabled is False


def test_config_parses_observability_env(monkeypatch):
    monkeypatch.setenv("SKEINRANK_GOVERNANCE_API_OBSERVABILITY_ENABLED", "true")
    monkeypatch.setenv("SKEINRANK_GOVERNANCE_API_LOG_FORMAT", "json")
    monkeypatch.setenv("SKEINRANK_GOVERNANCE_API_LOG_LEVEL", "debug")
    monkeypatch.setenv("SKEINRANK_GOVERNANCE_API_ACCESS_LOG_ENABLED", "false")
    monkeypatch.setenv("SKEINRANK_GOVERNANCE_API_REQUEST_ID_HEADER", "X-Correlation-ID")
    monkeypatch.setenv("SKEINRANK_GOVERNANCE_API_METRICS_ENABLED", "true")
    monkeypatch.setenv("SKEINRANK_GOVERNANCE_API_METRICS_PATH", "metrics")

    config = GovernanceApiConfig.from_env()

    assert config.observability_enabled is True
    assert config.log_format == "json"
    assert config.log_level == "debug"
    assert config.access_log_enabled is False
    assert config.request_id_header == "X-Correlation-ID"
    assert config.metrics_enabled is True
    assert config.metrics_path == "/metrics"


def test_config_defaults_unknown_observability_values(monkeypatch):
    monkeypatch.setenv("SKEINRANK_GOVERNANCE_API_LOG_FORMAT", "xml")
    monkeypatch.setenv("SKEINRANK_GOVERNANCE_API_LOG_LEVEL", "verbose")

    config = GovernanceApiConfig.from_env()

    assert config.log_format == "plain"
    assert config.log_level == "info"


def test_production_security_rejects_unsafe_defaults():
    config = GovernanceApiConfig(
        deployment_environment="production",
        database_url="sqlite:///dev.db",
        auth_enabled=False,
        bootstrap_admin=True,
        admin_password="change-me",
        cors_allow_origins=("*",),
        enrichment_jobs_backend="celery",
        celery_broker_url="amqp://guest:guest@rabbitmq:5672//",
        elasticsearch_url=None,
    )

    try:
        config.validate_production_security()
    except ValueError as exc:
        message = str(exc)
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("expected production security validation to fail")

    assert "auth must be enabled" in message
    assert "SQLite database URLs" in message
    assert "unsafe default value" in message
    assert "wildcard CORS" in message
    assert "unsafe default credentials" in message
    assert "Elasticsearch URL" not in message


def test_production_security_accepts_hardened_config():
    config = GovernanceApiConfig(
        deployment_environment="production",
        database_url="postgresql+psycopg://user:strong@postgres:5432/skeinrank",
        auth_enabled=True,
        bootstrap_admin=True,
        admin_password="long-unique-admin-password",
        cors_allow_origins=("https://skeinrank.example.com",),
        enrichment_jobs_backend="celery",
        celery_broker_url="amqp://skeinrank:long-unique-rabbit-password@rabbitmq:5672//",
        elasticsearch_url=None,
    )

    config.validate_production_security()


def test_production_security_rejects_elasticsearch_credentials_without_url():
    config = GovernanceApiConfig(
        deployment_environment="production",
        database_url="postgresql+psycopg://user:strong@postgres:5432/skeinrank",
        auth_enabled=True,
        bootstrap_admin=True,
        admin_password="long-unique-admin-password",
        cors_allow_origins=("https://skeinrank.example.com",),
        enrichment_jobs_backend="sync",
        elasticsearch_url=None,
        elasticsearch_api_key="secret-es-api-key",
    )

    try:
        config.validate_production_security()
    except ValueError as exc:
        message = str(exc)
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("expected production security validation to fail")

    assert "Elasticsearch credentials require" in message


def test_config_parses_tracing_env(monkeypatch):
    monkeypatch.setenv("SKEINRANK_GOVERNANCE_API_TRACING_ENABLED", "true")
    monkeypatch.setenv(
        "SKEINRANK_GOVERNANCE_API_OTEL_SERVICE_NAME", "skeinrank-test-api"
    )
    monkeypatch.setenv("SKEINRANK_GOVERNANCE_API_OTEL_TRACES_EXPORTER", "otlp")
    monkeypatch.setenv(
        "SKEINRANK_GOVERNANCE_API_OTEL_EXPORTER_OTLP_ENDPOINT",
        "http://collector:4317",
    )
    monkeypatch.setenv("SKEINRANK_GOVERNANCE_API_OTEL_SAMPLING_RATIO", "0.25")
    monkeypatch.setenv("SKEINRANK_GOVERNANCE_API_OTEL_CAPTURE_QUERY_TEXT", "true")

    config = GovernanceApiConfig.from_env()

    assert config.tracing_enabled is True
    assert config.otel_service_name == "skeinrank-test-api"
    assert config.otel_traces_exporter == "otlp"
    assert config.otel_exporter_otlp_endpoint == "http://collector:4317"
    assert config.otel_sampling_ratio == 0.25
    assert config.otel_capture_query_text is True


def test_config_defaults_unknown_tracing_values(monkeypatch):
    monkeypatch.setenv("SKEINRANK_GOVERNANCE_API_OTEL_TRACES_EXPORTER", "vendor")
    monkeypatch.setenv("SKEINRANK_GOVERNANCE_API_OTEL_SAMPLING_RATIO", "2.0")

    config = GovernanceApiConfig.from_env()

    assert config.otel_traces_exporter == "none"
    assert config.otel_sampling_ratio == 1.0
