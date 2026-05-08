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
    monkeypatch.setenv("SKEINRANK_ELASTICSEARCH_URL", "http://localhost:9200")
    monkeypatch.setenv("SKEINRANK_GOVERNANCE_API_ELASTICSEARCH_USERNAME", "elastic")
    monkeypatch.setenv("SKEINRANK_GOVERNANCE_API_ELASTICSEARCH_PASSWORD", "secret")
    monkeypatch.setenv("SKEINRANK_GOVERNANCE_API_ELASTICSEARCH_TIMEOUT_SECONDS", "9")

    config = GovernanceApiConfig.from_env()

    assert config.elasticsearch_url == "http://localhost:9200"
    assert config.elasticsearch_username == "elastic"
    assert config.elasticsearch_password == "secret"
    assert config.elasticsearch_timeout_seconds == 9
