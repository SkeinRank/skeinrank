"""Verified backup/restore drill for pilot operators.

The drill uses the existing portable JSON backup implementation against two
local SQLite databases. It is intentionally self-contained so operators can
verify the backup/restore path without touching a live pilot database.
"""

from __future__ import annotations

import argparse
import json
import shutil
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from skeinrank_governance import create_governance_engine, create_session_factory
from skeinrank_governance.models import (
    AgentRun,
    CanonicalTerm,
    ElasticsearchBinding,
    GovernanceSuggestion,
    ProfileSnapshot,
    TermAlias,
    TerminologyProfile,
    TermTag,
    normalize_profile_name,
    normalize_value,
)
from sqlalchemy import func, select
from sqlalchemy.engine import Engine

from .backup_restore import export_backup, inspect_backup_file, restore_backup
from .config import GovernanceApiConfig
from .migrations import upgrade_database

DRILL_SCHEMA_VERSION = "skeinrank.backup_restore_drill.v1"
DEFAULT_DRILL_DIR = Path("examples/pilots/reports/backup-restore-drill")
DEFAULT_PROFILE_NAME = "backup_restore_drill"
DEFAULT_BINDING_NAME = "backup-restore-drill-binding"


@dataclass(frozen=True)
class DrillPaths:
    """Filesystem paths used by the drill."""

    work_dir: Path
    source_db: Path
    target_db: Path
    backup_file: Path
    report_file: Path

    @classmethod
    def from_work_dir(cls, work_dir: Path) -> "DrillPaths":
        return cls(
            work_dir=work_dir,
            source_db=work_dir / "source-governance.db",
            target_db=work_dir / "restored-governance.db",
            backup_file=work_dir / "governance-backup.json",
            report_file=work_dir / "backup-restore-drill-report.json",
        )


def build_drill_plan(
    *, work_dir: Path, profile_name: str = DEFAULT_PROFILE_NAME
) -> dict[str, Any]:
    """Return a non-mutating drill plan."""

    paths = DrillPaths.from_work_dir(work_dir)
    return {
        "schema_version": DRILL_SCHEMA_VERSION,
        "status": "planned",
        "profile_name": profile_name,
        "work_dir": str(paths.work_dir),
        "outputs": {
            "source_db": str(paths.source_db),
            "target_db": str(paths.target_db),
            "backup_file": str(paths.backup_file),
            "report_file": str(paths.report_file),
        },
        "steps": [
            "create migrated source SQLite database",
            "seed profile, term, alias, binding, proposal, snapshot, and agent run",
            "export portable JSON backup",
            "inspect backup metadata",
            "create migrated target SQLite database",
            "run restore dry-run validation",
            "restore with replace/yes into target",
            "verify restored row counts and representative values",
        ],
        "safety": _safety_flags(),
    }


def run_backup_restore_drill(
    *,
    work_dir: Path,
    profile_name: str = DEFAULT_PROFILE_NAME,
    reset: bool = False,
) -> dict[str, Any]:
    """Run an end-to-end backup/restore drill against disposable SQLite DBs."""

    paths = DrillPaths.from_work_dir(work_dir)
    if reset and paths.work_dir.exists():
        shutil.rmtree(paths.work_dir)
    paths.work_dir.mkdir(parents=True, exist_ok=True)

    source_engine, source_config = _migrated_engine(paths.source_db)
    try:
        seed_summary = _seed_drill_data(source_engine, profile_name=profile_name)
        export_payload = export_backup(
            engine=source_engine,
            config=source_config,
            output_path=paths.backup_file,
        )
        source_verify = _verify_database(source_engine, profile_name=profile_name)
    finally:
        source_engine.dispose()

    backup_inspection = inspect_backup_file(paths.backup_file)

    target_engine, target_config = _migrated_engine(paths.target_db)
    try:
        dry_run_report = restore_backup(
            engine=target_engine,
            config=target_config,
            input_path=paths.backup_file,
            dry_run=True,
        )
        restore_report = restore_backup(
            engine=target_engine,
            config=target_config,
            input_path=paths.backup_file,
            replace=True,
            yes=True,
        )
        target_verify = _verify_database(target_engine, profile_name=profile_name)
    finally:
        target_engine.dispose()

    report = {
        "schema_version": DRILL_SCHEMA_VERSION,
        "status": "verified" if target_verify["ok"] else "failed",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "profile_name": profile_name,
        "work_dir": str(paths.work_dir),
        "outputs": {
            "source_db": str(paths.source_db),
            "target_db": str(paths.target_db),
            "backup_file": str(paths.backup_file),
            "report_file": str(paths.report_file),
        },
        "seed": seed_summary,
        "backup": {
            "format_version": export_payload.get("format_version"),
            "tables": len(export_payload.get("tables") or []),
            "total_rows": sum(
                int(table.get("row_count") or 0)
                for table in export_payload.get("tables") or []
            ),
            "inspection": backup_inspection,
        },
        "restore": {
            "dry_run": dry_run_report,
            "restored": restore_report,
        },
        "verification": {
            "source": source_verify,
            "target": target_verify,
            "counts_match": source_verify["counts"] == target_verify["counts"],
            "representative_values_match": source_verify["representative_values"]
            == target_verify["representative_values"],
        },
        "safety": _safety_flags(),
    }
    paths.report_file.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    return report


