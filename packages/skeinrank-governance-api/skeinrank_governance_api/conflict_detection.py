"""Conflict detection reports for governed terminology state.

The report is intentionally read-only. It surfaces risky terminology shapes for
reviewers without mutating profiles, proposals, bindings, or runtime snapshots.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from typing import Any

from skeinrank_governance.models import (
    ACTIVE_STATUS,
    CanonicalTerm,
    GovernanceConflictReview,
    GovernanceGlobalStopListEntry,
    GovernanceStopListEntry,
    GovernanceSuggestion,
    TermAlias,
    TerminologyProfile,
    normalize_profile_name,
    utc_now,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

ConflictEntity = dict[str, Any]
ConflictItem = dict[str, Any]

DEFAULT_CONFLICT_SEVERITY_BY_TYPE = {
    "alias_maps_to_multiple_canonicals": "high",
    "pending_alias_conflicts_with_active_alias": "high",
    "alias_stop_list_collision": "high",
    "canonical_stop_list_collision": "high",
    "pending_alias_proposals_conflict": "medium",
    "canonical_surface_multiple_slots": "medium",
    "alias_surface_shared_across_profiles": "low",
}


def build_conflict_report(
    session: Session,
    *,
    profile_name: str | None = None,
    include_suggestions: bool = True,
) -> dict[str, Any]:
    """Build a read-only terminology conflict report.

    The scanner focuses on conflicts that can exist even with database uniqueness
    constraints in place: cross-profile surface reuse, stop-list drift, and
    pending proposal collisions. Per-conflict review state and severity are
    included when the stored governance metadata is available.
    """

    profile = _get_profile(session, profile_name) if profile_name else None
    profile_id = profile.id if profile is not None else None

    conflicts: list[ConflictItem] = []
    conflicts.extend(_detect_alias_surface_conflicts(session, profile_id=profile_id))
    conflicts.extend(_detect_canonical_slot_conflicts(session, profile_id=profile_id))
    conflicts.extend(_detect_stop_list_collisions(session, profile_id=profile_id))
    if include_suggestions:
        conflicts.extend(
            _detect_pending_proposal_conflicts(session, profile_id=profile_id)
        )

    conflicts = [_attach_conflict_fingerprint(item) for item in conflicts]
    conflicts = _merge_conflict_review_state(session, conflicts)
    conflicts = sorted(
        conflicts,
        key=lambda item: (
            item["review_status"],
            item["severity"],
            item["conflict_type"],
            item["normalized_value"],
            item.get("profile_name") or "",
        ),
    )
    return {
        "profile_name": profile.name if profile is not None else None,
        "normalized_profile_name": profile.normalized_name
        if profile is not None
        else None,
        "include_suggestions": include_suggestions,
        "total": len(conflicts),
        "conflicts": conflicts,
    }


def find_current_conflict(
    session: Session,
    *,
    fingerprint: str,
    profile_name: str | None = None,
    include_suggestions: bool = True,
) -> ConflictItem | None:
    """Find one current conflict by deterministic fingerprint."""

    report = build_conflict_report(
        session,
        profile_name=profile_name,
        include_suggestions=include_suggestions,
    )
    for conflict in report["conflicts"]:
        if conflict["fingerprint"] == fingerprint:
            return conflict
    return None


def upsert_conflict_review_state(
    session: Session,
    *,
    conflict: ConflictItem,
    severity: str | None = None,
    review_status: str | None = None,
    review_note: str | None = None,
    reviewed_by: str,
) -> GovernanceConflictReview:
    """Create or update review metadata for a current conflict."""

    review = session.scalar(
        select(GovernanceConflictReview).where(
            GovernanceConflictReview.fingerprint == conflict["fingerprint"]
        )
    )
    if review is None:
        review = GovernanceConflictReview(
            profile_id=_profile_id_from_conflict(conflict),
            fingerprint=conflict["fingerprint"],
            conflict_type=conflict["conflict_type"],
            normalized_value=conflict["normalized_value"],
            severity=conflict["severity"],
            review_status=conflict["review_status"],
            details_json=_review_details(conflict),
        )
        session.add(review)

    review.conflict_type = conflict["conflict_type"]
    review.normalized_value = conflict["normalized_value"]
    review.profile_id = _profile_id_from_conflict(conflict)
    review.details_json = _review_details(conflict)
    if severity is not None:
        review.severity = severity
    if review_status is not None:
        review.review_status = review_status
    if review_note is not None:
        review.review_note = review_note
    review.reviewed_by = reviewed_by
    review.reviewed_at = utc_now()
    return review


def merge_conflict_with_review_state(
    conflict: ConflictItem, review: GovernanceConflictReview | None
) -> ConflictItem:
    """Return conflict item decorated with persisted or default review state."""

    item = dict(conflict)
    item.setdefault(
        "severity",
        DEFAULT_CONFLICT_SEVERITY_BY_TYPE.get(item["conflict_type"], "medium"),
    )
    item.setdefault("review_status", "open")
    item.setdefault("review_note", None)
    item.setdefault("reviewed_by", None)
    item.setdefault("reviewed_at", None)
    if review is not None:
        item["severity"] = review.severity
        item["review_status"] = review.review_status
        item["review_note"] = review.review_note
        item["reviewed_by"] = review.reviewed_by
        item["reviewed_at"] = review.reviewed_at
    return item


def _get_profile(
    session: Session, profile_name: str | None
) -> TerminologyProfile | None:
    if profile_name is None:
        return None
    normalized = normalize_profile_name(profile_name)
    return session.scalar(
        select(TerminologyProfile).where(
            TerminologyProfile.normalized_name == normalized
        )
    )


def _profiles_by_id(session: Session) -> dict[int, TerminologyProfile]:
    return {
        profile.id: profile for profile in session.scalars(select(TerminologyProfile))
    }


def _attach_conflict_fingerprint(conflict: ConflictItem) -> ConflictItem:
    item = dict(conflict)
    item["fingerprint"] = _conflict_fingerprint(item)
    item["severity"] = DEFAULT_CONFLICT_SEVERITY_BY_TYPE.get(
        item["conflict_type"], "medium"
    )
    item["review_status"] = "open"
    item["review_note"] = None
    item["reviewed_by"] = None
    item["reviewed_at"] = None
    return item


def _merge_conflict_review_state(
    session: Session, conflicts: list[ConflictItem]
) -> list[ConflictItem]:
    if not conflicts:
        return []
    fingerprints = [conflict["fingerprint"] for conflict in conflicts]
    reviews = {
        review.fingerprint: review
        for review in session.scalars(
            select(GovernanceConflictReview).where(
                GovernanceConflictReview.fingerprint.in_(fingerprints)
            )
        )
    }
    return [
        merge_conflict_with_review_state(conflict, reviews.get(conflict["fingerprint"]))
        for conflict in conflicts
    ]


def _conflict_fingerprint(conflict: ConflictItem) -> str:
    payload = {
        "conflict_type": conflict["conflict_type"],
        "scope": conflict["scope"],
        "profile_name": conflict.get("profile_name"),
        "normalized_value": conflict["normalized_value"],
        "entities": sorted(
            (
                {
                    "entity_type": entity.get("entity_type"),
                    "profile_name": entity.get("profile_name"),
                    "canonical_value": entity.get("canonical_value"),
                    "alias_value": entity.get("alias_value"),
                    "normalized_value": entity.get("normalized_value"),
                    "slot": entity.get("slot"),
                    "target": entity.get("target"),
                    "source": entity.get("source"),
                }
                for entity in conflict.get("entities", [])
            ),
            key=lambda entity: json.dumps(entity, sort_keys=True),
        ),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _profile_id_from_conflict(conflict: ConflictItem) -> int | None:
    profile_ids = {
        entity.get("profile_id")
        for entity in conflict.get("entities", [])
        if entity.get("profile_id") is not None
    }
    return next(iter(profile_ids)) if len(profile_ids) == 1 else None


def _review_details(conflict: ConflictItem) -> dict[str, Any]:
    return {
        "scope": conflict.get("scope"),
        "profile_name": conflict.get("profile_name"),
        "title": conflict.get("title"),
        "message": conflict.get("message"),
        "suggested_action": conflict.get("suggested_action"),
        "entity_count": len(conflict.get("entities", [])),
    }


def _detect_alias_surface_conflicts(
    session: Session,
    *,
    profile_id: int | None,
) -> list[ConflictItem]:
    query = select(TermAlias).where(TermAlias.status == ACTIVE_STATUS)
    if profile_id is not None:
        query = query.where(TermAlias.profile_id == profile_id)
    aliases = list(session.scalars(query))
    profiles = _profiles_by_id(session)
    groups: dict[str, list[TermAlias]] = defaultdict(list)
    for alias in aliases:
        groups[alias.normalized_alias].append(alias)

    conflicts: list[ConflictItem] = []
    for normalized_alias, group in groups.items():
        if len(group) < 2:
            continue
        profile_ids = {alias.profile_id for alias in group}
        canonical_values = {
            alias.term.normalized_value for alias in group if alias.term
        }
        if profile_id is None and len(profile_ids) < 2:
            continue
        conflict_type = (
            "alias_maps_to_multiple_canonicals"
            if len(canonical_values) > 1
            else "alias_surface_shared_across_profiles"
        )
        conflicts.append(
            {
                "conflict_type": conflict_type,
                "scope": "cross_profile" if len(profile_ids) > 1 else "profile",
                "profile_name": None,
                "normalized_value": normalized_alias,
                "title": f"Alias surface {normalized_alias!r} appears in multiple contexts",
                "message": (
                    "The same alias surface is active in multiple profiles or terms. "
                    "Future binding policies can decide whether this is allowed per runtime context."
                ),
                "suggested_action": (
                    "Review whether the alias should stay shared, be renamed, or become an ambiguous alias candidate."
                ),
                "entities": [
                    _alias_entity(alias, profiles.get(alias.profile_id))
                    for alias in group
                ],
            }
        )
    return conflicts


def _detect_canonical_slot_conflicts(
    session: Session,
    *,
    profile_id: int | None,
) -> list[ConflictItem]:
    query = select(CanonicalTerm).where(CanonicalTerm.status == ACTIVE_STATUS)
    if profile_id is not None:
        query = query.where(CanonicalTerm.profile_id == profile_id)
    terms = list(session.scalars(query))
    profiles = _profiles_by_id(session)
    groups: dict[str, list[CanonicalTerm]] = defaultdict(list)
    for term in terms:
        groups[term.normalized_value].append(term)

    conflicts: list[ConflictItem] = []
    for normalized_value, group in groups.items():
        slots = {term.slot for term in group}
        profile_ids = {term.profile_id for term in group}
        if len(group) < 2 or len(slots) < 2:
            continue
        if profile_id is None and len(profile_ids) < 2:
            continue
        conflicts.append(
            {
                "conflict_type": "canonical_surface_multiple_slots",
                "scope": "cross_profile" if len(profile_ids) > 1 else "profile",
                "profile_name": None,
                "normalized_value": normalized_value,
                "title": f"Canonical surface {normalized_value!r} uses multiple slots",
                "message": (
                    "The same canonical surface is active with different primary slots. "
                    "Tags should carry secondary classification, while slot should remain the primary extraction role."
                ),
                "suggested_action": "Review the primary slot choice or replace secondary roles with tags.",
                "entities": [
                    _term_entity(term, profiles.get(term.profile_id)) for term in group
                ],
            }
        )
    return conflicts


def _detect_stop_list_collisions(
    session: Session,
    *,
    profile_id: int | None,
) -> list[ConflictItem]:
    profiles = _profiles_by_id(session)
    profile_stop_entries = list(
        session.scalars(
            select(GovernanceStopListEntry).where(
                GovernanceStopListEntry.is_active.is_(True)
            )
        )
    )
    global_stop_entries = list(
        session.scalars(
            select(GovernanceGlobalStopListEntry).where(
                GovernanceGlobalStopListEntry.is_active.is_(True)
            )
        )
    )
    profile_stop_by_key: dict[tuple[int, str], list[GovernanceStopListEntry]] = (
        defaultdict(list)
    )
    for entry in profile_stop_entries:
        profile_stop_by_key[(entry.profile_id, entry.normalized_value)].append(entry)
    global_stop_by_value: dict[str, list[GovernanceGlobalStopListEntry]] = defaultdict(
        list
    )
    for entry in global_stop_entries:
        global_stop_by_value[entry.normalized_value].append(entry)

    conflicts: list[ConflictItem] = []

    alias_query = select(TermAlias).where(TermAlias.status == ACTIVE_STATUS)
    if profile_id is not None:
        alias_query = alias_query.where(TermAlias.profile_id == profile_id)
    for alias in session.scalars(alias_query):
        entries = _matching_stop_entries(
            profile_stop_by_key.get((alias.profile_id, alias.normalized_alias), []),
            global_stop_by_value.get(alias.normalized_alias, []),
            target="alias",
        )
        if not entries:
            continue
        profile = profiles.get(alias.profile_id)
        conflicts.append(
            {
                "conflict_type": "alias_stop_list_collision",
                "scope": "profile",
                "profile_name": profile.name if profile else None,
                "normalized_value": alias.normalized_alias,
                "title": f"Alias {alias.alias_value!r} collides with active stop list",
                "message": "An active alias now matches an active stop-list guardrail.",
                "suggested_action": "Disable the alias, remove the stop-list entry, or document why this exception is safe.",
                "entities": [
                    _alias_entity(alias, profile),
                    *[_stop_list_entity(entry, profiles) for entry in entries],
                ],
            }
        )

    term_query = select(CanonicalTerm).where(CanonicalTerm.status == ACTIVE_STATUS)
    if profile_id is not None:
        term_query = term_query.where(CanonicalTerm.profile_id == profile_id)
    for term in session.scalars(term_query):
        entries = _matching_stop_entries(
            profile_stop_by_key.get((term.profile_id, term.normalized_value), []),
            global_stop_by_value.get(term.normalized_value, []),
            target="canonical",
        )
        if not entries:
            continue
        profile = profiles.get(term.profile_id)
        conflicts.append(
            {
                "conflict_type": "canonical_stop_list_collision",
                "scope": "profile",
                "profile_name": profile.name if profile else None,
                "normalized_value": term.normalized_value,
                "title": f"Canonical term {term.canonical_value!r} collides with active stop list",
                "message": "An active canonical term now matches an active stop-list guardrail.",
                "suggested_action": "Disable the term, remove the stop-list entry, or document why this exception is safe.",
                "entities": [
                    _term_entity(term, profile),
                    *[_stop_list_entity(entry, profiles) for entry in entries],
                ],
            }
        )
    return conflicts


def _detect_pending_proposal_conflicts(
    session: Session,
    *,
    profile_id: int | None,
) -> list[ConflictItem]:
    profiles = _profiles_by_id(session)
    active_aliases = list(
        session.scalars(select(TermAlias).where(TermAlias.status == ACTIVE_STATUS))
    )
    active_alias_by_profile_surface: dict[tuple[int, str], list[TermAlias]] = (
        defaultdict(list)
    )
    for alias in active_aliases:
        active_alias_by_profile_surface[
            (alias.profile_id, alias.normalized_alias)
        ].append(alias)

    suggestion_query = select(GovernanceSuggestion).where(
        GovernanceSuggestion.status == "pending",
        GovernanceSuggestion.suggestion_type == "alias",
        GovernanceSuggestion.normalized_alias.is_not(None),
    )
    if profile_id is not None:
        suggestion_query = suggestion_query.where(
            GovernanceSuggestion.profile_id == profile_id
        )
    suggestions = list(session.scalars(suggestion_query))

    conflicts: list[ConflictItem] = []
    pending_groups: dict[tuple[int, str], list[GovernanceSuggestion]] = defaultdict(
        list
    )
    for suggestion in suggestions:
        if suggestion.normalized_alias is None:
            continue
        pending_groups[(suggestion.profile_id, suggestion.normalized_alias)].append(
            suggestion
        )

        for active_alias in active_alias_by_profile_surface.get(
            (suggestion.profile_id, suggestion.normalized_alias), []
        ):
            active_canonical = (
                active_alias.term.normalized_value if active_alias.term else None
            )
            if active_canonical == suggestion.normalized_canonical:
                continue
            profile = profiles.get(suggestion.profile_id)
            conflicts.append(
                {
                    "conflict_type": "pending_alias_conflicts_with_active_alias",
                    "scope": "profile",
                    "profile_name": profile.name if profile else None,
                    "normalized_value": suggestion.normalized_alias,
                    "title": f"Pending alias {suggestion.alias_value!r} conflicts with active alias",
                    "message": "A pending proposal reuses an active alias surface for a different canonical term.",
                    "suggested_action": "Reject the proposal or convert the surface into an ambiguous alias candidate in a later policy layer.",
                    "entities": [
                        _suggestion_entity(suggestion, profile),
                        _alias_entity(active_alias, profile),
                    ],
                }
            )

    for (group_profile_id, normalized_alias), group in pending_groups.items():
        canonical_values = {suggestion.normalized_canonical for suggestion in group}
        if len(group) < 2 or len(canonical_values) < 2:
            continue
        profile = profiles.get(group_profile_id)
        conflicts.append(
            {
                "conflict_type": "pending_alias_proposals_conflict",
                "scope": "profile",
                "profile_name": profile.name if profile else None,
                "normalized_value": normalized_alias,
                "title": f"Pending alias proposals disagree on {normalized_alias!r}",
                "message": "Multiple pending proposals reuse one alias surface for different canonical terms.",
                "suggested_action": "Review the proposals together before applying a batch.",
                "entities": [
                    _suggestion_entity(suggestion, profile) for suggestion in group
                ],
            }
        )
    return conflicts


def _matching_stop_entries(
    profile_entries: list[GovernanceStopListEntry],
    global_entries: list[GovernanceGlobalStopListEntry],
    *,
    target: str,
) -> list[GovernanceStopListEntry | GovernanceGlobalStopListEntry]:
    allowed_targets = {target, "both"}
    entries: list[GovernanceStopListEntry | GovernanceGlobalStopListEntry] = []
    entries.extend(
        entry for entry in profile_entries if entry.target in allowed_targets
    )
    entries.extend(entry for entry in global_entries if entry.target in allowed_targets)
    return entries


def _alias_entity(
    alias: TermAlias, profile: TerminologyProfile | None
) -> ConflictEntity:
    term = alias.term
    return {
        "entity_type": "alias",
        "id": alias.id,
        "profile_id": alias.profile_id,
        "profile_name": profile.name if profile else None,
        "term_id": alias.term_id,
        "alias_id": alias.id,
        "suggestion_id": None,
        "stop_list_id": None,
        "canonical_value": term.canonical_value if term else None,
        "alias_value": alias.alias_value,
        "normalized_value": alias.normalized_alias,
        "slot": term.slot if term else None,
        "status": alias.status,
        "target": None,
        "source": "active_term_alias",
        "details": {"confidence": alias.confidence},
    }


def _term_entity(
    term: CanonicalTerm, profile: TerminologyProfile | None
) -> ConflictEntity:
    return {
        "entity_type": "term",
        "id": term.id,
        "profile_id": term.profile_id,
        "profile_name": profile.name if profile else None,
        "term_id": term.id,
        "alias_id": None,
        "suggestion_id": None,
        "stop_list_id": None,
        "canonical_value": term.canonical_value,
        "alias_value": None,
        "normalized_value": term.normalized_value,
        "slot": term.slot,
        "status": term.status,
        "target": None,
        "source": "canonical_term",
        "details": {
            "tags": [
                tag.value
                for tag in sorted(term.tags, key=lambda item: item.normalized_value)
            ]
        },
    }


def _suggestion_entity(
    suggestion: GovernanceSuggestion,
    profile: TerminologyProfile | None,
) -> ConflictEntity:
    return {
        "entity_type": "suggestion",
        "id": suggestion.id,
        "profile_id": suggestion.profile_id,
        "profile_name": profile.name if profile else None,
        "term_id": suggestion.term_id,
        "alias_id": suggestion.alias_id,
        "suggestion_id": suggestion.id,
        "stop_list_id": None,
        "canonical_value": suggestion.canonical_value,
        "alias_value": suggestion.alias_value,
        "normalized_value": suggestion.normalized_alias,
        "slot": suggestion.slot,
        "status": suggestion.status,
        "target": None,
        "source": suggestion.proposal_source_type,
        "details": {
            "proposal_source_name": suggestion.proposal_source_name,
            "confidence": suggestion.confidence,
        },
    }


def _stop_list_entity(
    entry: GovernanceStopListEntry | GovernanceGlobalStopListEntry,
    profiles: dict[int, TerminologyProfile],
) -> ConflictEntity:
    profile_id = getattr(entry, "profile_id", None)
    profile = profiles.get(profile_id) if profile_id is not None else None
    return {
        "entity_type": "stop_list_entry"
        if profile_id is not None
        else "global_stop_list_entry",
        "id": entry.id,
        "profile_id": profile_id,
        "profile_name": profile.name if profile else None,
        "term_id": None,
        "alias_id": None,
        "suggestion_id": None,
        "stop_list_id": entry.id,
        "canonical_value": None,
        "alias_value": None,
        "normalized_value": entry.normalized_value,
        "slot": None,
        "status": "active" if entry.is_active else "inactive",
        "target": entry.target,
        "source": "profile_stop_list" if profile_id is not None else "global_stop_list",
        "details": {"value": entry.value, "reason": entry.reason},
    }
