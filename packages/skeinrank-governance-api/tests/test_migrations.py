from __future__ import annotations

from pathlib import Path

from skeinrank_governance_api.config import GovernanceApiConfig
from skeinrank_governance_api.migrations import (
    MIGRATION_SCRIPT_LOCATION_ENV,
    MigrationConfigurationError,
    create_alembic_config,
    resolve_migration_script_location,
    upgrade_database,
)
from sqlalchemy import create_engine, inspect, text


def test_api_resolves_governance_alembic_script_location():
    script_location = resolve_migration_script_location()

    assert script_location.name == "alembic"
    assert (script_location / "env.py").exists()
    assert (script_location / "versions").exists()


def test_api_builds_alembic_config_from_api_database_url(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'governance.db'}"
    config = create_alembic_config(GovernanceApiConfig(database_url=database_url))

    assert config.get_main_option("sqlalchemy.url") == database_url
    assert Path(config.get_main_option("script_location")).name == "alembic"


def test_api_migrations_upgrade_creates_governance_schema(tmp_path):
    database_path = tmp_path / "governance.db"
    database_url = f"sqlite:///{database_path}"

    upgrade_database(config=GovernanceApiConfig(database_url=database_url))

    engine = create_engine(database_url, future=True)
    inspector = inspect(engine)
    assert {
        "alembic_version",
        "terminology_profiles",
        "canonical_terms",
        "term_aliases",
        "term_tags",
        "profile_snapshots",
        "audit_events",
        "governance_users",
        "governance_auth_tokens",
        "governance_service_accounts",
        "governance_api_tokens",
        "governance_suggestions",
        "governance_stop_list_entries",
        "governance_global_stop_list_entries",
        "elasticsearch_bindings",
        "elasticsearch_enrichment_jobs",
    }.issubset(set(inspector.get_table_names()))
    user_columns = {
        column["name"] for column in inspector.get_columns("governance_users")
    }
    assert {"status", "is_active", "last_login_at"}.issubset(user_columns)

    service_account_columns = {
        column["name"]
        for column in inspector.get_columns("governance_service_accounts")
    }
    assert {
        "name",
        "normalized_name",
        "role",
        "is_active",
        "created_by",
    }.issubset(service_account_columns)

    api_token_columns = {
        column["name"] for column in inspector.get_columns("governance_api_tokens")
    }
    assert {
        "user_id",
        "service_account_id",
        "name",
        "token_hash",
        "token_prefix",
        "scopes",
        "expires_at",
        "revoked_at",
    }.issubset(api_token_columns)

    tag_columns = {column["name"] for column in inspector.get_columns("term_tags")}
    assert {"term_id", "value", "normalized_value"}.issubset(tag_columns)
    tag_indexes = {index["name"]: index for index in inspector.get_indexes("term_tags")}
    assert "ix_term_tags_normalized_value" in tag_indexes

    suggestion_columns = {
        column["name"] for column in inspector.get_columns("governance_suggestions")
    }
    assert {
        "suggestion_type",
        "term_id",
        "description",
        "evidence_snapshot",
        "evidence_checked_by",
        "evidence_checked_at",
        "binding_id",
        "proposal_source_type",
        "proposal_source_name",
        "idempotency_key",
        "source_payload_json",
        "validation_summary_json",
    }.issubset(suggestion_columns)
    suggestion_indexes = {
        index["name"]: index
        for index in inspector.get_indexes("governance_suggestions")
    }
    assert (
        bool(
            suggestion_indexes["ix_governance_suggestions_profile_idempotency"][
                "unique"
            ]
        )
        is True
    )

    conflict_review_columns = {
        column["name"]
        for column in inspector.get_columns("governance_conflict_reviews")
    }
    assert {
        "profile_id",
        "fingerprint",
        "conflict_type",
        "normalized_value",
        "severity",
        "review_status",
        "reviewed_by",
        "reviewed_at",
        "review_note",
        "details_json",
    }.issubset(conflict_review_columns)
    conflict_review_indexes = {
        index["name"]: index
        for index in inspector.get_indexes("governance_conflict_reviews")
    }
    assert "ix_governance_conflict_reviews_profile_status" in conflict_review_indexes
    assert "ix_governance_conflict_reviews_type_severity" in conflict_review_indexes

    stop_list_columns = {
        column["name"]
        for column in inspector.get_columns("governance_stop_list_entries")
    }
    assert {
        "profile_id",
        "value",
        "normalized_value",
        "target",
        "reason",
        "is_active",
    }.issubset(stop_list_columns)

    global_stop_list_columns = {
        column["name"]
        for column in inspector.get_columns("governance_global_stop_list_entries")
    }
    assert {
        "value",
        "normalized_value",
        "target",
        "reason",
        "is_active",
    }.issubset(global_stop_list_columns)

    binding_columns = {
        column["name"] for column in inspector.get_columns("elasticsearch_bindings")
    }
    assert {
        "profile_id",
        "name",
        "normalized_name",
        "provider",
        "index_name",
        "text_fields",
        "target_field",
        "filter_field",
        "filter_value",
        "mode",
        "write_strategy",
        "timestamp_field",
        "time_window_days",
        "is_enabled",
    }.issubset(binding_columns)

    job_columns = {
        column["name"]
        for column in inspector.get_columns("elasticsearch_enrichment_jobs")
    }
    assert {
        "binding_id",
        "profile_id",
        "status",
        "write_strategy",
        "source_index",
        "target_index",
        "alias_name",
        "documents_seen",
        "documents_enriched",
        "documents_failed",
        "result_json",
    }.issubset(job_columns)

    with engine.connect() as connection:
        revision = connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one()
    assert revision == "20260523_0019"


def test_api_migration_script_location_override_is_validated(tmp_path, monkeypatch):
    monkeypatch.setenv(MIGRATION_SCRIPT_LOCATION_ENV, str(tmp_path / "missing"))

    try:
        resolve_migration_script_location()
    except MigrationConfigurationError as exc:
        assert "does not exist" in str(exc)
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("Expected invalid migration script location to fail")
