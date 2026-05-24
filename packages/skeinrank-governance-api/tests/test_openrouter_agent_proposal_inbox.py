from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

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
        "profile_name": "infra_incidents",
        "idempotency_key": "key-k8s",
        "source_payload": {
            "candidate_alias": "k8s",
            "known_conflicts": [],
            "evidence_windows": [
                {
                    "source_id": "doc-1",
                    "source_type": "incident",
                    "field": "text",
                    "text": "The k8s rollout was stuck after a bad image tag.",
                }
            ],
        },
    }
    return {
        "schema_version": "skeinrank.agent_llm_review_report.v1",
        "reviewed_items": [
            {
                "candidate_alias": "k8s",
                "idempotency_key": "key-k8s",
                "proposal_ready_for_validation": True,
                "proposal_payload": payload,
                "judgment": {
                    "action": "propose",
                    "confidence": 0.9,
                    "reason": "Strong evidence supports k8s -> kubernetes.",
                },
            }
        ],
    }


def _sample_submission_report() -> dict[str, Any]:
    return {
        "schema_version": "skeinrank.agent_proposal_submission_report.v1",
        "results": [
            {
                "alias_value": "k8s",
                "canonical_value": "kubernetes",
                "slot": "technology",
                "confidence": 0.9,
                "idempotency_key": "key-k8s",
                "status": "manual_review_required",
                "validation_status": "warning",
                "submitted": False,
                "validation_decision": {
                    "category": "manual_review_required",
                    "reason": "slot_mismatch_warning",
                    "requires_manual_review": True,
                    "submit_allowed": False,
                },
            }
        ],
    }


def test_proposal_inbox_files_are_present_and_documented() -> None:
    assert (AGENT_DIR / "proposal_inbox.py").exists()
    assert (AGENT_DIR / "review_decisions.example.jsonl").exists()
    readme = (AGENT_DIR / "README.md").read_text(encoding="utf-8")
    guide = (REPO_ROOT / "docs" / "guides" / "openrouter-agent.md").read_text(
        encoding="utf-8"
    )
    for content in (readme, guide):
        assert "Patch 41G" in content
        assert "--print-proposal-inbox-plan" in content
        assert "--build-proposal-inbox" in content
        assert "--write-proposal-inbox" in content


def test_inbox_plan_is_offline_and_safe() -> None:
    module = _load_module("agent_proposal_inbox_plan", AGENT_DIR / "proposal_inbox.py")
    plan = module.ProposalInboxConfig().to_plan()

    assert plan["schema_version"] == "skeinrank.agent_proposal_inbox_plan.v1"
    assert plan["openrouter_calls"] is False
    assert plan["skeinrank_api_calls"] is False
    assert plan["safety"]["runtime_mutation_enabled"] is False
    assert "approve" in plan["supported_review_actions"]


def test_build_inbox_routes_manual_review_card() -> None:
    module = _load_module(
        "agent_proposal_inbox_report", AGENT_DIR / "proposal_inbox.py"
    )

    report = module.build_proposal_inbox_report(
        llm_review_report=_sample_llm_report(),
        proposal_submission_report=_sample_submission_report(),
    )

    assert report["schema_version"] == "skeinrank.agent_proposal_inbox.v1"
    assert report["summary"]["items_total"] == 1
    assert report["summary"]["pending_review"] == 1
    item = report["items"][0]
    assert item["candidate_alias"] == "k8s"
    assert item["review_status"] == "pending_review"
    assert item["recommended_action"] == "human_review"
    assert item["evidence_preview"][0]["source_id"] == "doc-1"


def test_review_decision_marks_item_as_approved() -> None:
    module = _load_module(
        "agent_proposal_inbox_decision", AGENT_DIR / "proposal_inbox.py"
    )

    report = module.build_proposal_inbox_report(
        llm_review_report=_sample_llm_report(),
        proposal_submission_report=_sample_submission_report(),
        review_decisions=[
            {
                "candidate_alias": "k8s",
                "action": "approve",
                "reviewer": "knowledge-manager",
                "comment": "Accept for governed apply.",
            }
        ],
    )

    assert report["summary"]["approved"] == 1
    assert report["items"][0]["review_status"] == "approved"
    assert report["items"][0]["recommended_action"] == "ready_for_governed_apply"


def test_load_review_decisions_rejects_unknown_action(tmp_path: Path) -> None:
    module = _load_module(
        "agent_proposal_inbox_decisions", AGENT_DIR / "proposal_inbox.py"
    )
    path = tmp_path / "decisions.jsonl"
    path.write_text(
        json.dumps({"candidate_alias": "k8s", "action": "maybe"}) + "\n",
        encoding="utf-8",
    )

    try:
        module.load_review_decisions(path)
    except ValueError as exc:
        assert "Invalid review action" in str(exc)
    else:  # pragma: no cover - assertion clarity.
        raise AssertionError("Expected invalid review action to fail")


def test_cli_print_proposal_inbox_plan_outputs_json() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(AGENT_DIR / "run_alias_scout.py"),
            "--config",
            str(AGENT_DIR / "agent_config.example.json"),
            "--print-proposal-inbox-plan",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)

    assert payload["schema_version"] == "skeinrank.agent_proposal_inbox_plan.v1"
    assert payload["openrouter_calls"] is False
    assert payload["skeinrank_api_calls"] is False


def test_cli_write_proposal_inbox(tmp_path: Path) -> None:
    llm_path = tmp_path / "llm.json"
    submission_path = tmp_path / "submission.json"
    output_path = tmp_path / "inbox.json"
    llm_path.write_text(json.dumps(_sample_llm_report()), encoding="utf-8")
    submission_path.write_text(
        json.dumps(_sample_submission_report()), encoding="utf-8"
    )

    result = subprocess.run(
        [
            sys.executable,
            str(AGENT_DIR / "run_alias_scout.py"),
            "--config",
            str(AGENT_DIR / "agent_config.example.json"),
            "--llm-review-report",
            str(llm_path),
            "--proposal-submission-report",
            str(submission_path),
            "--write-proposal-inbox",
            str(output_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout == ""
    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert payload["schema_version"] == "skeinrank.agent_proposal_inbox.v1"
    assert payload["summary"]["pending_review"] == 1
