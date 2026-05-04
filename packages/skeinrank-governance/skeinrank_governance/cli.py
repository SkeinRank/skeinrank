"""Admin CLI for SkeinRank terminology governance.

The CLI is intentionally small and uses the SQLAlchemy models directly. It is a
control-plane tool: users edit terminology in the database and export runtime
snapshots for SkeinRank core/server/provider packages.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from collections.abc import Iterable, Sequence
from datetime import timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .db import create_all, create_governance_engine, create_session_factory
from .models import (
    ACTIVE_STATUS,
    AuditEvent,
    CanonicalTerm,
    TermAlias,
    TerminologyProfile,
    normalize_value,
    utc_now,
)

DATABASE_URL_ENV = "SKEINRANK_GOVERNANCE_DATABASE_URL"
DEFAULT_DATABASE_URL = "sqlite:///skeinrank_governance.db"


class GovernanceCliError(RuntimeError):
    """User-facing CLI error."""


def resolve_database_url(database_url: str | None = None) -> str:
    """Resolve the governance database URL from CLI, env, or local default."""

    return database_url or os.getenv(DATABASE_URL_ENV, DEFAULT_DATABASE_URL)


def create_profile(
    session: Session,
    name: str,
    *,
    description: str | None = None,
    actor: str = "cli",
) -> TerminologyProfile:
    """Create a terminology profile."""

    normalized_name = normalize_value(name)
    existing = session.scalar(
        select(TerminologyProfile).where(
            TerminologyProfile.normalized_name == normalized_name
        )
    )
    if existing is not None:
        raise GovernanceCliError(f"Profile already exists: {name}")

    profile = TerminologyProfile(name=name, description=description)
    session.add(profile)
    session.flush()
    _add_audit_event(
        session,
        profile=profile,
        actor=actor,
        action="profile_created",
        entity_type="terminology_profile",
        entity_id=str(profile.id),
        payload={"name": name, "description": description},
    )
    return profile


def get_profile(session: Session, name: str) -> TerminologyProfile:
    """Return a profile by name or raise a user-facing error."""

    profile = session.scalar(
        select(TerminologyProfile).where(
            TerminologyProfile.normalized_name == normalize_value(name)
        )
    )
    if profile is None:
        raise GovernanceCliError(f"Profile not found: {name}")
    return profile


def add_term(
    session: Session,
    profile_name: str,
    canonical_value: str,
    *,
    slot: str,
    description: str | None = None,
    status: str = ACTIVE_STATUS,
    actor: str = "cli",
) -> CanonicalTerm:
    """Add a canonical term to a profile."""

    profile = get_profile(session, profile_name)
    normalized_value = normalize_value(canonical_value)
    existing = session.scalar(
        select(CanonicalTerm).where(
            CanonicalTerm.profile_id == profile.id,
            CanonicalTerm.normalized_value == normalized_value,
        )
    )
    if existing is not None:
        raise GovernanceCliError(
            f"Canonical term already exists in profile {profile_name!r}: "
            f"{canonical_value}"
        )

    term = CanonicalTerm(
        profile=profile,
        canonical_value=canonical_value,
        slot=slot,
        description=description,
        status=status,
    )
    session.add(term)
    session.flush()
    _add_audit_event(
        session,
        profile=profile,
        actor=actor,
        action="term_added",
        entity_type="canonical_term",
        entity_id=str(term.id),
        payload={
            "canonical_value": canonical_value,
            "slot": slot,
            "description": description,
            "status": status,
        },
    )
    return term


def get_term(
    session: Session, profile: TerminologyProfile, canonical_value: str
) -> CanonicalTerm:
    """Return a canonical term inside a profile."""

    term = session.scalar(
        select(CanonicalTerm).where(
            CanonicalTerm.profile_id == profile.id,
            CanonicalTerm.normalized_value == normalize_value(canonical_value),
        )
    )
    if term is None:
        raise GovernanceCliError(
            f"Canonical term not found in profile {profile.name!r}: {canonical_value}"
        )
    return term


def add_alias(
    session: Session,
    profile_name: str,
    canonical_value: str,
    alias_value: str,
    *,
    confidence: float = 1.0,
    status: str = ACTIVE_STATUS,
    notes: str | None = None,
    actor: str = "cli",
) -> TermAlias:
    """Add an alias to a canonical term."""

    profile = get_profile(session, profile_name)
    term = get_term(session, profile, canonical_value)
    normalized_alias = normalize_value(alias_value)
    existing = session.scalar(
        select(TermAlias).where(
            TermAlias.profile_id == profile.id,
            TermAlias.normalized_alias == normalized_alias,
        )
    )
    if existing is not None:
        raise GovernanceCliError(
            f"Alias already exists in profile {profile.name!r}: {alias_value}"
        )

    alias = TermAlias(
        profile=profile,
        term=term,
        alias_value=alias_value,
        confidence=confidence,
        status=status,
        notes=notes,
    )
    session.add(alias)
    session.flush()
    _add_audit_event(
        session,
        profile=profile,
        actor=actor,
        action="alias_added",
        entity_type="term_alias",
        entity_id=str(alias.id),
        payload={
            "canonical_value": canonical_value,
            "alias_value": alias_value,
            "confidence": confidence,
            "status": status,
            "notes": notes,
        },
    )
    return alias


def list_terms(session: Session, profile_name: str) -> list[CanonicalTerm]:
    """List canonical terms for a profile, including aliases."""

    profile = get_profile(session, profile_name)
    terms = list(
        session.scalars(
            select(CanonicalTerm)
            .where(CanonicalTerm.profile_id == profile.id)
            .order_by(CanonicalTerm.slot, CanonicalTerm.normalized_value)
        )
    )
    for term in terms:
        # Force relationship loading inside the active session for callers/tests.
        term.aliases.sort(key=lambda alias: alias.normalized_alias)
    return terms


def build_snapshot(
    session: Session,
    profile_name: str,
    *,
    snapshot_version: str | None = None,
    description: str | None = None,
) -> dict[str, Any]:
    """Build a runtime-compatible grouped-alias snapshot from active DB rows."""

    profile = get_profile(session, profile_name)
    version = snapshot_version or f"{_snapshot_slug(profile.name)}@v1"
    aliases_by_term: dict[tuple[str, str], list[str | dict[str, Any]]] = defaultdict(
        list
    )

    active_terms = list(
        session.scalars(
            select(CanonicalTerm)
            .where(
                CanonicalTerm.profile_id == profile.id,
                CanonicalTerm.status == ACTIVE_STATUS,
            )
            .order_by(CanonicalTerm.slot, CanonicalTerm.normalized_value)
        )
    )
    term_ids = {term.id for term in active_terms}
    if term_ids:
        active_aliases = list(
            session.scalars(
                select(TermAlias)
                .where(
                    TermAlias.profile_id == profile.id,
                    TermAlias.term_id.in_(term_ids),
                    TermAlias.status == ACTIVE_STATUS,
                )
                .order_by(TermAlias.normalized_alias)
            )
        )
    else:
        active_aliases = []

    terms_by_id = {term.id: term for term in active_terms}
    for alias in active_aliases:
        term = terms_by_id[alias.term_id]
        key = (term.slot, term.canonical_value)
        aliases_by_term[key].append(_alias_snapshot_value(alias))

    alias_groups = []
    for term in active_terms:
        key = (term.slot, term.canonical_value)
        aliases = aliases_by_term.get(key, [])
        if not aliases:
            continue
        alias_groups.append(
            {
                "slot": term.slot,
                "canonical": term.canonical_value,
                "aliases": aliases,
            }
        )

    created_at = utc_now().astimezone(timezone.utc).replace(microsecond=0).isoformat()
    return {
        "profile_id": profile.name,
        "snapshot": {
            "version": version,
            "source": "postgres",
            "created_at": created_at,
            "description": description
            or f"Exported from SkeinRank governance profile {profile.name}.",
        },
        "alias_matcher": {"backend": "aho_corasick"},
        "aliases": alias_groups,
        "rules": [],
    }


def export_snapshot(
    session: Session,
    profile_name: str,
    output_path: str | Path,
    *,
    snapshot_version: str | None = None,
    description: str | None = None,
    actor: str = "cli",
) -> dict[str, Any]:
    """Export a profile snapshot to disk and add an audit event."""

    profile = get_profile(session, profile_name)
    snapshot = build_snapshot(
        session,
        profile_name,
        snapshot_version=snapshot_version,
        description=description,
    )
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n")

    _add_audit_event(
        session,
        profile=profile,
        actor=actor,
        action="snapshot_exported",
        entity_type="profile_snapshot",
        entity_id=snapshot["snapshot"]["version"],
        payload={
            "path": str(path),
            "snapshot_version": snapshot["snapshot"]["version"],
        },
    )
    return snapshot


def main(argv: Sequence[str] | None = None) -> int:
    """Run the governance admin CLI."""

    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 2

    database_url = resolve_database_url(args.database_url)
    try:
        engine = create_governance_engine(database_url)
        SessionFactory = create_session_factory(engine)
        if args.command == "db" and args.db_command == "init":
            create_all(engine)
            print(f"initialized_database={database_url}")
            return 0

        with SessionFactory() as session:
            result = _run_command(session, args)
            session.commit()
            if result is not None:
                print(result)
        return 0
    except IntegrityError as exc:
        print(f"skeinrank-admin: database integrity error: {exc.orig}", file=sys.stderr)
        return 1
    except GovernanceCliError as exc:
        print(f"skeinrank-admin: error: {exc}", file=sys.stderr)
        return 1


def _run_command(session: Session, args: argparse.Namespace) -> str | None:
    if args.command == "profile" and args.profile_command == "create":
        profile = create_profile(
            session,
            args.name,
            description=args.description,
            actor=args.actor,
        )
        return f"created_profile={profile.name}"

    if args.command == "term" and args.term_command == "add":
        term = add_term(
            session,
            args.profile,
            args.canonical,
            slot=args.slot,
            description=args.description,
            status=args.status,
            actor=args.actor,
        )
        return f"created_term={term.canonical_value} slot={term.slot}"

    if args.command == "term" and args.term_command == "list":
        terms = list_terms(session, args.profile)
        if args.json:
            return json.dumps(_terms_payload(terms), ensure_ascii=False, indent=2)
        return _format_terms(args.profile, terms)

    if args.command == "alias" and args.alias_command == "add":
        alias = add_alias(
            session,
            args.profile,
            args.canonical,
            args.alias,
            confidence=args.confidence,
            status=args.status,
            notes=args.notes,
            actor=args.actor,
        )
        return (
            f"created_alias={alias.alias_value} canonical={alias.term.canonical_value}"
        )

    if args.command == "snapshot" and args.snapshot_command == "export":
        snapshot = export_snapshot(
            session,
            args.profile,
            args.out,
            snapshot_version=args.snapshot_version,
            description=args.description,
            actor=args.actor,
        )
        return (
            f"exported_snapshot={args.out}\n"
            f"profile_id={snapshot['profile_id']}\n"
            f"snapshot_version={snapshot['snapshot']['version']}"
        )

    raise GovernanceCliError("Unknown command")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skeinrank-admin",
        description="Manage SkeinRank terminology governance data.",
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help=(
            f"SQLAlchemy database URL. Defaults to ${DATABASE_URL_ENV} or "
            f"{DEFAULT_DATABASE_URL!r}."
        ),
    )
    parser.add_argument("--actor", default="cli", help="Audit actor name.")

    subparsers = parser.add_subparsers(dest="command")

    db_parser = subparsers.add_parser("db", help="Database utility commands.")
    db_subparsers = db_parser.add_subparsers(dest="db_command")
    db_subparsers.add_parser("init", help="Create governance tables locally.")

    profile_parser = subparsers.add_parser("profile", help="Profile commands.")
    profile_subparsers = profile_parser.add_subparsers(dest="profile_command")
    profile_create = profile_subparsers.add_parser("create", help="Create profile.")
    profile_create.add_argument("name")
    profile_create.add_argument("--description", default=None)

    term_parser = subparsers.add_parser("term", help="Canonical term commands.")
    term_subparsers = term_parser.add_subparsers(dest="term_command")
    term_add = term_subparsers.add_parser("add", help="Add canonical term.")
    term_add.add_argument("profile")
    term_add.add_argument("canonical")
    term_add.add_argument("--slot", required=True)
    term_add.add_argument("--description", default=None)
    term_add.add_argument("--status", default=ACTIVE_STATUS)

    term_list = term_subparsers.add_parser("list", help="List profile terms.")
    term_list.add_argument("profile")
    term_list.add_argument("--json", action="store_true")

    alias_parser = subparsers.add_parser("alias", help="Alias commands.")
    alias_subparsers = alias_parser.add_subparsers(dest="alias_command")
    alias_add = alias_subparsers.add_parser("add", help="Add alias to term.")
    alias_add.add_argument("profile")
    alias_add.add_argument("canonical")
    alias_add.add_argument("alias")
    alias_add.add_argument("--confidence", type=float, default=1.0)
    alias_add.add_argument("--status", default=ACTIVE_STATUS)
    alias_add.add_argument("--notes", default=None)

    snapshot_parser = subparsers.add_parser("snapshot", help="Snapshot commands.")
    snapshot_subparsers = snapshot_parser.add_subparsers(dest="snapshot_command")
    snapshot_export = snapshot_subparsers.add_parser(
        "export", help="Export runtime snapshot JSON."
    )
    snapshot_export.add_argument("profile")
    snapshot_export.add_argument("--out", required=True)
    snapshot_export.add_argument("--snapshot-version", default=None)
    snapshot_export.add_argument("--description", default=None)

    return parser


def _format_terms(profile_name: str, terms: Iterable[CanonicalTerm]) -> str:
    lines = [f"profile={profile_name}"]
    for term in terms:
        active_aliases = [
            alias.alias_value for alias in term.aliases if alias.status == ACTIVE_STATUS
        ]
        lines.append(
            f"{term.slot} {term.canonical_value} "
            f"status={term.status} aliases={active_aliases}"
        )
    return "\n".join(lines)


def _terms_payload(terms: Iterable[CanonicalTerm]) -> list[dict[str, Any]]:
    return [
        {
            "canonical": term.canonical_value,
            "slot": term.slot,
            "status": term.status,
            "aliases": [
                {
                    "value": alias.alias_value,
                    "status": alias.status,
                    "confidence": alias.confidence,
                }
                for alias in sorted(
                    term.aliases, key=lambda item: item.normalized_alias
                )
            ],
        }
        for term in terms
    ]


def _alias_snapshot_value(alias: TermAlias) -> str | dict[str, Any]:
    if alias.confidence == 1.0:
        return alias.alias_value
    return {"value": alias.alias_value, "confidence": alias.confidence}


def _snapshot_slug(value: str) -> str:
    normalized = normalize_value(value)
    return normalized.replace(" ", "_") or "profile"


def _add_audit_event(
    session: Session,
    *,
    profile: TerminologyProfile,
    actor: str,
    action: str,
    entity_type: str,
    entity_id: str | None,
    payload: dict[str, Any],
) -> None:
    session.add(
        AuditEvent(
            profile=profile,
            actor=actor,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            payload_json=payload,
        )
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
