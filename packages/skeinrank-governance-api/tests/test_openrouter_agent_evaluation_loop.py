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
    return {
        "schema_version": "skeinrank.agent_llm_review_report.v1",
        "candidate_summary": {
            "candidates_discovered": 3,
            "candidates_in_review_queue": 3,
            "candidates_with_evidence": 3,
            "total_evidence_windows": 5,
            "top_surfaces": ["pg", "k8s", "kube"],
        },
        "llm_review_summary": {
            "candidates_sent_to_model": 3,
            "proposals_prepared": 1,
            "actions": {"propose": 1, "reject": 1, "needs_evidence": 1},
            "live_openrouter_calls": 3,
            "cache_hits": 0,
            "skipped_due_to_budget": 0,
        },
        "budget_cache_summary": {
            "cache_hits": 0,
            "cache_misses": 3,
            "usage": {
                "prompt_tokens": 300,
                "completion_tokens": 90,
                "total_tokens": 390,
                "estimated_cost_usd": 0.00123,
            },
        },
        "proposals_submitted": 0,
        "reviewed_items": [
            {
                "candidate_alias": "pg",
                "judgment": {
                    "action": "propose",
                    "confidence": 0.91,
                    "reason": "Evidence links pg to Postgres.",
                    "risk_flags": [],
                },
                "proposal_ready_for_validation": True,
                "proposal_payload": {
                    "alias_value": "pg",
                    "canonical_value": "postgresql",
                },
                "cache": {"hit": False},
            },
            {
                "candidate_alias": "k8s",
                "judgment": {
                    "action": "reject",
                    "confidence": 0.42,
                    "reason": "Synthetic reject for evaluation.",
                    "risk_flags": ["weak_evidence"],
                },
                "proposal_ready_for_validation": False,
                "proposal_payload": None,
                "cache": {"hit": False},
            },
            {
                "candidate_alias": "kube",
                "judgment": {
                    "action": "needs_evidence",
                    "confidence": 0.61,
                    "reason": "Need more context.",
                    "risk_flags": [],
                },
                "proposal_ready_for_validation": False,
                "proposal_payload": None,
                "cache": {"hit": False},
            },
        ],
    }


def test_40n_files_exist_and_docs_are_linked() -> None:
    assert (AGENT_DIR / "agent_evaluation.py").exists()
    assert (AGENT_DIR / "evaluation_outcomes.example.jsonl").exists()

    readme = (AGENT_DIR / "README.md").read_text(encoding="utf-8")
    for fragment in (
        "Patch 40N adds an offline evaluation report",
        "--run-evaluation-report",
        "--llm-review-report",
        "skeinrank.agent_evaluation_report.v1",
    ):
        assert fragment in readme

    for path in (
        REPO_ROOT / "docs" / "README.md",
        REPO_ROOT / "docs" / "api" / "governance-api.md",
        REPO_ROOT / "packages" / "skeinrank-governance-api" / "README.md",
        REPO_ROOT / "docs" / "guides" / "openrouter-agent.md",
    ):
        content = path.read_text(encoding="utf-8")
        assert "Patch 40N" in content, path
        assert "--run-evaluation-report" in content, path


def test_evaluation_report_cli_is_offline_and_uses_sample_outcomes() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(AGENT_DIR / "run_alias_scout.py"),
            "--config",
            str(AGENT_DIR / "agent_config.example.json"),
            "--run-evaluation-report",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    report = json.loads(result.stdout)
    assert report["schema_version"] == "skeinrank.agent_evaluation_report.v1"
    assert report["evaluation_mode"] == "demo_dry_run"
    assert report["openrouter_calls"] is False
    assert report["skeinrank_api_calls"] is False
    assert report["candidate_summary"]["top_surfaces"] == ["pg", "k8s", "kube"]
    assert report["evidence_quality"]["evidence_coverage"] == 1.0
    assert report["outcome_summary"]["counts"]["accepted"] == 3
    assert report["outcome_summary"]["counts"]["noisy"] == 3
    assert report["before_after_snapshot_evaluation"]["enabled"] is False


def test_evaluation_report_accepts_saved_llm_review_report(tmp_path: Path) -> None:
    llm_report_path = tmp_path / "llm-report.json"
    llm_report_path.write_text(json.dumps(_sample_llm_report()), encoding="utf-8")
    outcomes_path = tmp_path / "outcomes.jsonl"
    outcomes_path.write_text(
        "\n".join(
            [
                json.dumps({"candidate_alias": "pg", "outcome": "accepted"}),
                json.dumps({"candidate_alias": "k8s", "outcome": "rejected"}),
                json.dumps({"candidate_alias": "kube", "outcome": "blocked"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(AGENT_DIR / "run_alias_scout.py"),
            "--config",
            str(AGENT_DIR / "agent_config.example.json"),
            "--llm-review-report",
            str(llm_report_path),
            "--evaluation-outcomes",
            str(outcomes_path),
            "--run-evaluation-report",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    report = json.loads(result.stdout)
    assert report["evaluation_mode"] == "llm_review"
    assert report["llm_quality"]["actions"] == {
        "needs_evidence": 1,
        "propose": 1,
        "reject": 1,
    }
    assert report["llm_quality"]["proposal_ready_for_validation"] == 1
    assert report["proposal_quality"]["proposals_prepared"] == 1
    assert report["proposal_quality"]["accepted_outcomes"] == 1
    assert report["proposal_quality"]["rejected_outcomes"] == 1
    assert report["outcome_summary"]["counts"]["blocked"] == 1
    assert report["quality_gate"]["status"] == "blocked"
    assert report["cost_summary"]["total_tokens"] == 390


def test_agent_evaluation_module_validates_outcome_values(tmp_path: Path) -> None:
    module = _load_module("agent_evaluation_40n", AGENT_DIR / "agent_evaluation.py")
    path = tmp_path / "bad-outcomes.jsonl"
    path.write_text(
        json.dumps({"candidate_alias": "pg", "outcome": "maybe"}) + "\n",
        encoding="utf-8",
    )
    try:
        module.load_evaluation_outcomes(path)
    except ValueError as exc:
        assert "Invalid outcome" in str(exc)
    else:  # pragma: no cover - assertion path only.
        raise AssertionError("invalid outcome should raise ValueError")


def test_write_evaluation_report_cli(tmp_path: Path) -> None:
    output = tmp_path / "evaluation-report.json"
    subprocess.run(
        [
            sys.executable,
            str(AGENT_DIR / "run_alias_scout.py"),
            "--config",
            str(AGENT_DIR / "agent_config.example.json"),
            "--write-evaluation-report",
            str(output),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["schema_version"] == "skeinrank.agent_evaluation_report.v1"
    assert report["safety"]["evaluation_is_offline"] is True
