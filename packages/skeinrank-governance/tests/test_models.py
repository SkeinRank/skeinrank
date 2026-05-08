from __future__ import annotations

import pytest
from skeinrank_governance import (
    AuditEvent,
    Base,
    CanonicalTerm,
    ElasticsearchBinding,
    GovernanceAuthToken,
    GovernanceStopListEntry,
    GovernanceSuggestion,
    GovernanceUser,
    ProfileSnapshot,
    TermAlias,
    TerminologyProfile,
    create_all,
    create_governance_engine,
    create_session_factory,
    normalize_profile_name,
    normalize_value,
)
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError


@pytest.fixture()
def session():
    engine = create_governance_engine("sqlite+pysqlite:///:memory:")
    create_all(engine)
    Session = create_session_factory(engine)
    with Session() as session:
        yield session


def test_metadata_contains_expected_tables():
    expected = {
        "terminology_profiles",
        "canonical_terms",
        "term_aliases",
        "profile_snapshots",
        "audit_events",
        "governance_users",
        "governance_auth_tokens",
        "governance_suggestions",
        "governance_stop_list_entries",
        "elasticsearch_bindings",
    }

    assert expected.issubset(set(Base.metadata.tables))


def test_create_governance_rows_and_normalized_values(session):
    profile = TerminologyProfile(name="Default IT", description="IT terminology")
    term = CanonicalTerm(
        profile=profile,
        canonical_value="Kubernetes",
        slot="tool",
        description="Container orchestration platform",
    )
    alias = TermAlias(
        profile=profile,
        term=term,
        alias_value="K8S",
        confidence=0.99,
    )
    snapshot = ProfileSnapshot(
        profile=profile,
        version="default_it@v1",
        artifact_path="snapshots/default_it.json",
    )
    suggestion = GovernanceSuggestion(
        profile=profile,
        canonical_value="Kubernetes",
        alias_value="Kube",
        slot="tool",
        confidence=0.72,
        source="manual",
        context="People search for kube",
        created_by="tester",
    )
    stop_list_entry = GovernanceStopListEntry(
        profile=profile,
        value="Service",
        target="alias",
        reason="Too generic for this profile",
    )
    binding = ElasticsearchBinding(
        profile=profile,
        name="Infra Docs",
        description="Apply infra profile to documentation.",
        index_name="docs",
        text_fields=["title", "body", "body"],
        target_field="skeinrank",
        filter_field="team",
        filter_value="infra",
    )
    audit = AuditEvent(
        profile=profile,
        actor="tester",
        action="alias_added",
        entity_type="term_alias",
        payload_json={"alias": "K8S"},
    )

    session.add_all(
        [profile, term, alias, snapshot, suggestion, stop_list_entry, binding, audit]
    )
    session.commit()

    assert profile.normalized_name == "default_it"
    assert term.normalized_value == "kubernetes"
    assert term.slot == "TOOL"
    assert alias.normalized_alias == "k8s"
    assert snapshot.status == "draft"
    assert suggestion.suggestion_type == "alias"
    assert suggestion.normalized_canonical == "kubernetes"
    assert suggestion.normalized_alias == "kube"
    assert suggestion.slot == "TOOL"
    assert suggestion.status == "pending"
    assert stop_list_entry.normalized_value == "service"
    assert stop_list_entry.target == "alias"
    assert stop_list_entry.is_active is True
    assert binding.normalized_name == "infra_docs"
    assert binding.provider == "elasticsearch"
    assert binding.text_fields == ["title", "body", "body"]
    assert binding.mode == "dry_run"
    assert binding.write_strategy == "reindex_alias_swap"
    assert audit.payload_json == {"alias": "K8S"}


def test_profile_wide_alias_collision_is_rejected(session):
    profile = TerminologyProfile(name="default_it")
    first = CanonicalTerm(profile=profile, canonical_value="postgresql", slot="DB")
    second = CanonicalTerm(
        profile=profile, canonical_value="payment-gateway", slot="SERVICE"
    )
    session.add_all(
        [
            profile,
            first,
            second,
            TermAlias(profile=profile, term=first, alias_value="pg"),
            TermAlias(profile=profile, term=second, alias_value="PG"),
        ]
    )

    with pytest.raises(IntegrityError):
        session.commit()


def test_snapshot_version_is_unique_per_profile(session):
    profile = TerminologyProfile(name="default_it")
    session.add_all(
        [
            profile,
            ProfileSnapshot(profile=profile, version="default_it@v1"),
            ProfileSnapshot(profile=profile, version="default_it@v1"),
        ]
    )

    with pytest.raises(IntegrityError):
        session.commit()


def test_invalid_alias_status_is_rejected(session):
    profile = TerminologyProfile(name="default_it")
    term = CanonicalTerm(profile=profile, canonical_value="kubernetes", slot="TOOL")
    alias = TermAlias(profile=profile, term=term, alias_value="k8s", status="unknown")
    session.add_all([profile, term, alias])

    with pytest.raises(IntegrityError):
        session.commit()


