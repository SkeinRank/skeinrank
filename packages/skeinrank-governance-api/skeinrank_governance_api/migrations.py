"""Alembic migration helpers for the SkeinRank governance API.

The SQLAlchemy models and canonical Alembic revision files live in the
``skeinrank-governance`` package. This module gives the API package a stable,
configuration-aware migration entrypoint so deployments can run the same schema
migrations against the database URL used by the HTTP service.
"""

from __future__ import annotations

import argparse
import os
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from importlib import metadata
from pathlib import Path

from alembic import command
from alembic.config import Config

from .config import API_DATABASE_URL_ENV, GovernanceApiConfig
from .dependencies import create_engine_for_config

MIGRATION_SCRIPT_LOCATION_ENV = "SKEINRANK_GOVERNANCE_API_ALEMBIC_SCRIPT_LOCATION"


class MigrationConfigurationError(RuntimeError):
    """Raised when the governance Alembic migration directory cannot be found."""


def resolve_migration_script_location() -> Path:
    """Return the Alembic script directory used by governance storage.

    ``skeinrank-governance`` owns the SQLAlchemy metadata and migration history.
    In local development it is installed as an editable path dependency, so the
    migration directory is usually available next to the package root. The
    metadata fallback keeps the helper usable when the dependency is installed
    from a wheel.
    """

    override = os.getenv(MIGRATION_SCRIPT_LOCATION_ENV)
    if override:
        return _validate_script_location(Path(override))

    try:
        import skeinrank_governance
    except ModuleNotFoundError as exc:  # pragma: no cover - packaging guard
        raise MigrationConfigurationError(
            "Cannot import skeinrank_governance. Install the governance package "
            "before running API migrations."
        ) from exc

    package_root = Path(skeinrank_governance.__file__).resolve().parents[1]
    candidate = package_root / "alembic"
    if candidate.exists():
        return _validate_script_location(candidate)

    try:
        files = metadata.files("skeinrank-governance") or ()
    except metadata.PackageNotFoundError as exc:  # pragma: no cover - packaging guard
        raise MigrationConfigurationError(
            "Cannot locate skeinrank-governance package metadata for migrations."
        ) from exc

    for package_file in files:
        if package_file.parts == ("alembic", "env.py"):
            return _validate_script_location(Path(package_file.locate()).parent)

    raise MigrationConfigurationError(
        "Cannot locate governance Alembic migrations. Set "
        f"{MIGRATION_SCRIPT_LOCATION_ENV} to the migration directory."
    )


def create_alembic_config(
    config: GovernanceApiConfig | None = None,
    *,
    script_location: Path | None = None,
) -> Config:
    """Build an Alembic config for the API's configured database URL."""

    api_config = config or GovernanceApiConfig.from_env()
    migrations_dir = script_location or resolve_migration_script_location()

    alembic_config = Config()
    alembic_config.set_main_option("script_location", str(migrations_dir))
    alembic_config.set_main_option("sqlalchemy.url", api_config.database_url)
    return alembic_config


def upgrade_database(
    revision: str = "head",
    *,
    config: GovernanceApiConfig | None = None,
) -> None:
    """Run Alembic upgrade for the governance API database."""

    api_config = config or GovernanceApiConfig.from_env()
    with _database_url_env(api_config.database_url):
        command.upgrade(create_alembic_config(api_config), revision)


def downgrade_database(
    revision: str,
    *,
    config: GovernanceApiConfig | None = None,
) -> None:
    """Run Alembic downgrade for the governance API database."""

    api_config = config or GovernanceApiConfig.from_env()
    with _database_url_env(api_config.database_url):
        command.downgrade(create_alembic_config(api_config), revision)


def show_current_revision(*, config: GovernanceApiConfig | None = None) -> None:
    """Print the current database revision through Alembic."""

    api_config = config or GovernanceApiConfig.from_env()
    with _database_url_env(api_config.database_url):
        command.current(create_alembic_config(api_config))


def show_revision_history(*, config: GovernanceApiConfig | None = None) -> None:
    """Print known migration revisions through Alembic."""

    api_config = config or GovernanceApiConfig.from_env()
    with _database_url_env(api_config.database_url):
        command.history(create_alembic_config(api_config))


def check_database_schema(*, config: GovernanceApiConfig | None = None) -> int:
    """Print read-only schema health and return a shell-friendly status code."""

    api_config = config or GovernanceApiConfig.from_env()
    from .schema_health import check_schema_health, format_schema_health_for_cli

    engine = create_engine_for_config(api_config)
    try:
        health = check_schema_health(engine, config=api_config)
        print(format_schema_health_for_cli(health))
        return 0 if health.ok else 1
    finally:
        engine.dispose()


def main(argv: Sequence[str] | None = None) -> int:
    """Run governance API migrations from the command line."""

    parser = argparse.ArgumentParser(
        prog="python -m skeinrank_governance_api.migrations",
        description="Run Alembic migrations for the SkeinRank governance API database.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    upgrade_parser = subparsers.add_parser("upgrade", help="Upgrade the database.")
    upgrade_parser.add_argument("revision", nargs="?", default="head")

    downgrade_parser = subparsers.add_parser(
        "downgrade", help="Downgrade the database."
    )
    downgrade_parser.add_argument("revision")

    subparsers.add_parser("current", help="Show the current database revision.")
    subparsers.add_parser("history", help="Show migration history.")
    subparsers.add_parser(
        "check",
        help=(
            "Check Alembic revision and metadata table health without mutating "
            "the database."
        ),
    )

    args = parser.parse_args(argv)

    if args.command == "upgrade":
        upgrade_database(args.revision)
    elif args.command == "downgrade":
        downgrade_database(args.revision)
    elif args.command == "current":
        show_current_revision()
    elif args.command == "history":
        show_revision_history()
    elif args.command == "check":
        return check_database_schema()
    else:  # pragma: no cover - argparse enforces known commands
        parser.error(f"Unknown migration command: {args.command}")
    return 0


@contextmanager
def _database_url_env(database_url: str) -> Iterator[None]:
    """Temporarily make Alembic env.py use the API database URL."""

    previous_value = os.environ.get(API_DATABASE_URL_ENV)
    os.environ[API_DATABASE_URL_ENV] = database_url
    try:
        yield
    finally:
        if previous_value is None:
            os.environ.pop(API_DATABASE_URL_ENV, None)
        else:
            os.environ[API_DATABASE_URL_ENV] = previous_value


def _validate_script_location(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    if not resolved.exists():
        raise MigrationConfigurationError(
            f"Alembic migration directory does not exist: {resolved}"
        )
    if not (resolved / "env.py").exists():
        raise MigrationConfigurationError(
            f"Alembic migration directory is missing env.py: {resolved}"
        )
    if not (resolved / "versions").exists():
        raise MigrationConfigurationError(
            f"Alembic migration directory is missing versions/: {resolved}"
        )
    return resolved


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
