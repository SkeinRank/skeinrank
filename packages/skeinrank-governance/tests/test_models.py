from __future__ import annotations

import pytest
from skeinrank_governance import (
    AuditEvent,
    Base,
    CanonicalTerm,
    ProfileSnapshot,
    TermAlias,
    TerminologyProfile,
    create_all,
    create_governance_engine,
    create_session_factory,
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
    audit = AuditEvent(
        profile=profile,
        actor="tester",
        action="alias_added",
        entity_type="term_alias",
        payload_json={"alias": "K8S"},
    )

    session.add_all([profile, term, alias, snapshot, audit])
    session.commit()

    assert profile.normalized_name == "default it"
    assert term.normalized_value == "kubernetes"
    assert term.slot == "TOOL"
    assert alias.normalized_alias == "k8s"
    assert snapshot.status == "draft"
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


def test_normalize_value_collapses_case_and_whitespace():
    assert normalize_value("  Kube   API  Server ") == "kube api server"
