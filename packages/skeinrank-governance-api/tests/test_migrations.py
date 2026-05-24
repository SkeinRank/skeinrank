from __future__ import annotations

from pathlib import Path

from alembic.script import ScriptDirectory
from skeinrank_governance_api.config import GovernanceApiConfig
from skeinrank_governance_api.migrations import (
    MIGRATION_SCRIPT_LOCATION_ENV,
    MigrationConfigurationError,
    check_database_schema,
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
        "agent_runs",
        "agent_document_visits",
        "agent_candidate_observations",
        "agent_evidence_windows",
        "agent_llm_reviews",
        "agent_proposal_attempts",
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

    ambiguous_alias_columns = {
        column["name"]
        for column in inspector.get_columns("governance_ambiguous_aliases")
    }
    assert {
        "profile_id",
        "surface_value",
        "normalized_surface",
        "status",
        "created_by",
        "reviewed_by",
        "reviewed_at",
        "review_note",
    }.issubset(ambiguous_alias_columns)
    ambiguous_alias_indexes = {
        index["name"]: index
        for index in inspector.get_indexes("governance_ambiguous_aliases")
    }
    assert "ix_governance_ambiguous_aliases_profile_status" in ambiguous_alias_indexes
    assert "ix_governance_ambiguous_aliases_surface" in ambiguous_alias_indexes

    ambiguous_candidate_columns = {
        column["name"]
        for column in inspector.get_columns("governance_ambiguous_alias_candidates")
    }
    assert {
        "ambiguous_alias_id",
        "term_id",
        "canonical_value",
        "normalized_canonical",
        "slot",
        "source",
        "confidence",
        "status",
        "evidence_json",
    }.issubset(ambiguous_candidate_columns)
    ambiguous_candidate_indexes = {
        index["name"]: index
        for index in inspector.get_indexes("governance_ambiguous_alias_candidates")
    }
    assert (
        "ix_governance_ambiguous_alias_candidates_term" in ambiguous_candidate_indexes
    )
    assert (
        "ix_governance_ambiguous_alias_candidates_status" in ambiguous_candidate_indexes
    )

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

    binding_policy_columns = {
        column["name"]
        for column in inspector.get_columns("governance_binding_policies")
    }
    assert {
        "binding_id",
        "profile_id",
        "status",
        "preferred_slots",
        "allowed_tags",
        "deny_slots",
        "context_rules",
        "created_by",
        "updated_by",
    }.issubset(binding_policy_columns)
    binding_policy_indexes = {
        index["name"]: index
        for index in inspector.get_indexes("governance_binding_policies")
    }
    assert "ix_governance_binding_policies_profile" in binding_policy_indexes
    assert "ix_governance_binding_policies_status" in binding_policy_indexes
    binding_policy_uniques = {
        item["name"]: item
        for item in inspector.get_unique_constraints("governance_binding_policies")
    }
    assert "uq_governance_binding_policies_binding_id" in binding_policy_uniques

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

    agent_run_columns = {
        column["name"] for column in inspector.get_columns("agent_runs")
    }
    assert {
        "run_id",
        "agent_name",
        "agent_version",
        "status",
        "trigger_type",
        "profile_id",
        "profile_name",
        "normalized_profile_name",
        "binding_id",
        "openrouter_model",
        "prompt_version",
        "workflow_engine",
        "config_hash",
        "artifacts_uri",
        "report_uri",
        "summary_json",
        "error_message",
        "requested_by",
        "started_at",
        "finished_at",
    }.issubset(agent_run_columns)
    agent_run_indexes = {
        index["name"]: index for index in inspector.get_indexes("agent_runs")
    }
    assert "ix_agent_runs_status_created" in agent_run_indexes
    assert "ix_agent_runs_profile_created" in agent_run_indexes
    agent_run_uniques = {
        item["name"]: item for item in inspector.get_unique_constraints("agent_runs")
    }
    assert "uq_agent_runs_run_id" in agent_run_uniques

    visit_columns = {
        column["name"] for column in inspector.get_columns("agent_document_visits")
    }
    assert {
        "agent_run_id",
        "run_id",
        "profile_id",
        "binding_id",
        "source_id",
        "external_document_id",
        "source_type",
        "index_name",
        "content_hash",
        "processing_context_hash",
        "visit_status",
        "should_scan",
        "metadata_json",
    }.issubset(visit_columns)
    visit_indexes = {
        index["name"] for index in inspector.get_indexes("agent_document_visits")
    }
    assert "ix_agent_document_visits_run_status" in visit_indexes
    assert "ix_agent_document_visits_hashes" in visit_indexes

    observation_columns = {
        column["name"]
        for column in inspector.get_columns("agent_candidate_observations")
    }
    assert {
        "agent_run_id",
        "run_id",
        "document_visit_id",
        "profile_id",
        "binding_id",
        "candidate_alias",
        "normalized_alias",
        "possible_canonical",
        "normalized_canonical",
        "slot",
        "observation_status",
        "discovery_score",
        "weighted_count",
        "document_frequency",
        "evidence_windows_found",
        "discovery_reasons_json",
        "canonical_hint_json",
        "candidate_pack_json",
        "metadata_json",
    }.issubset(observation_columns)
    observation_indexes = {
        index["name"] for index in inspector.get_indexes("agent_candidate_observations")
    }
    assert "ix_agent_candidate_observations_run_status" in observation_indexes
    assert "ix_agent_candidate_observations_alias" in observation_indexes
    observation_uniques = {
        item["name"]
        for item in inspector.get_unique_constraints("agent_candidate_observations")
    }
    assert "uq_agent_candidate_observations_run_alias" in observation_uniques

    evidence_window_columns = {
        column["name"] for column in inspector.get_columns("agent_evidence_windows")
    }
    assert {
        "agent_run_id",
        "candidate_observation_id",
        "document_visit_id",
        "run_id",
        "profile_id",
        "binding_id",
        "candidate_alias",
        "normalized_alias",
        "source_id",
        "source_type",
        "field",
        "start_char",
        "end_char",
        "text",
        "evidence_hash",
        "metadata_json",
    }.issubset(evidence_window_columns)
    evidence_window_indexes = {
        index["name"] for index in inspector.get_indexes("agent_evidence_windows")
    }
    assert "ix_agent_evidence_windows_run" in evidence_window_indexes
    assert "ix_agent_evidence_windows_candidate" in evidence_window_indexes
    evidence_window_uniques = {
        item["name"]
        for item in inspector.get_unique_constraints("agent_evidence_windows")
    }
    assert "uq_agent_evidence_windows_candidate_hash" in evidence_window_uniques

    llm_review_columns = {
        column["name"] for column in inspector.get_columns("agent_llm_reviews")
    }
    assert {
        "agent_run_id",
        "run_id",
        "candidate_observation_id",
        "profile_id",
        "binding_id",
        "candidate_alias",
        "normalized_alias",
        "possible_canonical",
        "normalized_canonical",
        "slot",
        "review_status",
        "action",
        "confidence",
        "model",
        "prompt_version",
        "response_id",
        "prompt_hash",
        "review_hash",
        "usage_json",
        "judgment_json",
        "raw_response_json",
    }.issubset(llm_review_columns)
    llm_review_indexes = {
        index["name"] for index in inspector.get_indexes("agent_llm_reviews")
    }
    assert "ix_agent_llm_reviews_run_status" in llm_review_indexes
    assert "ix_agent_llm_reviews_model_created" in llm_review_indexes
    llm_review_uniques = {
        item["name"] for item in inspector.get_unique_constraints("agent_llm_reviews")
    }
    assert "uq_agent_llm_reviews_run_alias_hash" in llm_review_uniques

    proposal_attempt_columns = {
        column["name"] for column in inspector.get_columns("agent_proposal_attempts")
    }
    assert {
        "agent_run_id",
        "run_id",
        "candidate_observation_id",
        "llm_review_id",
        "governance_suggestion_id",
        "profile_id",
        "binding_id",
        "alias_value",
        "normalized_alias",
        "canonical_value",
        "normalized_canonical",
        "slot",
        "attempt_status",
        "validation_status",
        "validation_category",
        "confidence",
        "idempotency_key",
        "submitted",
        "proposal_source_type",
        "proposal_source_name",
        "validation_response_json",
        "submission_response_json",
        "source_payload_json",
    }.issubset(proposal_attempt_columns)
    proposal_attempt_indexes = {
        index["name"] for index in inspector.get_indexes("agent_proposal_attempts")
    }
    assert "ix_agent_proposal_attempts_run_status" in proposal_attempt_indexes
    assert "ix_agent_proposal_attempts_idempotency" in proposal_attempt_indexes
    proposal_attempt_uniques = {
        item["name"]
        for item in inspector.get_unique_constraints("agent_proposal_attempts")
    }
    assert "uq_agent_proposal_attempts_run_idempotency" in proposal_attempt_uniques

    with engine.connect() as connection:
        revision = connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one()
    expected_head = ScriptDirectory.from_config(
        create_alembic_config(GovernanceApiConfig(database_url=database_url))
    ).get_current_head()
    assert revision == expected_head


def test_api_migrations_check_returns_zero_for_up_to_date_schema(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'governance.db'}"
    config = GovernanceApiConfig(database_url=database_url)
    upgrade_database(config=config)

    assert check_database_schema(config=config) == 0


def test_api_migration_script_location_override_is_validated(tmp_path, monkeypatch):
    monkeypatch.setenv(MIGRATION_SCRIPT_LOCATION_ENV, str(tmp_path / "missing"))

    try:
        resolve_migration_script_location()
    except MigrationConfigurationError as exc:
        assert "does not exist" in str(exc)
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("Expected invalid migration script location to fail")
