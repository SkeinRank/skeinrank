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
