from __future__ import annotations

import skeinrank_governance as governance


def test_public_api_exports_governance_models_and_helpers():
    assert governance.TerminologyProfile.__tablename__ == "terminology_profiles"
    assert governance.CanonicalTerm.__tablename__ == "canonical_terms"
    assert governance.TermAlias.__tablename__ == "term_aliases"
    assert governance.ProfileSnapshot.__tablename__ == "profile_snapshots"
    assert governance.AuditEvent.__tablename__ == "audit_events"
    assert governance.normalize_value(" K8S ") == "k8s"
    assert governance.create_profile is not None
    assert governance.add_term is not None
    assert governance.add_alias is not None
    assert governance.build_snapshot is not None
    assert governance.export_snapshot is not None
