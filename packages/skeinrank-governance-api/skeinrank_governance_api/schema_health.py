"""Read-only schema health checks for governance API deployments."""

from __future__ import annotations

from collections.abc import Iterable

from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect
from sqlalchemy.engine import Engine

from .config import GovernanceApiConfig
from .migrations import create_alembic_config
from .schemas import SchemaHealth


def check_schema_health(
    engine: Engine,
    *,
    config: GovernanceApiConfig | None = None,
) -> SchemaHealth:
    """Return Alembic and SQLAlchemy metadata health for a governance database.

    The check is intentionally read-only. It validates three deployment-critical
    properties without mutating schema state:

    * the migration script tree has exactly one Alembic head;
    * the database exposes an ``alembic_version`` table at that head;
    * every table declared in SQLAlchemy metadata exists in the database.
    """

    try:
        alembic_config = create_alembic_config(config)
        script_directory = ScriptDirectory.from_config(alembic_config)
        migration_heads = sorted(script_directory.get_heads())
        head_revision = migration_heads[0] if len(migration_heads) == 1 else None

        inspector = inspect(engine)
        database_tables = set(inspector.get_table_names())
        expected_tables = _expected_metadata_tables()
        missing_tables = sorted(set(expected_tables) - database_tables)
        alembic_version_present = "alembic_version" in database_tables
        current_revisions = _current_database_revisions(engine, alembic_version_present)
        current_revision = current_revisions[0] if len(current_revisions) == 1 else None
        current_matches_head = (
            len(current_revisions) == 1
            and len(migration_heads) == 1
            and current_revisions[0] == migration_heads[0]
        )
        multiple_heads = len(migration_heads) > 1
        ok = (
            alembic_version_present
            and current_matches_head
            and not multiple_heads
            and not missing_tables
        )

        return SchemaHealth(
            ok=ok,
            alembic_version_present=alembic_version_present,
            current_revision=current_revision,
            current_revisions=current_revisions,
            head_revision=head_revision,
            migration_heads=migration_heads,
            current_matches_head=current_matches_head,
            multiple_heads=multiple_heads,
            missing_tables=missing_tables,
            expected_tables_count=len(expected_tables),
            database_tables_count=len(database_tables),
        )
    except Exception as exc:
        return SchemaHealth(
            ok=False,
            alembic_version_present=False,
            current_revision=None,
            current_revisions=[],
            head_revision=None,
            migration_heads=[],
            current_matches_head=False,
            multiple_heads=False,
            missing_tables=[],
            expected_tables_count=0,
            database_tables_count=0,
            error=f"{type(exc).__name__}: {exc}",
        )


def format_schema_health_for_cli(health: SchemaHealth) -> str:
    """Format schema health as a stable, grep-friendly CLI report."""

    lines = [
        f"schema_ok={str(health.ok).lower()}",
        f"alembic_version_present={str(health.alembic_version_present).lower()}",
        f"current_revision={health.current_revision or ''}",
        f"head_revision={health.head_revision or ''}",
        f"current_matches_head={str(health.current_matches_head).lower()}",
        f"multiple_heads={str(health.multiple_heads).lower()}",
        "migration_heads=" + ",".join(health.migration_heads),
        "missing_tables=" + ",".join(health.missing_tables),
        f"expected_tables_count={health.expected_tables_count}",
        f"database_tables_count={health.database_tables_count}",
    ]
    if health.error:
        lines.append(f"error={health.error}")
    return "\n".join(lines)


def _current_database_revisions(
    engine: Engine,
    alembic_version_present: bool,
) -> list[str]:
    if not alembic_version_present:
        return []
    with engine.connect() as connection:
        context = MigrationContext.configure(connection)
        return sorted(context.get_current_heads())


def _expected_metadata_tables() -> list[str]:
    import skeinrank_governance.models  # noqa: F401  # Populate Base.metadata.
    from skeinrank_governance.db import Base

    return sorted(_table_names(Base.metadata.tables.keys()))


def _table_names(values: Iterable[str]) -> set[str]:
    return {str(value) for value in values if str(value)}
