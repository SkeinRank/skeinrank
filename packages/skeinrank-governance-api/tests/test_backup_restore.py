from __future__ import annotations

import json

import pytest
from skeinrank_governance import create_governance_engine, create_session_factory
from skeinrank_governance.models import (
    CanonicalTerm,
    TermAlias,
    TerminologyProfile,
    normalize_profile_name,
    normalize_value,
)
from skeinrank_governance_api.backup_restore import (
    BACKUP_FORMAT_VERSION,
    BackupConflictError,
    export_backup,
    inspect_backup_file,
    restore_backup,
)
from skeinrank_governance_api.config import GovernanceApiConfig
from skeinrank_governance_api.migrations import upgrade_database
from sqlalchemy import select


def _database_url(tmp_path, name: str) -> str:
    return f"sqlite:///{tmp_path / name}"


def _migrated_engine(database_url: str):
    config = GovernanceApiConfig(database_url=database_url)
    upgrade_database(config=config)
    return create_governance_engine(database_url), config


def _seed_profile(engine) -> None:
    session_factory = create_session_factory(engine)
    with session_factory() as session:
        profile = TerminologyProfile(
            name="platform_ops",
            normalized_name=normalize_profile_name("platform_ops"),
            description="Platform operations",
        )
        term = CanonicalTerm(
            profile=profile,
            canonical_value="kubernetes",
            normalized_value=normalize_value("kubernetes"),
            slot="technology",
            status="active",
        )
        alias = TermAlias(
            profile=profile,
            term=term,
            alias_value="k8s",
            normalized_alias=normalize_value("k8s"),
            status="active",
            confidence=1.0,
        )
        session.add(alias)
        session.commit()


def test_backup_export_writes_portable_json_manifest(tmp_path):
    engine, config = _migrated_engine(_database_url(tmp_path, "source.db"))
    try:
        _seed_profile(engine)
        backup_path = tmp_path / "backup.json"

        payload = export_backup(engine=engine, config=config, output_path=backup_path)
    finally:
        engine.dispose()

    assert backup_path.exists()
    saved = json.loads(backup_path.read_text(encoding="utf-8"))
    assert saved["format_version"] == BACKUP_FORMAT_VERSION
    assert payload["format_version"] == BACKUP_FORMAT_VERSION
    tables = {table["name"]: table for table in saved["tables"]}
    assert tables["terminology_profiles"]["row_count"] == 1
    assert tables["canonical_terms"]["row_count"] == 1
    assert tables["term_aliases"]["row_count"] == 1
    assert saved["database"]["schema"]["current_matches_head"] is True


def test_backup_inspect_returns_compact_table_counts(tmp_path):
    engine, config = _migrated_engine(_database_url(tmp_path, "source.db"))
    try:
        _seed_profile(engine)
        backup_path = tmp_path / "backup.json"
        export_backup(engine=engine, config=config, output_path=backup_path)
    finally:
        engine.dispose()

    summary = inspect_backup_file(backup_path)

    assert summary["format_version"] == BACKUP_FORMAT_VERSION
    tables = {table["name"]: table["row_count"] for table in summary["tables"]}
    assert tables["terminology_profiles"] == 1
    assert tables["term_aliases"] == 1


def test_backup_restore_requires_replace_for_non_empty_target(tmp_path):
    source_engine, source_config = _migrated_engine(
        _database_url(tmp_path, "source.db")
    )
    try:
        _seed_profile(source_engine)
        backup_path = tmp_path / "backup.json"
        export_backup(
            engine=source_engine, config=source_config, output_path=backup_path
        )
    finally:
        source_engine.dispose()

    target_engine, target_config = _migrated_engine(
        _database_url(tmp_path, "target.db")
    )
    try:
        _seed_profile(target_engine)
        with pytest.raises(BackupConflictError):
            restore_backup(
                engine=target_engine,
                config=target_config,
                input_path=backup_path,
            )
    finally:
        target_engine.dispose()


def test_backup_restore_rehydrates_rows_into_migrated_database(tmp_path):
    source_engine, source_config = _migrated_engine(
        _database_url(tmp_path, "source.db")
    )
    try:
        _seed_profile(source_engine)
        backup_path = tmp_path / "backup.json"
        export_backup(
            engine=source_engine, config=source_config, output_path=backup_path
        )
    finally:
        source_engine.dispose()

    target_engine, target_config = _migrated_engine(
        _database_url(tmp_path, "target.db")
    )
    try:
        dry_run = restore_backup(
            engine=target_engine,
            config=target_config,
            input_path=backup_path,
            dry_run=True,
        )
        assert dry_run["status"] == "validated"
        report = restore_backup(
            engine=target_engine,
            config=target_config,
            input_path=backup_path,
            replace=True,
            yes=True,
        )
        assert report["status"] == "restored"

        session_factory = create_session_factory(target_engine)
        with session_factory() as session:
            profile = session.scalar(select(TerminologyProfile))
            alias = session.scalar(select(TermAlias))
            assert profile is not None
            assert profile.name == "platform_ops"
            assert alias is not None
            assert alias.alias_value == "k8s"
    finally:
        target_engine.dispose()
