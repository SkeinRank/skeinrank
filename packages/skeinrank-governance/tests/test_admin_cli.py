from __future__ import annotations

import json
from pathlib import Path

import pytest
from skeinrank_governance.cli import (
    GovernanceCliError,
    add_alias,
    add_term,
    build_snapshot,
    create_profile,
    export_snapshot,
    main,
)
from skeinrank_governance.db import (
    create_all,
    create_governance_engine,
    create_session_factory,
)
from skeinrank_governance.models import AuditEvent
from sqlalchemy import select


@pytest.fixture()
def session():
    engine = create_governance_engine("sqlite+pysqlite:///:memory:")
    create_all(engine)
    Session = create_session_factory(engine)
    with Session() as session:
        yield session


def test_admin_service_creates_terms_aliases_and_snapshot(session, tmp_path: Path):
    profile = create_profile(session, "default_it", description="IT terms")
    term = add_term(session, "default_it", "kubernetes", slot="tool")
    alias = add_alias(session, "default_it", "kubernetes", "k8s", confidence=0.99)
    session.commit()

    assert profile.normalized_name == "default_it"
    assert term.slot == "TOOL"
    assert alias.normalized_alias == "k8s"

    snapshot = build_snapshot(
        session,
        "default_it",
        snapshot_version="default_it@v1",
    )

    assert snapshot["profile_id"] == "default_it"
    assert snapshot["snapshot"]["source"] == "postgres"
    assert snapshot["snapshot"]["version"] == "default_it@v1"
    assert snapshot["alias_matcher"]["backend"] == "aho_corasick"
    assert snapshot["aliases"] == [
        {
            "slot": "TOOL",
            "canonical": "kubernetes",
            "aliases": [{"value": "k8s", "confidence": 0.99}],
        }
    ]

    output = tmp_path / "default_it.json"
    exported = export_snapshot(session, "default_it", output)
    session.commit()

    assert exported["profile_id"] == "default_it"
    assert output.exists()
    assert json.loads(output.read_text())["profile_id"] == "default_it"
    assert session.scalar(
        select(AuditEvent).where(AuditEvent.action == "snapshot_exported")
    )


def test_admin_service_rejects_duplicate_alias(session):
    create_profile(session, "default_it")
    add_term(session, "default_it", "postgresql", slot="DB")
    add_term(session, "default_it", "payment-gateway", slot="SERVICE")
    add_alias(session, "default_it", "postgresql", "pg")

    with pytest.raises(GovernanceCliError):
        add_alias(session, "default_it", "payment-gateway", "PG")


def test_admin_cli_end_to_end_workflow(tmp_path: Path, capsys):
    db_url = f"sqlite+pysqlite:///{tmp_path / 'governance.db'}"
    output = tmp_path / "snapshot.json"

    assert main(["--database-url", db_url, "db", "init"]) == 0
    assert main(["--database-url", db_url, "profile", "create", "default_it"]) == 0
    assert (
        main(
            [
                "--database-url",
                db_url,
                "term",
                "add",
                "default_it",
                "kubernetes",
                "--slot",
                "TOOL",
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "--database-url",
                db_url,
                "alias",
                "add",
                "default_it",
                "kubernetes",
                "k8s",
                "--confidence",
                "0.99",
            ]
        )
        == 0
    )
    assert main(["--database-url", db_url, "term", "list", "default_it"]) == 0
    listed = capsys.readouterr().out
    assert "TOOL kubernetes" in listed
    assert "k8s" in listed

    assert (
        main(
            [
                "--database-url",
                db_url,
                "snapshot",
                "export",
                "default_it",
                "--out",
                str(output),
                "--snapshot-version",
                "default_it@v1",
            ]
        )
        == 0
    )

    payload = json.loads(output.read_text())
    assert payload["snapshot"]["version"] == "default_it@v1"
    assert payload["alias_matcher"]["backend"] == "aho_corasick"
    assert payload["aliases"][0]["aliases"] == [{"value": "k8s", "confidence": 0.99}]


def test_admin_cli_returns_nonzero_for_missing_profile(tmp_path: Path, capsys):
    db_url = f"sqlite+pysqlite:///{tmp_path / 'governance.db'}"

    assert main(["--database-url", db_url, "db", "init"]) == 0
    assert (
        main(
            [
                "--database-url",
                db_url,
                "term",
                "add",
                "missing",
                "kubernetes",
                "--slot",
                "TOOL",
            ]
        )
        == 1
    )

    assert "Profile not found" in capsys.readouterr().err
