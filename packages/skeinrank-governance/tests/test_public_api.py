from __future__ import annotations

import skeinrank_governance as governance


def test_public_api_exports_governance_models_and_helpers():
    assert governance.TerminologyProfile.__tablename__ == "terminology_profiles"
    assert governance.CanonicalTerm.__tablename__ == "canonical_terms"
    assert governance.TermAlias.__tablename__ == "term_aliases"
    assert governance.ProfileSnapshot.__tablename__ == "profile_snapshots"
    assert governance.AuditEvent.__tablename__ == "audit_events"
    assert governance.GovernanceUser.__tablename__ == "governance_users"
    assert governance.GovernanceAuthToken.__tablename__ == "governance_auth_tokens"
    assert governance.ElasticsearchBinding.__tablename__ == "elasticsearch_bindings"
    assert (
        governance.ElasticsearchEnrichmentJob.__tablename__
        == "elasticsearch_enrichment_jobs"
    )
    assert governance.GovernanceSuggestion.__tablename__ == "governance_suggestions"
    assert (
        governance.GovernanceStopListEntry.__tablename__
        == "governance_stop_list_entries"
    )
    assert (
        governance.GovernanceGlobalStopListEntry.__tablename__
        == "governance_global_stop_list_entries"
    )
    assert governance.USER_ROLES == ("admin", "moderator", "contributor")
    assert governance.SUGGESTION_STATUSES == ("pending", "approved", "rejected")
    assert governance.SUGGESTION_TYPES == ("alias", "canonical_term")
    assert governance.STOP_LIST_TARGETS == ("alias", "canonical", "both")
    assert governance.ELASTICSEARCH_BINDING_MODES == ("dry_run", "write")
    assert governance.ELASTICSEARCH_BINDING_WRITE_STRATEGIES == (
        "in_place",
        "reindex_alias_swap",
    )
    assert governance.ELASTICSEARCH_ENRICHMENT_JOB_STATUSES == (
        "queued",
        "running",
        "succeeded",
        "failed",
    )
    assert governance.ELASTICSEARCH_BINDING_PROVIDERS == ("elasticsearch",)
    assert governance.normalize_value(" K8S ") == "k8s"
    assert governance.normalize_profile_name("Default IT") == "default_it"
    assert governance.create_profile is not None
    assert governance.add_term is not None
    assert governance.add_alias is not None
    assert governance.build_snapshot is not None
    assert governance.export_snapshot is not None
