from __future__ import annotations

from fastapi.testclient import TestClient
from skeinrank_governance import (
    create_all,
    create_governance_engine,
    create_session_factory,
)
from skeinrank_governance.models import (
    GovernanceGlobalStopListEntry,
    TerminologyProfile,
)
from skeinrank_governance_api import GovernanceApiConfig, create_app
from skeinrank_governance_api.proposal_validation import (
    PROPOSAL_CHECK_NAMES,
    PROPOSAL_VALIDATION_SCHEMA_VERSION,
    build_proposal_validation_summary,
)


def _client(tmp_path) -> TestClient:
    app = create_app(
        GovernanceApiConfig(
            database_url=f"sqlite:///{tmp_path / 'governance.db'}",
            create_tables_on_startup=True,
            service_version="test",
        )
    )
    return TestClient(app)


def test_proposal_validation_registry_exposes_expected_checks():
    assert PROPOSAL_CHECK_NAMES == (
        "shape",
        "canonical_state",
        "alias_state",
        "stop_list",
        "noise",
        "confidence",
        "idempotency_key",
        "agent_payload",
        "prompt_like_instruction",
    )


def test_proposal_validation_summary_is_stored_when_not_provided(tmp_path):
    client = _client(tmp_path)
    client.post("/v1/governance/profiles", json={"name": "default_it"})
    client.post(
        "/v1/governance/profiles/default_it/terms",
        json={"canonical_value": "kubernetes", "slot": "tool"},
    )

    response = client.post(
        "/v1/governance/profiles/default_it/suggestions",
        json={
            "canonical_value": "kubernetes",
            "alias_value": "kube",
            "slot": "tool",
            "confidence": 0.84,
            "proposal_source_type": "agent",
            "proposal_source_name": "search-log-scout",
            "idempotency_key": "search-log-scout:default_it:kube",
            "source_payload": {"query_count": 42},
        },
    )

    assert response.status_code == 201
    summary = response.json()["validation_summary"]
    assert summary["schema_version"] == PROPOSAL_VALIDATION_SCHEMA_VERSION
    assert summary["status"] == "passed"
    assert summary["checks"]["canonical_state"]["status"] == "passed"
    assert summary["checks"]["alias_state"]["status"] == "passed"
    assert summary["checks"]["idempotency_key"]["status"] == "passed"
    assert summary["checks"]["agent_payload"]["status"] == "passed"
    assert summary["apply_policy"]["schema_version"] == "skeinrank.apply_policy.v1"
    assert summary["risk_level"] == "medium"


def test_proposal_validation_flags_duplicate_alias_without_blocking_creation(tmp_path):
    client = _client(tmp_path)
    client.post("/v1/governance/profiles", json={"name": "default_it"})
    client.post(
        "/v1/governance/profiles/default_it/terms",
        json={"canonical_value": "kubernetes", "slot": "tool"},
    )
    client.post(
        "/v1/governance/profiles/default_it/terms/kubernetes/aliases",
        json={"alias_value": "kube"},
    )

    response = client.post(
        "/v1/governance/profiles/default_it/suggestions",
        json={
            "canonical_value": "postgresql",
            "alias_value": "Kube",
            "slot": "database",
            "confidence": 0.2,
            "proposal_source_type": "agent",
        },
    )

    assert response.status_code == 201
    summary = response.json()["validation_summary"]
    assert summary["status"] == "blocked"
    assert summary["checks"]["alias_state"]["status"] == "blocked"
    assert summary["checks"]["confidence"]["status"] == "warning"
    assert summary["checks"]["agent_payload"]["status"] == "warning"


def test_proposal_validation_preserves_external_validation_summary(tmp_path):
    client = _client(tmp_path)
    client.post("/v1/governance/profiles", json={"name": "default_it"})
    client.post(
        "/v1/governance/profiles/default_it/terms",
        json={"canonical_value": "kubernetes", "slot": "tool"},
    )
    external_summary = {"checks": {"duplicate_alias": "passed"}}

    response = client.post(
        "/v1/governance/profiles/default_it/suggestions",
        json={
            "canonical_value": "kubernetes",
            "alias_value": "kube",
            "slot": "tool",
            "validation_summary": external_summary,
        },
    )

    assert response.status_code == 201
    summary = response.json()["validation_summary"]
    assert summary["checks"] == external_summary["checks"]
    assert summary["risk_level"] == "medium"
    assert summary["apply_policy"]["schema_version"] == "skeinrank.apply_policy.v1"
    assert response.json()["risk_level"] == "medium"


def test_proposal_validation_summary_can_report_stop_list_blocks():
    engine = create_governance_engine("sqlite+pysqlite:///:memory:")
    create_all(engine)
    session_factory = create_session_factory(engine)

    with session_factory() as session:
        profile = TerminologyProfile(name="default_it")
        session.add(profile)
        session.add(
            GovernanceGlobalStopListEntry(
                value="tmp",
                target="alias",
                reason="too generic",
            )
        )
        session.commit()
        session.refresh(profile)
        summary = build_proposal_validation_summary(
            session,
            profile,
            suggestion_type="alias",
            canonical_value="kubernetes",
            alias_value="tmp",
            slot="tool",
            confidence=0.8,
        )

    assert summary["status"] == "blocked"
    assert summary["checks"]["stop_list"]["status"] == "blocked"
    assert summary["checks"]["stop_list"]["details"]["reason"] == "too generic"
