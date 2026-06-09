from __future__ import annotations

import pytest
from skeinrank_governance import (
    AgentCandidateObservation,
    AgentDocumentVisit,
    AgentEvidenceWindow,
    AgentLlmReview,
    AgentProposalAttempt,
    AgentRun,
    AuditEvent,
    Base,
    CanonicalTerm,
    ElasticsearchBinding,
    ElasticsearchEnrichmentJob,
    GovernanceAmbiguousAlias,
    GovernanceAmbiguousAliasCandidate,
    GovernanceApiToken,
    GovernanceAuthToken,
    GovernanceBindingPolicy,
    GovernanceConflictReview,
    GovernanceGlobalStopListEntry,
    GovernanceServiceAccount,
    GovernanceStopListEntry,
    GovernanceSuggestion,
    GovernanceUser,
    ProfileSnapshot,
    TermAlias,
    TerminologyProfile,
    TermTag,
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
        "term_tags",
        "profile_snapshots",
        "audit_events",
        "governance_users",
        "governance_auth_tokens",
        "governance_service_accounts",
        "governance_api_tokens",
        "governance_suggestions",
        "governance_conflict_reviews",
        "governance_ambiguous_aliases",
        "governance_ambiguous_alias_candidates",
        "governance_binding_policies",
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
        context_triggers=["rollout", "pod crash"],
    )
    tag = TermTag(term=term, value="Infra")
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
        evidence_snapshot={
            "binding_id": 1,
            "binding_name": "Infra Docs",
            "index_name": "docs",
            "profile_name": "Default IT",
            "query": "kube",
            "normalized_query": "kube",
            "canonical_value": "Kubernetes",
            "max_documents": 5,
            "documents": [],
            "warnings": [],
        },
        evidence_checked_by="tester",
    )
    conflict_review = GovernanceConflictReview(
        profile=profile,
        fingerprint="abc123",
        conflict_type="alias_maps_to_multiple_canonicals",
        normalized_value="pg",
        severity="high",
        review_status="ignored",
        reviewed_by="tester",
        review_note="Accepted cross-domain term",
        details_json={"scope": "cross_profile"},
    )
    ambiguous_alias = GovernanceAmbiguousAlias(
        profile=profile,
        surface_value="PG",
        status="open",
        created_by="tester",
        review_note="Needs binding policy",
    )
    ambiguous_candidate = GovernanceAmbiguousAliasCandidate(
        ambiguous_alias=ambiguous_alias,
        term=term,
        canonical_value="Kubernetes",
        slot="TOOL",
        source="manual",
        confidence=0.88,
        status="candidate",
        evidence_json={"query_count": 42},
    )
    stop_list_entry = GovernanceStopListEntry(
        profile=profile,
        value="Service",
        target="alias",
        reason="Too generic for this profile",
    )
    global_stop_list_entry = GovernanceGlobalStopListEntry(
        value="Unknown",
        target="both",
        reason="Organization-wide noise",
    )
    user = GovernanceUser(
        username="Maxim",
        display_name="Maxim",
        password_hash="hash",
        role="admin",
    )
    service_account = GovernanceServiceAccount(
        name="Migration Bot",
        display_name="Migration Bot",
        description="Loads dictionary migrations.",
        role="moderator",
        created_by="tester",
    )
    personal_token = GovernanceApiToken(
        user=user,
        name="Jupyter token",
        token_hash="personal-hash",
        token_prefix="sk_pat_abc",
        scopes=["migration:apply", "migration:validate", "migration:validate"],
        created_by="Maxim",
    )
    service_token = GovernanceApiToken(
        service_account=service_account,
        name="CI token",
        token_hash="service-hash",
        token_prefix="sk_sat_abc",
        scopes=["migration:validate"],
        created_by="tester",
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
        timestamp_field="created_at",
        time_window_days=1825,
    )
    binding_policy = GovernanceBindingPolicy(
        binding=binding,
        profile=profile,
        preferred_slots=["database", " tool "],
        allowed_tags=["Infra", " backend "],
        deny_slots=["document_component"],
        context_rules=[
            {
                "surface": "PG",
                "prefer": "PostgreSQL",
                "slot": "database",
                "reason": "Infra binding",
            }
        ],
        created_by="tester",
        updated_by="tester",
    )
    job = ElasticsearchEnrichmentJob(
        binding=binding,
        profile=profile,
        status="queued",
        write_strategy="reindex_alias_swap",
        source_index="docs",
        target_index="docs__skeinrank_job_1",
        alias_name="docs_current",
        requested_by="tester",
    )
    agent_run = AgentRun(
        profile=profile,
        binding=binding,
        run_id="run-001",
        agent_name="openrouter_alias_scout",
        agent_version="agent-runner-v1",
        status="running",
        trigger_type="scheduled",
        openrouter_model="openai/gpt-4o-mini",
        prompt_version="prompt-v1",
        workflow_engine="dependency_light_state_machine",
        config_hash="abc123",
        artifacts_uri="reports/run-001",
        report_uri="reports/run-001/manifest.json",
        summary_json={"candidates": 3},
        requested_by="agent-service-account",
    )
    visit = AgentDocumentVisit(
        agent_run=agent_run,
        profile=profile,
        binding=binding,
        run_id="run-001",
        source_id="doc-001",
        source_type="elasticsearch_hit",
        index_name="default-it-docs",
        content_hash="abc123def456",
        processing_context_hash="ctx123def456",
        agent_name="openrouter_alias_scout",
        agent_version="document-visit-v1",
        prompt_version="prompt-v1",
        openrouter_model="openai/gpt-4o-mini",
        visit_status="new_document",
        should_scan=True,
        metadata_json={"title": "Kubernetes rollout"},
    )
    observation = AgentCandidateObservation(
        agent_run=agent_run,
        document_visit=visit,
        profile=profile,
        binding=binding,
        run_id="run-001",
        candidate_alias="k8s",
        normalized_alias="k8s",
        possible_canonical="kubernetes",
        normalized_canonical="kubernetes",
        slot="TOOL",
        observation_status="queued_for_review",
        discovery_score=9.5,
        weighted_count=3.0,
        document_frequency=1,
        discovery_reasons_json=["mixed_alpha_digit"],
        canonical_hint_json={"reason": "single_configured_alias_match"},
        candidate_pack_json={"possible_canonical": "kubernetes"},
        metadata_json={"source": "unit-test"},
    )
    evidence_window = AgentEvidenceWindow(
        agent_run=agent_run,
        candidate_observation=observation,
        document_visit=visit,
        profile=profile,
        binding=binding,
        run_id="run-001",
        candidate_alias="k8s",
        normalized_alias="k8s",
        source_id="doc-001",
        source_type="elasticsearch_hit",
        field="body",
        start_char=0,
        end_char=17,
        text="k8s rollout notes",
        evidence_hash="evidence123456",
        metadata_json={"title": "Kubernetes rollout"},
    )
    llm_review = AgentLlmReview(
        agent_run=agent_run,
        candidate_observation=observation,
        profile=profile,
        binding=binding,
        run_id="run-001",
        candidate_alias="k8s",
        normalized_alias="k8s",
        possible_canonical="kubernetes",
        normalized_canonical="kubernetes",
        slot="TOOL",
        review_status="proposed",
        action="propose",
        confidence=0.9,
        model="openai/gpt-4o-mini",
        prompt_version="prompt-v1",
        response_id="resp-001",
        prompt_hash="prompt123456",
        review_hash="review123456",
        usage_json={"total_tokens": 123},
        judgment_json={"reason": "evidence matched"},
        raw_response_json={"id": "resp-001"},
    )
    proposal_attempt = AgentProposalAttempt(
        agent_run=agent_run,
        candidate_observation=observation,
        llm_review=llm_review,
        profile=profile,
        binding=binding,
        run_id="run-001",
        alias_value="k8s",
        normalized_alias="k8s",
        canonical_value="kubernetes",
        normalized_canonical="kubernetes",
        slot="TOOL",
        attempt_status="validation_passed",
        validation_status="passed",
        validation_category="validation_passed",
        confidence=0.9,
        idempotency_key="run-001:k8s",
        proposal_source_type="agent",
        proposal_source_name="openrouter-alias-scout",
        validation_response_json={"status": "passed"},
        source_payload_json={"candidate_alias": "k8s"},
    )
    audit = AuditEvent(
        profile=profile,
        actor="tester",
        action="alias_added",
        entity_type="term_alias",
        payload_json={"alias": "K8S"},
    )

    session.add_all(
        [
            profile,
            term,
            alias,
            tag,
            snapshot,
            suggestion,
            conflict_review,
            ambiguous_alias,
            ambiguous_candidate,
            stop_list_entry,
            global_stop_list_entry,
            user,
            service_account,
            personal_token,
            service_token,
            binding,
            job,
            agent_run,
            visit,
            observation,
            evidence_window,
            llm_review,
            proposal_attempt,
            audit,
        ]
    )
    session.commit()

    assert profile.normalized_name == "default_it"
    assert term.normalized_value == "kubernetes"
    assert term.slot == "TOOL"
    assert alias.normalized_alias == "k8s"
    assert alias.context_triggers == ["rollout", "pod crash"]
    assert tag.value == "infra"
    assert tag.normalized_value == "infra"
    assert snapshot.status == "draft"
    assert suggestion.suggestion_type == "alias"
    assert suggestion.normalized_canonical == "kubernetes"
    assert suggestion.normalized_alias == "kube"
    assert suggestion.slot == "TOOL"
    assert suggestion.status == "pending"
    assert suggestion.evidence_snapshot["query"] == "kube"
    assert suggestion.evidence_checked_by == "tester"
    assert conflict_review.severity == "high"
    assert conflict_review.review_status == "ignored"
    assert conflict_review.review_note == "Accepted cross-domain term"
    assert ambiguous_alias.normalized_surface == "pg"
    assert ambiguous_alias.status == "open"
    assert ambiguous_candidate.normalized_canonical == "kubernetes"
    assert ambiguous_candidate.slot == "TOOL"
    assert ambiguous_candidate.evidence_json == {"query_count": 42}
    assert binding_policy.preferred_slots == [
        "TOOL",
        "DATABASE",
    ] or binding_policy.preferred_slots == ["DATABASE", "TOOL"]
    assert binding_policy.allowed_tags == ["backend", "infra"]
    assert binding_policy.deny_slots == ["DOCUMENT_COMPONENT"]
    assert binding_policy.context_rules[0]["normalized_surface"] == "pg"
    assert binding_policy.context_rules[0]["normalized_prefer"] == "postgresql"
    assert binding_policy.context_rules[0]["slot"] == "DATABASE"
    assert stop_list_entry.normalized_value == "service"
    assert stop_list_entry.target == "alias"
    assert stop_list_entry.is_active is True
    assert global_stop_list_entry.normalized_value == "unknown"
    assert global_stop_list_entry.target == "both"
    assert global_stop_list_entry.is_active is True
    assert user.normalized_username == "maxim"
    assert user.status == "active"
    assert user.is_active is True
    assert service_account.normalized_name == "migration_bot"
    assert service_account.role == "moderator"
    assert personal_token.scopes == ["migration:apply", "migration:validate"]
    assert service_token.scopes == ["migration:validate"]
    assert binding.normalized_name == "infra_docs"
    assert binding.provider == "elasticsearch"
    assert binding.text_fields == ["title", "body", "body"]
    assert binding.mode == "dry_run"
    assert binding.write_strategy == "reindex_alias_swap"
    assert binding.timestamp_field == "created_at"
    assert binding.time_window_days == 1825
    assert job.status == "queued"
    assert job.write_strategy == "reindex_alias_swap"
    assert job.documents_seen == 0
    assert agent_run.status == "running"
    assert agent_run.trigger_type == "scheduled"
    assert agent_run.normalized_profile_name == "default_it"
    assert agent_run.summary_json == {"candidates": 3}
    assert agent_run.document_visits[0].source_id == "doc-001"
    assert agent_run.document_visits[0].should_scan is True
    assert agent_run.candidate_observations[0].candidate_alias == "k8s"
    assert agent_run.candidate_observations[0].evidence_windows_found == 0
    assert agent_run.evidence_windows[0].text == "k8s rollout notes"
    assert agent_run.llm_reviews[0].review_status == "proposed"
    assert agent_run.llm_reviews[0].review_hash == "review123456"
    assert agent_run.proposal_attempts[0].attempt_status == "validation_passed"
    assert agent_run.proposal_attempts[0].idempotency_key == "run-001:k8s"
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


