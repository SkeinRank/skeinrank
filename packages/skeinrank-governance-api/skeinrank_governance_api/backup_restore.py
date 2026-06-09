"""Portable backup/restore helpers for SkeinRank governance operations.

The backup format is intentionally JSON-based and SQLAlchemy-metadata driven.
It is meant as an operational safety net for local, pilot, and small production
deployments, not as an alternative to native PostgreSQL backups for large
production databases.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Import models for side effects so Base.metadata is fully populated.
import skeinrank_governance.models as _governance_models  # noqa: F401
from skeinrank_governance.db import Base
from sqlalchemy import DateTime, delete, func, inspect, select
from sqlalchemy.engine import Engine
from sqlalchemy.sql.schema import Column, Table

from .config import GovernanceApiConfig
from .dependencies import create_engine_for_config
from .schema_health import check_schema_health

BACKUP_FORMAT_VERSION = "skeinrank.governance.backup.v1"
DEFAULT_BACKUP_INDENT = 2


class BackupRestoreError(RuntimeError):
    """Raised when backup/restore validation fails."""


class BackupConflictError(BackupRestoreError):
    """Raised when restore would overwrite non-empty target tables unsafely."""


def export_backup(
    *,
    engine: Engine,
    config: GovernanceApiConfig,
    output_path: Path,
) -> dict[str, Any]:
    """Export SQLAlchemy governance tables into a portable JSON backup file."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    schema_health = check_schema_health(engine, config=config)
    tables: list[dict[str, Any]] = []
    with engine.connect() as connection:
        for table in _governance_tables():
            rows = [
                _serialize_row(table, row)
                for row in connection.execute(_ordered_select(table)).mappings().all()
            ]
            tables.append(
                {
                    "name": table.name,
                    "columns": [column.name for column in table.columns],
                    "row_count": len(rows),
                    "rows": rows,
                }
            )

    payload: dict[str, Any] = {
        "format_version": BACKUP_FORMAT_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "service": {
            "name": config.service_name,
            "version": config.service_version,
        },
        "database": {
            "dialect": engine.dialect.name,
            "schema": {
                "ok": schema_health.ok,
                "current_revision": schema_health.current_revision,
                "head_revision": schema_health.head_revision,
                "current_matches_head": schema_health.current_matches_head,
                "multiple_heads": schema_health.multiple_heads,
                "missing_tables": schema_health.missing_tables,
            },
        },
        "tables": tables,
        "warnings": _backup_warnings(schema_health_ok=schema_health.ok),
    }
    output_path.write_text(
        json.dumps(
            payload,
            indent=DEFAULT_BACKUP_INDENT,
            ensure_ascii=False,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return payload


def inspect_backup_file(path: Path) -> dict[str, Any]:
    """Return a compact summary for a backup file without connecting to a DB."""

    payload = _load_backup(path)
    return {
        "format_version": payload["format_version"],
        "generated_at": payload.get("generated_at"),
        "service": payload.get("service", {}),
        "database": payload.get("database", {}),
        "tables": [
            {
                "name": table.get("name"),
                "row_count": int(
                    table.get("row_count") or len(table.get("rows") or [])
                ),
            }
            for table in payload.get("tables", [])
        ],
        "warnings": payload.get("warnings", []),
    }


def restore_backup(
    *,
    engine: Engine,
    config: GovernanceApiConfig,
    input_path: Path,
    replace: bool = False,
    yes: bool = False,
    dry_run: bool = False,
    skip_schema_check: bool = False,
) -> dict[str, Any]:
    """Restore a portable governance backup into an already-migrated database.

    Restore is intentionally explicit:
    - target schema must match Alembic head unless ``skip_schema_check`` is set;
    - non-empty target tables require ``replace=True`` and ``yes=True``;
    - ``dry_run`` validates everything but does not mutate the database.
    """

    payload = _load_backup(input_path)
    tables_by_name = {table.name: table for table in _governance_tables()}
    backup_tables = payload.get("tables") or []
    unknown_tables = sorted(
        table.get("name", "")
        for table in backup_tables
        if table.get("name") not in tables_by_name
    )
    if unknown_tables:
        raise BackupRestoreError(
            "Backup contains tables that are not part of current governance metadata: "
            + ", ".join(unknown_tables)
        )

    schema_health = check_schema_health(engine, config=config)
    if not skip_schema_check and not schema_health.ok:
        raise BackupRestoreError(
            "Target database schema is not healthy. Run migrations first or pass "
            "--skip-schema-check for emergency restore after manual verification."
        )

    target_counts = _target_table_counts(engine)
    non_empty_tables = sorted(
        name for name, count in target_counts.items() if count > 0
    )
    if non_empty_tables and not (replace and yes):
        raise BackupConflictError(
            "Target governance tables are not empty: "
            + ", ".join(non_empty_tables[:10])
            + ("..." if len(non_empty_tables) > 10 else "")
            + ". Use --replace --yes after taking a fresh backup."
        )

    backup_counts = {
        str(table.get("name")): int(
            table.get("row_count") or len(table.get("rows") or [])
        )
        for table in backup_tables
    }
    report = {
        "status": "validated" if dry_run else "restored",
        "dry_run": dry_run,
        "replace": replace,
        "source_format_version": payload["format_version"],
        "source_generated_at": payload.get("generated_at"),
        "tables": backup_counts,
        "total_rows": sum(backup_counts.values()),
    }
    if dry_run:
        return report

    with engine.begin() as connection:
        if replace:
            for table in reversed(_governance_tables()):
                connection.execute(delete(table))
        for backup_table in backup_tables:
            table = tables_by_name[str(backup_table["name"])]
            rows = [
                _deserialize_row(table, row) for row in backup_table.get("rows") or []
            ]
            if rows:
                connection.execute(table.insert(), rows)
    return report


def main(argv: Sequence[str] | None = None) -> int:
    """Run backup/restore commands from ``python -m``."""

    parser = argparse.ArgumentParser(
        prog="python -m skeinrank_governance_api.backup_restore",
        description="Export, inspect, and restore SkeinRank governance DB backups.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    export_parser = subparsers.add_parser("export", help="Export governance DB backup.")
    export_parser.add_argument(
        "--out",
        required=True,
        type=Path,
        help="Output JSON path.",
    )
    export_parser.add_argument(
        "--database-url",
        help="Override SKEINRANK_GOVERNANCE_API_DATABASE_URL for this command.",
    )

    inspect_parser = subparsers.add_parser("inspect", help="Inspect backup metadata.")
    inspect_parser.add_argument(
        "--file",
        required=True,
        type=Path,
        help="Backup JSON path.",
    )

    restore_parser = subparsers.add_parser(
        "restore", help="Restore governance DB backup."
    )
    restore_parser.add_argument(
        "--file",
        required=True,
        type=Path,
        help="Backup JSON path.",
    )
    restore_parser.add_argument(
        "--database-url",
        help="Override SKEINRANK_GOVERNANCE_API_DATABASE_URL for this command.",
    )
    restore_parser.add_argument(
        "--replace",
        action="store_true",
        help="Clear governance tables before restore.",
    )
    restore_parser.add_argument(
        "--yes",
        action="store_true",
        help="Confirm destructive restore actions.",
    )
    restore_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate restore without writing.",
    )
    restore_parser.add_argument(
        "--skip-schema-check",
        action="store_true",
        help="Skip target schema health check after manual verification.",
    )

    args = parser.parse_args(argv)
    try:
        if args.command == "inspect":
            print(
                json.dumps(
                    inspect_backup_file(args.file),
                    indent=2,
                    ensure_ascii=False,
                )
            )
            return 0

        config = _config_with_database_url(args.database_url)
        engine = create_engine_for_config(config)
        try:
            if args.command == "export":
                payload = export_backup(
                    engine=engine,
                    config=config,
                    output_path=args.out,
                )
                summary = {
                    "status": "exported",
                    "path": str(args.out),
                    "format_version": payload["format_version"],
                    "tables": len(payload.get("tables") or []),
                    "total_rows": sum(
                        int(table.get("row_count") or 0)
                        for table in payload.get("tables") or []
                    ),
                    "warnings": payload.get("warnings", []),
                }
            elif args.command == "restore":
                summary = restore_backup(
                    engine=engine,
                    config=config,
                    input_path=args.file,
                    replace=args.replace,
                    yes=args.yes,
                    dry_run=args.dry_run,
                    skip_schema_check=args.skip_schema_check,
                )
            else:  # pragma: no cover - argparse enforces commands
                parser.error(f"Unknown command: {args.command}")
            print(json.dumps(summary, indent=2, ensure_ascii=False))
            return 0
        finally:
            engine.dispose()
    except BackupRestoreError as exc:
        parser.exit(2, f"error: {exc}\n")


def _governance_tables() -> tuple[Table, ...]:
    return tuple(Base.metadata.sorted_tables)


def _ordered_select(table: Table):
    statement = select(table)
    primary_keys = list(table.primary_key.columns)
    if primary_keys:
        statement = statement.order_by(*primary_keys)
    return statement


def _serialize_row(table: Table, row: dict[str, Any]) -> dict[str, Any]:
    serialized: dict[str, Any] = {}
    for column in table.columns:
        value = row.get(column.name)
        if isinstance(value, datetime):
            serialized[column.name] = value.isoformat()
        else:
            serialized[column.name] = value
    return serialized


def _deserialize_row(table: Table, row: dict[str, Any]) -> dict[str, Any]:
    restored: dict[str, Any] = {}
    columns_by_name: dict[str, Column[Any]] = {
        column.name: column for column in table.columns
    }
    for name, value in row.items():
        column = columns_by_name.get(name)
        if column is None:
            continue
        if value is not None and isinstance(column.type, DateTime):
            restored[name] = _parse_datetime(value)
        else:
            restored[name] = value
    return restored


def _parse_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        raise BackupRestoreError(f"Cannot restore datetime value {value!r}")
    normalized = value.replace("Z", "+00:00")
    return datetime.fromisoformat(normalized)


def _target_table_counts(engine: Engine) -> dict[str, int]:
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    counts: dict[str, int] = {}
    with engine.connect() as connection:
        for table in _governance_tables():
            if table.name not in existing_tables:
                counts[table.name] = 0
                continue
            counts[table.name] = int(
                connection.execute(select(func.count()).select_from(table)).scalar_one()
            )
    return counts


def _load_backup(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise BackupRestoreError(f"Backup file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise BackupRestoreError(f"Invalid backup JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise BackupRestoreError("Backup file must contain a JSON object.")
    if payload.get("format_version") != BACKUP_FORMAT_VERSION:
        raise BackupRestoreError(
            f"Unsupported backup format version: {payload.get('format_version')!r}"
        )
    if not isinstance(payload.get("tables"), list):
        raise BackupRestoreError("Backup file is missing a tables list.")
    return payload


def _config_with_database_url(database_url: str | None) -> GovernanceApiConfig:
    base = GovernanceApiConfig.from_env()
    if not database_url:
        return base
    return replace(base, database_url=database_url)


def _backup_warnings(*, schema_health_ok: bool) -> list[str]:
    warnings: list[str] = []
    if not schema_health_ok:
        warnings.append(
            "Source schema is not at the current Alembic head; "
            "run migrations before using this backup for restore."
        )
    warnings.append(
        "This portable JSON backup is intended for MVP/dev/pilot operations; "
        "use native database backups for large production datasets."
    )
    return warnings


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    raise SystemExit(main())
