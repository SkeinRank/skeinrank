"""Runtime text canonicalization endpoints."""

from __future__ import annotations

import re
from dataclasses import dataclass

from fastapi import APIRouter, Depends, HTTPException, status
from skeinrank_governance.models import (
    CanonicalTerm,
    GovernanceGlobalStopListEntry,
    GovernanceStopListEntry,
    TermAlias,
    TerminologyProfile,
    normalize_profile_name,
    normalize_value,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import AuthContext, require_roles
from ..dependencies import get_session
from ..schemas import (
    TextCanonicalizeEvidence,
    TextCanonicalizeMatch,
    TextCanonicalizeRequest,
    TextCanonicalizeResponse,
)

router = APIRouter(prefix="/v1/text", tags=["runtime"])

_CANONICALIZE_MODES = {"annotate", "replace", "attributes"}


@dataclass(frozen=True)
class _AliasEntry:
    alias_value: str
    normalized_alias: str
    canonical_value: str
    normalized_canonical: str
    slot: str
    confidence: float


@dataclass(frozen=True)
class _CandidateMatch:
    alias_value: str
    canonical_value: str
    slot: str
    matched_text: str
    start: int
    end: int
    confidence: float


@router.post("/canonicalize", response_model=TextCanonicalizeResponse)
def canonicalize_text(
    request: TextCanonicalizeRequest,
    _current_user: AuthContext = Depends(
        require_roles("admin", "moderator", "contributor")
    ),
    session: Session = Depends(get_session),
) -> TextCanonicalizeResponse:
    """Canonicalize aliases and jargon in a text using one terminology profile."""

    mode = request.mode.strip().lower()
    if mode not in _CANONICALIZE_MODES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                "Invalid canonicalization mode. "
                "Expected one of: annotate, replace, attributes."
            ),
        )

    profile = _get_profile_or_404(session, request.profile_name)
    alias_entries = _active_alias_entries_for_profile(session, profile)
    candidate_matches = _find_alias_matches(request.text, alias_entries)
    matches = _select_non_overlapping_matches(candidate_matches, request.max_matches)

    canonical_text = request.text
    replacements: list[TextCanonicalizeMatch] = []
    if mode == "replace":
        canonical_text = _replace_matches(request.text, matches)
        replacements = [_match_response(match) for match in matches]
    elif mode == "annotate":
        replacements = [_match_response(match) for match in matches]

    canonical_values = sorted({match.canonical_value for match in matches})
    slots = _slots_for_matches(matches)
    matched_aliases = sorted({match.alias_value for match in matches})
    evidence = (
        [
            TextCanonicalizeEvidence(
                reason="Alias matched active canonical term",
                alias_value=match.alias_value,
                canonical_value=match.canonical_value,
                slot=match.slot,
                matched_text=match.matched_text,
                start=match.start,
                end=match.end,
                confidence=match.confidence,
                source="alias",
            )
            for match in matches
        ]
        if request.include_evidence
        else []
    )

    warnings: list[str] = []
    if candidate_matches and len(matches) < len(candidate_matches):
        warnings.append(
            "Some overlapping or extra matches were omitted from replacements."
        )
    if not alias_entries:
        warnings.append("No active aliases are available for this profile.")
    if not matches:
        warnings.append("No active aliases matched the input text.")

    return TextCanonicalizeResponse(
        profile_name=profile.name,
        normalized_profile_name=profile.normalized_name,
        mode=mode,
        original_text=request.text,
        canonical_text=canonical_text,
        changed=canonical_text != request.text,
        canonical_values=canonical_values,
        slots=slots,
        matched_aliases=matched_aliases,
        replacements=replacements,
        evidence=evidence,
        warnings=warnings,
    )


def _get_profile_or_404(session: Session, profile_name: str) -> TerminologyProfile:
    normalized_name = normalize_profile_name(profile_name)
    profile = session.scalar(
        select(TerminologyProfile).where(
            TerminologyProfile.normalized_name == normalized_name
        )
    )
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Profile not found: {profile_name}",
        )
    return profile


