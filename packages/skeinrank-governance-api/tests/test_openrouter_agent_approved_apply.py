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


def _sample_inbox() -> dict[str, Any]:
    return {
        "schema_version": "skeinrank.agent_proposal_inbox.v1",
        "items": [
            {
                "candidate_alias": "pgx",
                "canonical_value": "postgresql",
                "slot": "database",
                "confidence": 0.91,
                "idempotency_key": "key-pgx",
                "review_status": "approved",
                "review_decision": {
                    "candidate_alias": "pgx",
                    "action": "approve",
                    "reviewer": "knowledge-manager",
                },
                "evidence_preview": [
                    {"source_id": "doc-1", "text": "pgx timeout runbook"}
                ],
                "llm_judgment": {"action": "propose", "confidence": 0.91},
            },
            {
                "candidate_alias": "k8s",
                "canonical_value": "kubernetes",
                "review_status": "idempotent_noop",
                "idempotency_key": "key-k8s",
            },
            {
                "candidate_alias": "kube",
                "canonical_value": "kubernetes",
                "review_status": "pending_review",
                "idempotency_key": "key-kube",
            },
        ],
    }


def test_approved_apply_files_are_present_and_documented() -> None:
    assert (AGENT_DIR / "approved_apply.py").exists()
    readme = (AGENT_DIR / "README.md").read_text(encoding="utf-8")
    guide = (REPO_ROOT / "docs" / "guides" / "openrouter-agent.md").read_text(
        encoding="utf-8"
    )
    for content in (readme, guide):
        assert "Patch 41H" in content
        assert "--print-approved-apply-plan" in content
        assert "--build-approved-apply-plan" in content
        assert "--run-snapshot-evaluation" in content


def test_approved_apply_plan_is_offline_and_selects_only_approved_items() -> None:
    module = _load_module("agent_approved_apply", AGENT_DIR / "approved_apply.py")

    report = module.build_approved_proposals_apply_plan(_sample_inbox())

    assert report["schema_version"] == "skeinrank.agent_approved_apply_plan.v1"
    assert report["skeinrank_api_calls"] is False
    assert report["runtime_mutation_enabled"] is False
    assert report["summary"]["approved_operations"] == 1
    assert report["summary"]["skipped_items"] == 2
    assert report["operations"][0]["candidate_alias"] == "pgx"
    assert report["operations"][0]["status"] == "ready_for_governed_apply"


def test_snapshot_evaluation_without_snapshots_is_explicit_placeholder() -> None:
    module = _load_module(
        "agent_snapshot_eval_placeholder", AGENT_DIR / "approved_apply.py"
    )
    apply_plan = module.build_approved_proposals_apply_plan(_sample_inbox())

    report = module.build_snapshot_evaluation_report(apply_plan=apply_plan)

    assert report["schema_version"] == "skeinrank.agent_snapshot_evaluation_report.v1"
    assert report["snapshot_eval_enabled"] is False
    assert report["approved_operations"] == 1
    assert report["safety"]["agent_may_mutate_runtime"] is False


def test_snapshot_evaluation_reports_added_alias_and_coverage() -> None:
    module = _load_module("agent_snapshot_eval", AGENT_DIR / "approved_apply.py")
    apply_plan = module.build_approved_proposals_apply_plan(_sample_inbox())
    before = {
        "terms": [
            {
                "canonical_value": "postgresql",
                "slot": "database",
                "aliases": ["pg", "postgres"],
            }
        ]
    }
    after = {
        "terms": [
            {
                "canonical_value": "postgresql",
                "slot": "database",
                "aliases": ["pg", "postgres", "pgx"],
            }
        ]
    }

    report = module.build_snapshot_evaluation_report(
        apply_plan=apply_plan, before_snapshot=before, after_snapshot=after
    )

    assert report["snapshot_eval_enabled"] is True
    assert report["alias_diff"]["counts"]["added"] == 1
    assert report["approved_operation_coverage"]["coverage_rate"] == 1.0
    assert report["quality_gate"]["status"] == "ready_for_publish_review"


def test_cli_print_approved_apply_plan_outputs_json() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(AGENT_DIR / "run_alias_scout.py"),
            "--config",
            str(AGENT_DIR / "agent_config.example.json"),
            "--print-approved-apply-plan",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)

    assert payload["schema_version"] == "skeinrank.agent_approved_apply_plan.v1"
    assert payload["skeinrank_api_calls"] is False
    assert payload["snapshot_publish_enabled"] is False


def test_cli_write_approved_apply_plan(tmp_path: Path) -> None:
    inbox_path = tmp_path / "inbox.json"
    output_path = tmp_path / "apply-plan.json"
    inbox_path.write_text(json.dumps(_sample_inbox()), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(AGENT_DIR / "run_alias_scout.py"),
            "--config",
            str(AGENT_DIR / "agent_config.example.json"),
            "--proposal-inbox-report",
            str(inbox_path),
            "--write-approved-apply-plan",
            str(output_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout == ""
    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert payload["schema_version"] == "skeinrank.agent_approved_apply_plan.v1"
    assert payload["summary"]["approved_operations"] == 1


def test_cli_snapshot_evaluation_with_artifacts(tmp_path: Path) -> None:
    module = _load_module(
        "agent_snapshot_eval_cli_seed", AGENT_DIR / "approved_apply.py"
    )
    apply_plan = module.build_approved_proposals_apply_plan(_sample_inbox())
    apply_path = tmp_path / "apply-plan.json"
    before_path = tmp_path / "before.json"
    after_path = tmp_path / "after.json"
    output_path = tmp_path / "eval.json"
    apply_path.write_text(json.dumps(apply_plan), encoding="utf-8")
    before_path.write_text(
        json.dumps(
            {"aliases": {"pg": {"canonical": "postgresql", "slot": "database"}}}
        ),
        encoding="utf-8",
    )
    after_path.write_text(
        json.dumps(
            {
                "aliases": {
                    "pg": {"canonical": "postgresql", "slot": "database"},
                    "pgx": {"canonical": "postgresql", "slot": "database"},
                }
            }
        ),
        encoding="utf-8",
    )

    subprocess.run(
        [
            sys.executable,
            str(AGENT_DIR / "run_alias_scout.py"),
            "--config",
            str(AGENT_DIR / "agent_config.example.json"),
            "--approved-apply-plan",
            str(apply_path),
            "--before-snapshot",
            str(before_path),
            "--after-snapshot",
            str(after_path),
            "--write-snapshot-evaluation-report",
            str(output_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert payload["schema_version"] == "skeinrank.agent_snapshot_evaluation_report.v1"
    assert payload["snapshot_eval_enabled"] is True
    assert payload["alias_diff"]["counts"]["added"] == 1
