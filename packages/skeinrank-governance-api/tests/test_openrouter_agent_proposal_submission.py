from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
AGENT_DIR = REPO_ROOT / "examples" / "agents" / "openrouter_alias_scout"


def _load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _sample_llm_report() -> dict[str, Any]:
    payload = {
        "alias_value": "k8s",
        "canonical_value": "kubernetes",
        "slot": "technology",
        "confidence": 0.9,
        "context": "Container orchestration platform used in infra incidents.",
        "profile_name": "infra_incidents",
        "proposal_source_name": "openrouter-alias-scout",
        "idempotency_key": "openrouter-alias-scout:profile:infra_incidents:candidate:k8s",
        "source_payload": {
            "candidate_alias": "k8s",
            "possible_canonical": "kubernetes",
        },
    }
    return {
        "schema_version": "skeinrank.agent_llm_review_report.v1",
        "reviewed_items": [
            {
                "candidate_alias": "k8s",
                "proposal_ready_for_validation": True,
                "proposal_payload": payload,
            },
            {
                "candidate_alias": "pg",
                "proposal_ready_for_validation": False,
                "proposal_payload": None,
            },
        ],
    }


class FakeProposalClient:
    def __init__(
        self,
        *,
        validation_status: str = "passed",
        validation_summary: dict[str, Any] | None = None,
    ) -> None:
        self.validation_status = validation_status
        self.validation_summary = validation_summary
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def validate_alias(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("validate", kwargs))
        return {
            "canonical_value": kwargs["canonical_value"],
            "alias_value": kwargs["alias_value"],
            "slot": kwargs["slot"],
            "validation_summary": self.validation_summary
            or {"status": self.validation_status},
        }

    def suggest_alias(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("suggest", kwargs))
        return {
            "created": True,
            "suggestion": {"id": 123, "status": "pending"},
            "validation_summary": {"status": self.validation_status},
        }


def test_proposal_submission_files_are_present_and_documented() -> None:
    assert (AGENT_DIR / "proposal_submission.py").exists()
    readme = (AGENT_DIR / "README.md").read_text(encoding="utf-8")
    docs = (REPO_ROOT / "docs" / "guides" / "openrouter-agent.md").read_text(
        encoding="utf-8"
    )
    for content in (readme, docs):
        assert "--validate-ready-proposals" in content
        assert "Validation statuses are classified" in content
        assert "--validate-ready-proposals" in content
        assert "--submit-ready-proposals" in content


def test_submission_plan_counts_ready_payloads() -> None:
    module = _load_module(
        "agent_proposal_submission_plan", AGENT_DIR / "proposal_submission.py"
    )
    plan = module.build_proposal_submission_plan(_sample_llm_report())

    assert plan["schema_version"] == "skeinrank.agent_proposal_submission_plan.v1"
    assert plan["eligible_proposals"] == 1
    assert plan["candidate_aliases"] == ["k8s"]
    assert plan["will_validate_aliases"] is True
    assert plan["will_submit_aliases"] is False


def test_validate_only_calls_validate_alias_without_submission() -> None:
    module = _load_module(
        "agent_proposal_submission_validate", AGENT_DIR / "proposal_submission.py"
    )
    client = FakeProposalClient()

    report = module.validate_and_optionally_submit_proposals(
        _sample_llm_report(), client=client
    )

    assert report["schema_version"] == "skeinrank.agent_proposal_submission_report.v1"
    assert report["summary"]["validated"] == 1
    assert report["summary"]["validation_passed"] == 1
    assert report["summary"]["submitted"] == 0
    assert [call[0] for call in client.calls] == ["validate"]


def test_submit_requires_explicit_config_and_security_policy() -> None:
    module = _load_module(
        "agent_proposal_submission_blocked", AGENT_DIR / "proposal_submission.py"
    )
    client = FakeProposalClient()

    with pytest.raises(RuntimeError, match="submit_enabled=false"):
        module.validate_and_optionally_submit_proposals(
            _sample_llm_report(), client=client, submit=True
        )


def test_submit_calls_validate_then_suggest_when_policy_allows() -> None:
    module = _load_module(
        "agent_proposal_submission_live", AGENT_DIR / "proposal_submission.py"
    )
    security = _load_module(
        "agent_security_for_submission", AGENT_DIR / "security_profile.py"
    )
    client = FakeProposalClient()

    report = module.validate_and_optionally_submit_proposals(
        _sample_llm_report(),
        client=client,
        submission_config=module.ProposalSubmissionConfig(submit_enabled=True),
        security_config=security.SecurityProfileConfig(allow_proposal_submission=True),
        submit=True,
    )

    assert [call[0] for call in client.calls] == ["validate", "suggest"]
    assert report["summary"]["submitted"] == 1
    assert report["summary"]["created"] == 1
    assert report["results"][0]["status"] == "submitted"