def _active_alias_entries_for_profile(
    session: Session, profile: TerminologyProfile
) -> list[_AliasEntry]:
    blocked_alias_values = _active_stop_values_for_target(
        session, profile, targets=("alias", "both")
    ) | _active_global_stop_values_for_target(session, targets=("alias", "both"))
    blocked_canonical_values = _active_stop_values_for_target(
        session, profile, targets=("canonical", "both")
    ) | _active_global_stop_values_for_target(session, targets=("canonical", "both"))
    aliases = list(
        session.scalars(
            select(TermAlias)
            .join(CanonicalTerm)
            .where(
                TermAlias.profile_id == profile.id,
                TermAlias.status == "active",
                CanonicalTerm.status == "active",
            )
            .order_by(TermAlias.normalized_alias)
        )
    )
    entries: list[_AliasEntry] = []
    for alias in aliases:
        if alias.normalized_alias in blocked_alias_values:
            continue
        if alias.term.normalized_value in blocked_canonical_values:
            continue
        entries.append(
            _AliasEntry(
                alias_value=alias.alias_value,
                normalized_alias=alias.normalized_alias,
                canonical_value=alias.term.canonical_value,
                normalized_canonical=alias.term.normalized_value,
                slot=alias.term.slot,
                confidence=alias.confidence,
            )
        )
    return entries


def _active_stop_values_for_target(
    session: Session, profile: TerminologyProfile, *, targets: tuple[str, ...]
) -> set[str]:
    values = session.scalars(
        select(GovernanceStopListEntry.normalized_value).where(
            GovernanceStopListEntry.profile_id == profile.id,
            GovernanceStopListEntry.is_active.is_(True),
            GovernanceStopListEntry.target.in_(targets),
        )
    )
    return set(values)


def _active_global_stop_values_for_target(
    session: Session, *, targets: tuple[str, ...]
) -> set[str]:
    values = session.scalars(
        select(GovernanceGlobalStopListEntry.normalized_value).where(
            GovernanceGlobalStopListEntry.is_active.is_(True),
            GovernanceGlobalStopListEntry.target.in_(targets),
        )
    )
    return set(values)


def _find_alias_matches(
    text: str, alias_entries: list[_AliasEntry]
) -> list[_CandidateMatch]:
    matches: list[_CandidateMatch] = []
    for alias_entry in alias_entries:
        pattern = _alias_pattern(alias_entry.alias_value)
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            matches.append(
                _CandidateMatch(
                    alias_value=alias_entry.alias_value,
                    canonical_value=alias_entry.canonical_value,
                    slot=alias_entry.slot,
                    matched_text=match.group(0),
                    start=match.start(),
                    end=match.end(),
                    confidence=alias_entry.confidence,
                )
            )
    return sorted(
        matches,
        key=lambda item: (item.start, -(item.end - item.start), item.alias_value),
    )


def _alias_pattern(alias_value: str) -> str:
    parts = [re.escape(part) for part in normalize_value(alias_value).split()]
    if not parts:
        return r"(?!)"
    body = r"\s+".join(parts)
    return rf"(?<!\w){body}(?!\w)"


def _select_non_overlapping_matches(
    matches: list[_CandidateMatch], max_matches: int
) -> list[_CandidateMatch]:
    selected: list[_CandidateMatch] = []
    occupied: list[range] = []
    for match in matches:
        match_range = range(match.start, match.end)
        if any(_ranges_overlap(match_range, used) for used in occupied):
            continue
        selected.append(match)
        occupied.append(match_range)
        if len(selected) >= max_matches:
            break
    return selected


def _ranges_overlap(left: range, right: range) -> bool:
    return left.start < right.stop and right.start < left.stop


def _replace_matches(text: str, matches: list[_CandidateMatch]) -> str:
    if not matches:
        return text
    pieces: list[str] = []
    cursor = 0
    for match in sorted(matches, key=lambda item: item.start):
        pieces.append(text[cursor : match.start])
        pieces.append(match.canonical_value)
        cursor = match.end
    pieces.append(text[cursor:])
    return "".join(pieces)


def _slots_for_matches(matches: list[_CandidateMatch]) -> dict[str, list[str]]:
    slots: dict[str, set[str]] = {}
    for match in matches:
        slots.setdefault(match.slot, set()).add(match.canonical_value)
    return {slot: sorted(values) for slot, values in sorted(slots.items())}


def _match_response(match: _CandidateMatch) -> TextCanonicalizeMatch:
    return TextCanonicalizeMatch(
        alias_value=match.alias_value,
        canonical_value=match.canonical_value,
        slot=match.slot,
        matched_text=match.matched_text,
        start=match.start,
        end=match.end,
        confidence=match.confidence,
        source="alias",
    )