def test_tables_can_be_created_with_sqlalchemy_inspector():
    engine = create_governance_engine("sqlite+pysqlite:///:memory:")
    create_all(engine)

    table_names = set(inspect(engine).get_table_names())

    assert "terminology_profiles" in table_names
    assert "canonical_terms" in table_names
    assert "term_aliases" in table_names
    assert "governance_users" in table_names
    assert "governance_auth_tokens" in table_names
    assert "governance_suggestions" in table_names
    assert "governance_stop_list_entries" in table_names
    assert "elasticsearch_bindings" in table_names


def test_normalize_value_collapses_case_and_whitespace():
    assert normalize_value("  Kube   API  Server ") == "kube api server"


def test_normalize_profile_name_treats_slugs_and_display_names_as_same():
    assert normalize_profile_name("default_it") == "default_it"
    assert normalize_profile_name("Default IT") == "default_it"
    assert normalize_profile_name("default-it") == "default_it"
    assert normalize_profile_name("  Default   IT  ") == "default_it"


def test_governance_user_normalized_username(session):
    user = GovernanceUser(
        username="Admin User",
        display_name="Admin",
        password_hash="hash",
        role="admin",
    )
    session.add(user)
    session.commit()

    assert user.normalized_username == "admin_user"


def test_invalid_governance_user_role_is_rejected(session):
    user = GovernanceUser(
        username="bad",
        password_hash="hash",
        role="owner",
    )
    session.add(user)

    with pytest.raises(IntegrityError):
        session.commit()


def test_governance_auth_token_is_linked_to_user(session):
    from datetime import timedelta

    from skeinrank_governance.models import utc_now

    user = GovernanceUser(
        username="admin",
        password_hash="hash",
        role="admin",
    )
    token = GovernanceAuthToken(
        user=user,
        token_hash="abc",
        token_prefix="abc",
        expires_at=utc_now() + timedelta(hours=1),
    )
    session.add_all([user, token])
    session.commit()

    assert token.user.username == "admin"


def test_canonical_term_suggestion_normalizes_without_alias(session):
    profile = TerminologyProfile(name="default_it")
    suggestion = GovernanceSuggestion(
        profile=profile,
        suggestion_type="canonical_term",
        canonical_value="Vector Database",
        alias_value=None,
        slot="tool",
        description="Vector search storage system",
        context="No canonical term exists for vector databases yet.",
    )
    session.add_all([profile, suggestion])
    session.commit()

    assert suggestion.normalized_canonical == "vector database"
    assert suggestion.normalized_alias is None
    assert suggestion.slot == "TOOL"
    assert suggestion.description == "Vector search storage system"


def test_invalid_governance_suggestion_type_is_rejected(session):
    profile = TerminologyProfile(name="default_it")
    suggestion = GovernanceSuggestion(
        profile=profile,
        suggestion_type="rename",
        canonical_value="kubernetes",
        alias_value="k8s",
        slot="TOOL",
    )
    session.add_all([profile, suggestion])

    with pytest.raises(IntegrityError):
        session.commit()


def test_invalid_governance_suggestion_status_is_rejected(session):
    profile = TerminologyProfile(name="default_it")
    suggestion = GovernanceSuggestion(
        profile=profile,
        canonical_value="kubernetes",
        alias_value="k8s",
        slot="TOOL",
        status="merged",
    )
    session.add_all([profile, suggestion])

    with pytest.raises(IntegrityError):
        session.commit()


def test_invalid_governance_suggestion_confidence_is_rejected(session):
    profile = TerminologyProfile(name="default_it")
    suggestion = GovernanceSuggestion(
        profile=profile,
        canonical_value="kubernetes",
        alias_value="k8s",
        slot="TOOL",
        confidence=1.5,
    )
    session.add_all([profile, suggestion])

    with pytest.raises(IntegrityError):
        session.commit()


def test_stop_list_entry_target_is_validated(session):
    profile = TerminologyProfile(name="default_it")
    entry = GovernanceStopListEntry(
        profile=profile,
        value="service",
        target="unknown",
    )
    session.add_all([profile, entry])

    with pytest.raises(IntegrityError):
        session.commit()


def test_stop_list_entry_uniqueness_is_profile_target_scoped(session):
    profile = TerminologyProfile(name="default_it")
    first = GovernanceStopListEntry(profile=profile, value="Service", target="alias")
    second = GovernanceStopListEntry(profile=profile, value=" service ", target="alias")
    session.add_all([profile, first, second])

    with pytest.raises(IntegrityError):
        session.commit()


def test_invalid_elasticsearch_binding_mode_is_rejected(session):
    profile = TerminologyProfile(name="default_it")
    binding = ElasticsearchBinding(
        profile=profile,
        name="docs",
        index_name="docs",
        text_fields=["body"],
        target_field="skeinrank",
        mode="unsafe",
    )
    session.add(binding)

    with pytest.raises(IntegrityError):
        session.commit()


def test_invalid_elasticsearch_binding_write_strategy_is_rejected(session):
    profile = TerminologyProfile(name="default_it")
    binding = ElasticsearchBinding(
        profile=profile,
        name="docs",
        index_name="docs",
        text_fields=["body"],
        target_field="skeinrank",
        write_strategy="unsafe",
    )
    session.add(binding)

    with pytest.raises(IntegrityError):
        session.commit()