def inspect_drill_report(path: Path) -> dict[str, Any]:
    """Read a previously generated drill report."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        "schema_version": payload.get("schema_version"),
        "status": payload.get("status"),
        "profile_name": payload.get("profile_name"),
        "outputs": payload.get("outputs", {}),
        "backup_total_rows": payload.get("backup", {}).get("total_rows"),
        "verification": payload.get("verification", {}),
        "safety": payload.get("safety", {}),
    }


def main(argv: Sequence[str] | None = None) -> int:
    """Run the backup/restore drill CLI."""

    parser = argparse.ArgumentParser(
        prog="python -m skeinrank_governance_api.backup_restore_drill",
        description="Run a verified local backup/restore drill for SkeinRank governance data.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan_parser = subparsers.add_parser("plan", help="Print the drill plan.")
    _add_common_args(plan_parser)

    run_parser = subparsers.add_parser("run", help="Run the verified drill.")
    _add_common_args(run_parser)
    run_parser.add_argument(
        "--reset",
        action="store_true",
        help="Remove the existing drill work directory before running.",
    )

    inspect_parser = subparsers.add_parser("inspect", help="Inspect a drill report.")
    inspect_parser.add_argument(
        "--file",
        type=Path,
        default=DEFAULT_DRILL_DIR / "backup-restore-drill-report.json",
        help="Drill report JSON path.",
    )

    args = parser.parse_args(argv)
    if args.command == "plan":
        payload = build_drill_plan(
            work_dir=args.work_dir,
            profile_name=args.profile_name,
        )
    elif args.command == "run":
        payload = run_backup_restore_drill(
            work_dir=args.work_dir,
            profile_name=args.profile_name,
            reset=args.reset,
        )
    elif args.command == "inspect":
        payload = inspect_drill_report(args.file)
    else:  # pragma: no cover - argparse enforces commands
        parser.error(f"Unknown command: {args.command}")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if payload.get("status") in {"planned", "verified"} else 2


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--work-dir",
        type=Path,
        default=DEFAULT_DRILL_DIR,
        help="Directory for disposable DBs, backup JSON, and report JSON.",
    )
    parser.add_argument(
        "--profile-name",
        default=DEFAULT_PROFILE_NAME,
        help="Profile name to seed and verify during the drill.",
    )


def _migrated_engine(path: Path) -> tuple[Engine, GovernanceApiConfig]:
    path.parent.mkdir(parents=True, exist_ok=True)
    database_url = f"sqlite:///{path}"
    config = GovernanceApiConfig(database_url=database_url)
    upgrade_database(config=config)
    engine = create_governance_engine(database_url)
    return engine, config


def _seed_drill_data(engine: Engine, *, profile_name: str) -> dict[str, Any]:
    session_factory = create_session_factory(engine)
    with session_factory() as session:
        profile = TerminologyProfile(
            name=profile_name,
            normalized_name=normalize_profile_name(profile_name),
            description="Backup/restore drill profile",
        )
        term = CanonicalTerm(
            profile=profile,
            canonical_value="kubernetes",
            normalized_value=normalize_value("kubernetes"),
            slot="technology",
            status="active",
            description="Container orchestration platform used in drill data.",
        )
        tag = TermTag(
            term=term,
            value="infra",
            normalized_value=normalize_value("infra"),
        )
        alias = TermAlias(
            profile=profile,
            term=term,
            alias_value="k8s",
            normalized_alias=normalize_value("k8s"),
            status="active",
            confidence=1.0,
        )
        binding = ElasticsearchBinding(
            profile=profile,
            name=DEFAULT_BINDING_NAME,
            normalized_name=normalize_profile_name(DEFAULT_BINDING_NAME),
            description="Dry-run binding used by backup/restore drill.",
            index_name="backup-restore-drill-docs",
            text_fields=["title", "body"],
            target_field="skeinrank.attributes",
            filter_field="team",
            filter_value="platform",
            mode="dry_run",
            write_strategy="reindex_alias_swap",
            is_enabled=True,
            runtime_snapshot_json={
                "profile": profile_name,
                "terms": [{"canonical_value": "kubernetes", "aliases": ["k8s"]}],
            },
        )
        suggestion = GovernanceSuggestion(
            profile=profile,
            term=term,
            binding=binding,
            suggestion_type="alias",
            canonical_value="kubernetes",
            normalized_canonical=normalize_value("kubernetes"),
            alias_value="kube",
            normalized_alias=normalize_value("kube"),
            slot="technology",
            description="Agent-style pending alias proposal used by restore drill.",
            confidence=0.92,
            source="discovery",
            proposal_source_type="agent",
            proposal_source_name="backup-restore-drill",
            idempotency_key="backup-restore-drill:kube",
            source_payload_json={"evidence": ["kube rollout failed"]},
            validation_summary_json={"status": "warning", "category": "review"},
            context="backup_restore_drill",
            status="pending",
            created_by="backup-restore-drill",
            evidence_snapshot={"windows": [{"text": "kube rollout failed"}]},
            evidence_checked_by="backup-restore-drill",
        )
        snapshot = ProfileSnapshot(
            profile=profile,
            version="backup-restore-drill-v1",
            status="published",
            source="backup_restore_drill",
            artifact_path="snapshots/backup-restore-drill-v1.json",
            checksum="sha256:backup-restore-drill",
            published_at=datetime.now(timezone.utc),
        )
        run = AgentRun(
            run_id="backup-restore-drill-run-001",
            agent_name="backup-restore-drill",
            agent_version="v1",
            status="succeeded",
            trigger_type="test",
            profile=profile,
            binding=binding,
            summary_json={
                "documents_total": 3,
                "proposals_prepared": 1,
                "errors": 0,
            },
            report_uri="examples/pilots/reports/backup-restore-drill-report.json",
            requested_by="backup-restore-drill",
            started_at=datetime.now(timezone.utc),
            finished_at=datetime.now(timezone.utc),
        )
        session.add_all([alias, tag, suggestion, snapshot, run])
        session.commit()
        return {
            "profile_id": profile.id,
            "term_id": term.id,
            "alias_id": alias.id,
            "binding_id": binding.id,
            "suggestion_id": suggestion.id,
            "snapshot_id": snapshot.id,
            "agent_run_id": run.id,
        }


def _verify_database(engine: Engine, *, profile_name: str) -> dict[str, Any]:
    session_factory = create_session_factory(engine)
    with session_factory() as session:
        profile = session.scalar(
            select(TerminologyProfile).where(TerminologyProfile.name == profile_name)
        )
        counts = {
            "profiles": _count(session, TerminologyProfile),
            "terms": _count(session, CanonicalTerm),
            "aliases": _count(session, TermAlias),
            "tags": _count(session, TermTag),
            "bindings": _count(session, ElasticsearchBinding),
            "proposals": _count(session, GovernanceSuggestion),
            "snapshots": _count(session, ProfileSnapshot),
            "agent_runs": _count(session, AgentRun),
        }
        values: dict[str, Any] = {}
        if profile is not None:
            term = session.scalar(
                select(CanonicalTerm).where(CanonicalTerm.profile_id == profile.id)
            )
            alias = session.scalar(
                select(TermAlias).where(TermAlias.profile_id == profile.id)
            )
            binding = session.scalar(
                select(ElasticsearchBinding).where(
                    ElasticsearchBinding.profile_id == profile.id
                )
            )
            suggestion = session.scalar(
                select(GovernanceSuggestion).where(
                    GovernanceSuggestion.profile_id == profile.id
                )
            )
            snapshot = session.scalar(
                select(ProfileSnapshot).where(ProfileSnapshot.profile_id == profile.id)
            )
            run = session.scalar(
                select(AgentRun).where(AgentRun.profile_id == profile.id)
            )
            values = {
                "profile_name": profile.name,
                "canonical_value": term.canonical_value if term else None,
                "alias_value": alias.alias_value if alias else None,
                "binding_name": binding.name if binding else None,
                "binding_index": binding.index_name if binding else None,
                "proposal_alias": suggestion.alias_value if suggestion else None,
                "proposal_status": suggestion.status if suggestion else None,
                "snapshot_version": snapshot.version if snapshot else None,
                "agent_run_id": run.run_id if run else None,
                "agent_run_status": run.status if run else None,
            }
        required_counts = {
            "profiles": 1,
            "terms": 1,
            "aliases": 1,
            "tags": 1,
            "bindings": 1,
            "proposals": 1,
            "snapshots": 1,
            "agent_runs": 1,
        }
        missing = [
            name
            for name, minimum in required_counts.items()
            if counts.get(name, 0) < minimum
        ]
        return {
            "ok": profile is not None and not missing,
            "missing_required_counts": missing,
            "counts": counts,
            "representative_values": values,
        }


def _count(session: Any, model: type[Any]) -> int:
    return int(session.scalar(select(func.count()).select_from(model)) or 0)


def _safety_flags() -> dict[str, bool]:
    return {
        "openrouter_calls": False,
        "elasticsearch_calls": False,
        "database_calls": True,
        "runtime_mutation_enabled": False,
        "live_database_used": False,
        "uses_disposable_sqlite_databases": True,
        "generated_drill_artifacts_committed_by_default": False,
    }


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    raise SystemExit(main())
