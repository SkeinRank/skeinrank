from __future__ import annotations

import json
from pathlib import Path

from skeinrank_governance_api.backup_restore_drill import (
    DRILL_SCHEMA_VERSION,
    build_drill_plan,
    inspect_drill_report,
    main,
    run_backup_restore_drill,
)

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_backup_restore_drill_plan_is_safe_and_non_mutating(tmp_path: Path) -> None:
    plan = build_drill_plan(work_dir=tmp_path / "drill")

    assert plan["schema_version"] == DRILL_SCHEMA_VERSION
    assert plan["status"] == "planned"
    assert plan["safety"]["openrouter_calls"] is False
    assert plan["safety"]["elasticsearch_calls"] is False
    assert plan["safety"]["live_database_used"] is False
    assert "restore dry-run validation" in " ".join(plan["steps"])


def test_backup_restore_drill_runs_and_verifies_restored_data(tmp_path: Path) -> None:
    report = run_backup_restore_drill(work_dir=tmp_path / "drill", reset=True)

    assert report["schema_version"] == DRILL_SCHEMA_VERSION
    assert report["status"] == "verified"
    assert report["restore"]["dry_run"]["status"] == "validated"
    assert report["restore"]["restored"]["status"] == "restored"
    assert report["verification"]["counts_match"] is True
    assert report["verification"]["representative_values_match"] is True

    target = report["verification"]["target"]
    assert target["counts"]["profiles"] == 1
    assert target["counts"]["terms"] == 1
    assert target["counts"]["aliases"] == 1
    assert target["counts"]["bindings"] == 1
    assert target["counts"]["proposals"] == 1
    assert target["counts"]["snapshots"] == 1
    assert target["counts"]["agent_runs"] == 1
    assert target["representative_values"]["canonical_value"] == "kubernetes"
    assert target["representative_values"]["alias_value"] == "k8s"
    assert target["representative_values"]["proposal_alias"] == "kube"
    assert (
        target["representative_values"]["agent_run_id"]
        == "backup-restore-drill-run-001"
    )

    report_file = Path(report["outputs"]["report_file"])
    assert report_file.exists()
    saved = json.loads(report_file.read_text(encoding="utf-8"))
    assert saved["status"] == "verified"


def test_backup_restore_drill_inspect_returns_compact_summary(tmp_path: Path) -> None:
    report = run_backup_restore_drill(work_dir=tmp_path / "drill", reset=True)

    summary = inspect_drill_report(Path(report["outputs"]["report_file"]))

    assert summary["schema_version"] == DRILL_SCHEMA_VERSION
    assert summary["status"] == "verified"
    assert summary["verification"]["counts_match"] is True
    assert summary["backup_total_rows"] >= 7


def test_backup_restore_drill_cli_plan_and_run(tmp_path: Path, capsys) -> None:
    work_dir = tmp_path / "cli-drill"

    assert main(["plan", "--work-dir", str(work_dir)]) == 0
    plan_output = json.loads(capsys.readouterr().out)
    assert plan_output["status"] == "planned"

    assert main(["run", "--work-dir", str(work_dir), "--reset"]) == 0
    run_output = json.loads(capsys.readouterr().out)
    assert run_output["status"] == "verified"

    report_file = work_dir / "backup-restore-drill-report.json"
    assert main(["inspect", "--file", str(report_file)]) == 0
    inspect_output = json.loads(capsys.readouterr().out)
    assert inspect_output["status"] == "verified"


def test_backup_restore_drill_makefile_targets_are_documented() -> None:
    makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
    guide = (
        REPO_ROOT / "docs/deployment/backup-restore-verified-scenario.md"
    ).read_text(encoding="utf-8")
    package_readme = (
        REPO_ROOT / "packages/skeinrank-governance-api/README.md"
    ).read_text(encoding="utf-8")

    for target in (
        "backup-restore-drill-plan",
        "backup-restore-drill-run",
        "backup-restore-drill-inspect",
        "backup-restore-drill-clean",
    ):
        assert f"{target}:" in makefile
        assert f"make {target}" in guide or target == "backup-restore-drill-clean"

    assert "skeinrank-governance-backup-drill" in package_readme
