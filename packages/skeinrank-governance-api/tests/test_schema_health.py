from __future__ import annotations

from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient
from skeinrank_governance import create_all, create_governance_engine
from skeinrank_governance_api import create_app
from skeinrank_governance_api.config import GovernanceApiConfig
from skeinrank_governance_api.migrations import (
    check_database_schema,
    create_alembic_config,
    upgrade_database,
)
from skeinrank_governance_api.schema_health import (
    check_schema_health,
    format_schema_health_for_cli,
)


def _database_url(tmp_path) -> str:
    return f"sqlite:///{tmp_path / 'governance.db'}"


def _head_revision(config: GovernanceApiConfig) -> str:
    head = ScriptDirectory.from_config(create_alembic_config(config)).get_current_head()
    assert head is not None
    return head


def test_schema_health_is_ok_after_alembic_upgrade(tmp_path):
    config = GovernanceApiConfig(database_url=_database_url(tmp_path))
    upgrade_database(config=config)
    engine = create_governance_engine(config.database_url)

    try:
        health = check_schema_health(engine, config=config)
    finally:
        engine.dispose()

    assert health.ok is True
    assert health.alembic_version_present is True
    assert health.current_revision == _head_revision(config)
    assert health.head_revision == _head_revision(config)
    assert health.current_matches_head is True
    assert health.multiple_heads is False
    assert health.missing_tables == []
    assert _head_revision(config) in health.migration_heads
    assert health.expected_tables_count > 0
    assert health.database_tables_count >= health.expected_tables_count


def test_schema_health_reports_create_all_database_without_alembic_version(tmp_path):
    config = GovernanceApiConfig(database_url=_database_url(tmp_path))
    engine = create_governance_engine(config.database_url)
    try:
        create_all(engine)
        health = check_schema_health(engine, config=config)
    finally:
        engine.dispose()

    assert health.ok is False
    assert health.alembic_version_present is False
    assert health.current_revision is None
    assert health.current_revisions == []
    assert health.current_matches_head is False
    assert health.missing_tables == []
    assert health.head_revision == _head_revision(config)


def test_schema_health_endpoint_reports_migration_state(tmp_path):
    config = GovernanceApiConfig(database_url=_database_url(tmp_path))
    upgrade_database(config=config)
    app = create_app(config)

    response = TestClient(app).get("/schema/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["alembic_version_present"] is True
    assert payload["current_revision"] == _head_revision(config)
    assert payload["head_revision"] == _head_revision(config)
    assert payload["missing_tables"] == []


def test_schema_health_cli_report_and_exit_code(tmp_path, capsys):
    config = GovernanceApiConfig(database_url=_database_url(tmp_path))
    upgrade_database(config=config)

    exit_code = check_database_schema(config=config)

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "schema_ok=true" in captured.out
    assert f"head_revision={_head_revision(config)}" in captured.out


def test_schema_health_cli_formatter_includes_failures(tmp_path):
    config = GovernanceApiConfig(database_url=_database_url(tmp_path))
    engine = create_governance_engine(config.database_url)
    try:
        create_all(engine)
        health = check_schema_health(engine, config=config)
    finally:
        engine.dispose()

    report = format_schema_health_for_cli(health)

    assert "schema_ok=false" in report
    assert "alembic_version_present=false" in report
    assert "missing_tables=" in report