def test_generic_warning_routes_to_manual_review() -> None:
    module = _load_module(
        "agent_proposal_submission_warning", AGENT_DIR / "proposal_submission.py"
    )
    security = _load_module(
        "agent_security_for_submission_warning", AGENT_DIR / "security_profile.py"
    )
    client = FakeProposalClient(validation_status="warning")

    report = module.validate_and_optionally_submit_proposals(
        _sample_llm_report(),
        client=client,
        submission_config=module.ProposalSubmissionConfig(submit_enabled=True),
        security_config=security.SecurityProfileConfig(allow_proposal_submission=True),
        submit=True,
    )

    assert [call[0] for call in client.calls] == ["validate"]
    assert report["summary"]["manual_review_required"] == 1
    assert report["summary"]["submitted"] == 0
    assert report["results"][0]["status"] == "manual_review_required"


def test_existing_alias_warning_is_classified_as_idempotent_noop() -> None:
    module = _load_module(
        "agent_proposal_submission_idempotent", AGENT_DIR / "proposal_submission.py"
    )
    client = FakeProposalClient(
        validation_summary={
            "status": "warning",
            "checks": {
                "alias_state": {
                    "status": "warning",
                    "severity": "warning",
                    "message": "Alias already maps to the requested canonical term.",
                    "details": {"existing_canonical": "kubernetes"},
                },
                "canonical_state": {"status": "passed"},
            },
            "counts": {"passed": 1, "warning": 1, "blocked": 0},
        }
    )

    report = module.validate_and_optionally_submit_proposals(
        _sample_llm_report(), client=client
    )

    assert [call[0] for call in client.calls] == ["validate"]
    assert report["results"][0]["status"] == "idempotent_existing_alias"
    assert report["results"][0]["validation_decision"]["counts_as_idempotent"] is True
    assert report["summary"]["idempotent_existing_aliases"] == 1
    assert report["summary"]["validation_passed"] == 0
    assert report["summary"]["submitted"] == 0


def test_slot_mismatch_warning_requires_manual_review() -> None:
    module = _load_module(
        "agent_proposal_submission_slot_mismatch", AGENT_DIR / "proposal_submission.py"
    )
    client = FakeProposalClient(
        validation_summary={
            "status": "warning",
            "checks": {
                "alias_state": {
                    "status": "warning",
                    "message": "Alias already maps to the requested canonical term.",
                    "details": {"existing_canonical": "kubernetes"},
                },
                "canonical_state": {
                    "status": "warning",
                    "message": "Proposal slot differs from the existing canonical term slot.",
                    "details": {
                        "existing_slot": "TOOL",
                        "proposal_slot": "TECHNOLOGY",
                    },
                },
            },
            "counts": {"passed": 0, "warning": 2, "blocked": 0},
        }
    )

    report = module.validate_and_optionally_submit_proposals(
        _sample_llm_report(), client=client
    )

    assert report["results"][0]["status"] == "manual_review_required"
    assert report["results"][0]["validation_decision"]["reason"] == (
        "slot_mismatch_warning"
    )
    assert report["summary"]["manual_review_required"] == 1


def test_blocked_validation_is_never_submitted() -> None:
    module = _load_module(
        "agent_proposal_submission_blocked_status", AGENT_DIR / "proposal_submission.py"
    )
    client = FakeProposalClient(
        validation_summary={
            "status": "blocked",
            "checks": {
                "stop_list": {
                    "status": "blocked",
                    "severity": "blocked",
                    "message": "Proposal value is blocked by a stop list.",
                }
            },
            "counts": {"passed": 0, "warning": 0, "blocked": 1},
        }
    )

    report = module.validate_and_optionally_submit_proposals(
        _sample_llm_report(), client=client
    )

    assert report["results"][0]["status"] == "blocked"
    assert report["summary"]["blocked"] == 1
    assert report["summary"]["submitted"] == 0


def test_cli_print_proposal_submission_plan(tmp_path: Path) -> None:
    report_path = tmp_path / "llm-report.json"
    report_path.write_text(json.dumps(_sample_llm_report()), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(AGENT_DIR / "run_alias_scout.py"),
            "--config",
            str(AGENT_DIR / "agent_config.example.json"),
            "--llm-review-report",
            str(report_path),
            "--print-proposal-submission-plan",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)

    assert payload["schema_version"] == "skeinrank.agent_proposal_submission_plan.v1"
    assert payload["eligible_proposals"] == 1
    assert payload["skeinrank_api_calls"] is False
