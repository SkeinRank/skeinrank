from __future__ import annotations

import skeinrank_governance as governance


def test_public_api_exports_governance_models_and_helpers():
    assert governance.TerminologyProfile.__tablename__ == "terminology_profiles"
    assert governance.CanonicalTerm.__tablename__ == "canonical_terms"
    assert governance.TermAlias.__tablename__ == "term_aliases"
    assert governance.TermTag.__tablename__ == "term_tags"
    assert (
        governance.GovernanceBindingPolicy.__tablename__
        == "governance_binding_policies"
    )
    assert governance.ProfileSnapshot.__tablename__ == "profile_snapshots"
    assert governance.AgentRun.__tablename__ == "agent_runs"
    assert governance.AgentDocumentVisit.__tablename__ == "agent_document_visits"
    assert (
        governance.AgentCandidateObservation.__tablename__
        == "agent_candidate_observations"
    )
    assert governance.AgentEvidenceWindow.__tablename__ == "agent_evidence_windows"
    assert governance.AgentLlmReview.__tablename__ == "agent_llm_reviews"
    assert governance.AgentProposalAttempt.__tablename__ == "agent_proposal_attempts"
    assert governance.AuditEvent.__tablename__ == "audit_events"
    assert governance.GovernanceUser.__tablename__ == "governance_users"
    assert governance.GovernanceAuthToken.__tablename__ == "governance_auth_tokens"
    assert governance.GovernanceServiceAccount.__tablename__ == (
        "governance_service_accounts"
    )
    assert governance.GovernanceApiToken.__tablename__ == "governance_api_tokens"
    assert governance.ElasticsearchBinding.__tablename__ == "elasticsearch_bindings"
    assert (
        governance.ElasticsearchEnrichmentJob.__tablename__
        == "elasticsearch_enrichment_jobs"
    )
    assert governance.GovernanceSuggestion.__tablename__ == "governance_suggestions"
    assert (
        governance.GovernanceAmbiguousAlias.__tablename__
        == "governance_ambiguous_aliases"
    )
    assert (
        governance.GovernanceAmbiguousAliasCandidate.__tablename__
        == "governance_ambiguous_alias_candidates"
    )
    assert (
        governance.GovernanceConflictReview.__tablename__
        == "governance_conflict_reviews"
    )
    assert (
        governance.GovernanceStopListEntry.__tablename__
        == "governance_stop_list_entries"
    )
    assert (
        governance.GovernanceGlobalStopListEntry.__tablename__
        == "governance_global_stop_list_entries"
    )
    assert governance.USER_ROLES == ("admin", "moderator", "contributor")
    assert governance.API_TOKEN_OWNER_TYPES == ("personal", "service_account")
    assert governance.SUGGESTION_STATUSES == ("pending", "approved", "rejected")
    assert governance.SUGGESTION_TYPES == ("alias", "canonical_term")
    assert governance.PROPOSAL_SOURCE_TYPES == (
        "human",
        "agent",
        "cli",
        "api",
        "job",
        "import",
    )
    assert governance.CONFLICT_SEVERITIES == ("low", "medium", "high")
    assert governance.CONFLICT_REVIEW_STATUSES == ("open", "ignored", "resolved")
    assert governance.AMBIGUOUS_ALIAS_STATUSES == ("open", "resolved", "ignored")
    assert governance.AMBIGUOUS_ALIAS_CANDIDATE_STATUSES == (
        "candidate",
        "preferred",
        "rejected",
    )
    assert governance.AMBIGUOUS_ALIAS_CANDIDATE_SOURCES == (
        "manual",
        "active_alias",
        "suggestion",
        "conflict",
        "agent",
        "import",
    )
    assert governance.BINDING_POLICY_STATUSES == ("active", "disabled")
    assert governance.STOP_LIST_TARGETS == ("alias", "canonical", "both")
    assert governance.ELASTICSEARCH_BINDING_MODES == ("dry_run", "write")
    assert governance.ELASTICSEARCH_BINDING_WRITE_STRATEGIES == (
        "in_place",
        "reindex_alias_swap",
    )
    assert governance.ELASTICSEARCH_ENRICHMENT_JOB_STATUSES == (
        "queued",
        "running",
        "cancel_requested",
        "cancelled",
        "succeeded",
        "failed",
    )
    assert governance.ELASTICSEARCH_BINDING_PROVIDERS == ("elasticsearch",)
    assert governance.AGENT_RUN_STATUSES == (
        "queued",
        "running",
        "succeeded",
        "failed",
        "cancelled",
        "needs_review",
    )
    assert governance.AGENT_RUN_TRIGGER_TYPES == (
        "manual",
        "scheduled",
        "api",
        "worker",
        "test",
    )
    assert governance.AGENT_CANDIDATE_OBSERVATION_STATUSES == (
        "discovered",
        "queued_for_review",
        "reviewed",
        "rejected",
        "needs_evidence",
        "error",
    )
    assert governance.AGENT_LLM_REVIEW_STATUSES == (
        "proposed",
        "rejected",
        "needs_evidence",
        "error",
    )
    assert governance.AGENT_PROPOSAL_ATTEMPT_STATUSES == (
        "validation_passed",
        "validation_warning",
        "validation_blocked",
        "submitted",
        "created",
        "idempotent_existing_alias",
        "manual_review_required",
        "error",
    )
    assert governance.normalize_value(" K8S ") == "k8s"
    assert governance.normalize_profile_name("Default IT") == "default_it"
    assert governance.create_profile is not None
    assert governance.add_term is not None
    assert governance.add_alias is not None
    assert governance.normalize_tag_values(["Infra", " infra "]) == ["infra"]
    assert governance.set_term_tags is not None
    assert governance.build_snapshot is not None
    assert governance.export_snapshot is not None