def test_global_stop_list_overlap_is_rejected(session):
    session.add_all(
        [
            GovernanceGlobalStopListEntry(value="unknown", target="alias"),
            GovernanceGlobalStopListEntry(value="Unknown", target="alias"),
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
    assert "governance_service_accounts" in table_names
    assert "governance_api_tokens" in table_names
    assert "governance_suggestions" in table_names
    assert "governance_stop_list_entries" in table_names
    assert "governance_global_stop_list_entries" in table_names
    assert "elasticsearch_bindings" in table_names
    assert "elasticsearch_enrichment_jobs" in table_names
    assert "agent_runs" in table_names
    assert "agent_document_visits" in table_names
    assert "agent_candidate_observations" in table_names
    assert "agent_evidence_windows" in table_names

    suggestion_columns = {
        column["name"]
        for column in inspect(engine).get_columns("governance_suggestions")
    }
    assert {
        "binding_id",
        "proposal_source_type",
        "proposal_source_name",
        "idempotency_key",
        "source_payload_json",
        "validation_summary_json",
    }.issubset(suggestion_columns)


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


def test_paused_elasticsearch_enrichment_job_status_is_valid(session):
    profile = TerminologyProfile(name="default_it")
    binding = ElasticsearchBinding(
        profile=profile,
        name="docs",
        index_name="docs",
        text_fields=["body"],
        target_field="skeinrank",
    )
    job = ElasticsearchEnrichmentJob(
        binding=binding,
        profile=profile,
        status="paused",
        write_strategy="reindex_alias_swap",
        source_index="docs",
    )
    session.add(job)

    session.commit()


def test_invalid_elasticsearch_enrichment_job_status_is_rejected(session):
    profile = TerminologyProfile(name="default_it")
    binding = ElasticsearchBinding(
        profile=profile,
        name="docs",
        index_name="docs",
        text_fields=["body"],
        target_field="skeinrank",
    )
    job = ElasticsearchEnrichmentJob(
        binding=binding,
        profile=profile,
        status="not_a_status",
        write_strategy="reindex_alias_swap",
        source_index="docs",
    )
    session.add(job)

    with pytest.raises(IntegrityError):
        session.commit()


def test_term_tags_are_unique_per_term(session):
    profile = TerminologyProfile(name="Default IT")
    term = CanonicalTerm(profile=profile, canonical_value="PostgreSQL", slot="database")
    session.add_all([profile, term])
    session.flush()

    session.add_all(
        [TermTag(term=term, value="Storage"), TermTag(term=term, value=" storage ")]
    )

    with pytest.raises(IntegrityError):
        session.commit()
