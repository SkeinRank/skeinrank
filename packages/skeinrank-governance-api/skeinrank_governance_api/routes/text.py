"""Runtime text canonicalization endpoints."""

from __future__ import annotations

import re
from dataclasses import dataclass

from fastapi import APIRouter, Depends, HTTPException, Request, status
from skeinrank_governance.models import (
    CanonicalTerm,
    ElasticsearchBinding,
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
from ..observability import start_span, trace_query_text
from ..runtime_policy import RuntimePolicyDecision, resolve_runtime_binding_policy
from ..runtime_snapshots import (
    active_runtime_alias_entries,
    alias_entries_from_snapshot,
    build_runtime_snapshot_payload,
)
from ..schemas import (
    RuntimeContextResponse,
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
    tags: tuple[str, ...] = ()
    context_triggers: tuple[str, ...] = ()


@dataclass(frozen=True)
class _CandidateMatch:
    alias_value: str
    canonical_value: str
    slot: str
    tags: tuple[str, ...]
    context_triggers: tuple[str, ...]
    matched_context_triggers: tuple[str, ...]
    matched_text: str
    start: int
    end: int
    confidence: float
    source: str = "alias"
    reason: str = "Alias matched active canonical term"


@dataclass(frozen=True)
class _RuntimeAliasContext:
    profile: TerminologyProfile
    binding: ElasticsearchBinding | None
    alias_entries: list[_AliasEntry]
    snapshot_version: str | None
    snapshot_source: str
    warnings: list[str]
    policy_decisions: list[RuntimePolicyDecision]


@router.post("/canonicalize", response_model=TextCanonicalizeResponse)
def canonicalize_text(
    request: TextCanonicalizeRequest,
    http_request: Request,
    _current_user: AuthContext = Depends(
        require_roles("admin", "moderator", "contributor")
    ),
    session: Session = Depends(get_session),
) -> TextCanonicalizeResponse:
    """Canonicalize aliases and jargon in a text using profile or binding context."""

    mode = request.mode.strip().lower()
    if mode not in _CANONICALIZE_MODES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                "Invalid canonicalization mode. "
                "Expected one of: annotate, replace, attributes."
            ),
        )

    config = http_request.app.state.config
    with start_span(
        "runtime.text_canonicalize",
        {
            "skeinrank.runtime.endpoint": "text_canonicalize",
            "skeinrank.binding_id": request.binding_id,
            "skeinrank.profile_name": request.profile_name,
            "skeinrank.canonicalize_mode": mode,
            **trace_query_text(config, request.text),
        },
    ):
        context = _resolve_runtime_alias_context(
            session=session,
            profile_name=request.profile_name,
            binding_id=request.binding_id,
            binding_name=request.binding_name,
        )
        candidate_matches = _find_alias_matches(request.text, context.alias_entries)
        matches = _select_non_overlapping_matches(
            candidate_matches, request.max_matches
        )

    canonical_text = request.text
    replacements: list[TextCanonicalizeMatch] = []
    if mode == "replace":
        canonical_text = _replace_matches(request.text, matches)
        replacements = [_match_response(match) for match in matches]
    elif mode == "annotate":
        replacements = [_match_response(match) for match in matches]

    canonical_values = sorted({match.canonical_value for match in matches})
    slots = _slots_for_matches(matches)
    tags = _tags_for_matches(matches)
    matched_aliases = sorted({match.alias_value for match in matches})
    evidence = (
        [
            TextCanonicalizeEvidence(
                reason=match.reason,
                alias_value=match.alias_value,
                canonical_value=match.canonical_value,
                slot=match.slot,
                tags=list(match.tags),
                context_triggers=list(match.context_triggers),
                matched_context_triggers=list(match.matched_context_triggers),
                matched_text=match.matched_text,
                start=match.start,
                end=match.end,
                confidence=match.confidence,
                source=match.source,
            )
            for match in matches
        ]
        if request.include_evidence
        else []
    )

    warnings: list[str] = list(context.warnings)
    if candidate_matches and len(matches) < len(candidate_matches):
        warnings.append(
            "Some overlapping or extra matches were omitted from replacements."
        )
    if not context.alias_entries:
        warnings.append("No active aliases are available for this runtime context.")
    if not matches:
        warnings.append("No active aliases matched the input text.")

    return TextCanonicalizeResponse(
        profile_name=context.profile.name,
        normalized_profile_name=context.profile.normalized_name,
        mode=mode,
        binding_id=context.binding.id if context.binding is not None else None,
        binding_name=context.binding.name if context.binding is not None else None,
        snapshot_version=context.snapshot_version,
        snapshot_source=context.snapshot_source,
        runtime_context=_runtime_context_response(
            context, application_scope=request.application_scope
        ),
        original_text=request.text,
        canonical_text=canonical_text,
        changed=canonical_text != request.text,
        canonical_values=canonical_values,
        slots=slots,
        tags=tags,
        matched_aliases=matched_aliases,
        replacements=replacements,
        evidence=evidence,
        warnings=warnings,
        policy_decisions=_policy_decisions_for_matches(
            context.policy_decisions, matches
        ),
    )


def _resolve_runtime_alias_context(
    *,
    session: Session,
    profile_name: str | None,
    binding_id: int | None,
    binding_name: str | None = None,
) -> _RuntimeAliasContext:
    """Resolve aliases for latest profile preview or binding-pinned runtime mode."""

    warnings: list[str] = []
    if binding_id is not None or binding_name is not None:
        binding = _get_binding_or_404(
            session, binding_id=binding_id, binding_name=binding_name
        )
        if profile_name is not None and (
            binding.profile.normalized_name != normalize_profile_name(profile_name)
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Binding does not belong to the requested profile.",
            )
        alias_entries = _alias_entries_from_binding_snapshot(binding)
        if alias_entries:
            resolution = _apply_binding_policy(
                session=session, binding=binding, alias_entries=alias_entries
            )
            warnings.extend(resolution.warnings)
            return _RuntimeAliasContext(
                profile=binding.profile,
                binding=binding,
                alias_entries=resolution.alias_entries,
                snapshot_version=binding.last_successful_snapshot_version,
                snapshot_source="binding_runtime_snapshot",
                warnings=warnings,
                policy_decisions=resolution.policy_decisions,
            )
        warnings.append(
            "Binding has no runtime snapshot yet; latest profile state was used."
        )
        latest_snapshot = build_runtime_snapshot_payload(session, binding.profile)
        latest_entries = _alias_entries_from_runtime_entries(
            active_runtime_alias_entries(session, binding.profile)
        )
        resolution = _apply_binding_policy(
            session=session, binding=binding, alias_entries=latest_entries
        )
        warnings.extend(resolution.warnings)
        return _RuntimeAliasContext(
            profile=binding.profile,
            binding=binding,
            alias_entries=resolution.alias_entries,
            snapshot_version=str(latest_snapshot["version"]),
            snapshot_source="latest_profile",
            warnings=warnings,
            policy_decisions=resolution.policy_decisions,
        )

    if profile_name is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Either binding_id, binding_name, or profile_name is required.",
        )
    profile = _get_profile_or_404(session, profile_name)
    latest_snapshot = build_runtime_snapshot_payload(session, profile)
    return _RuntimeAliasContext(
        profile=profile,
        binding=None,
        alias_entries=_active_alias_entries_for_profile(session, profile),
        snapshot_version=str(latest_snapshot["version"]),
        snapshot_source="latest_profile",
        warnings=warnings,
        policy_decisions=[],
    )


def _get_binding_or_404(
    session: Session,
    *,
    binding_id: int | None = None,
    binding_name: str | None = None,
) -> ElasticsearchBinding:
    if binding_id is None and binding_name is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Either binding_id or binding_name is required.",
        )

    binding_by_id: ElasticsearchBinding | None = None
    if binding_id is not None:
        binding_by_id = session.scalar(
            select(ElasticsearchBinding).where(ElasticsearchBinding.id == binding_id)
        )
        if binding_by_id is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Elasticsearch binding not found: {binding_id}",
            )

    if binding_name is None:
        assert binding_by_id is not None
        return binding_by_id

    normalized_name = normalize_profile_name(binding_name)
    binding_by_name = session.scalar(
        select(ElasticsearchBinding).where(
            ElasticsearchBinding.normalized_name == normalized_name
        )
    )
    if binding_by_name is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Elasticsearch binding not found: {binding_name}",
        )
    if binding_by_id is not None and binding_by_id.id != binding_by_name.id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="binding_id and binding_name refer to different bindings.",
        )
    return binding_by_name


def _runtime_context_response(
    context: _RuntimeAliasContext, *, application_scope: dict[str, object] | None = None
) -> RuntimeContextResponse:
    binding = context.binding
    if binding is None:
        mode = "profile_preview"
    elif context.snapshot_source == "binding_runtime_snapshot":
        mode = "binding_runtime"
    else:
        mode = "binding_latest_profile"
    return RuntimeContextResponse(
        mode=mode,
        profile_name=context.profile.name,
        normalized_profile_name=context.profile.normalized_name,
        binding_id=binding.id if binding is not None else None,
        binding_name=binding.name if binding is not None else None,
        normalized_binding_name=(
            binding.normalized_name if binding is not None else None
        ),
        index_name=binding.index_name if binding is not None else None,
        text_fields=list(binding.text_fields) if binding is not None else [],
        target_field=binding.target_field if binding is not None else None,
        filter_field=binding.filter_field if binding is not None else None,
        filter_value=binding.filter_value if binding is not None else None,
        snapshot_version=context.snapshot_version,
        snapshot_source=context.snapshot_source,
        application_scope=_sanitize_application_scope(application_scope or {}),
    )


def _sanitize_application_scope(scope: dict[str, object]) -> dict[str, object]:
    sanitized: dict[str, object] = {}
    for key, value in scope.items():
        normalized_key = str(key).strip()
        if not normalized_key:
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            sanitized[normalized_key] = value
        else:
            sanitized[normalized_key] = str(value)
    return sanitized


def _alias_entries_from_binding_snapshot(
    binding: ElasticsearchBinding,
) -> list[_AliasEntry]:
    if not isinstance(binding.runtime_snapshot_json, dict):
        return []
    return _alias_entries_from_runtime_entries(
        alias_entries_from_snapshot(binding.runtime_snapshot_json)
    )


def _alias_entries_from_runtime_entries(entries) -> list[_AliasEntry]:
    return [
        _AliasEntry(
            alias_value=entry.alias_value,
            normalized_alias=entry.normalized_alias,
            canonical_value=entry.canonical_value,
            normalized_canonical=entry.normalized_canonical,
            slot=entry.slot,
            confidence=entry.confidence,
            tags=tuple(getattr(entry, "tags", ()) or ()),
            context_triggers=tuple(getattr(entry, "context_triggers", ()) or ()),
        )
        for entry in entries
    ]


@dataclass(frozen=True)
class _PolicyResolutionView:
    alias_entries: list[_AliasEntry]
    policy_decisions: list[RuntimePolicyDecision]
    warnings: list[str]


def _apply_binding_policy(
    *, session: Session, binding: ElasticsearchBinding, alias_entries: list[_AliasEntry]
) -> _PolicyResolutionView:
    resolution = resolve_runtime_binding_policy(
        session=session, binding=binding, alias_entries=alias_entries
    )
    return _PolicyResolutionView(
        alias_entries=_alias_entries_from_runtime_entries(resolution.alias_entries),
        policy_decisions=resolution.decisions,
        warnings=resolution.warnings,
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
                tags=_tags_for_term(alias.term),
                context_triggers=_normalize_context_triggers(
                    getattr(alias, "context_triggers", []) or []
                ),
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
    normalized_text = normalize_value(text)
    for alias_entry in alias_entries:
        matched_context_triggers = _matched_context_triggers(
            normalized_text, alias_entry.context_triggers
        )
        if alias_entry.context_triggers and not matched_context_triggers:
            continue
        pattern = _alias_pattern(alias_entry.alias_value)
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            reason = "Alias matched active canonical term"
            source = "alias"
            confidence = alias_entry.confidence
            if alias_entry.context_triggers:
                reason = (
                    "Alias matched active canonical term with context trigger(s): "
                    + ", ".join(matched_context_triggers)
                )
                source = "alias_context_trigger"
            matches.append(
                _CandidateMatch(
                    alias_value=alias_entry.alias_value,
                    canonical_value=alias_entry.canonical_value,
                    slot=alias_entry.slot,
                    tags=alias_entry.tags,
                    context_triggers=alias_entry.context_triggers,
                    matched_context_triggers=matched_context_triggers,
                    matched_text=match.group(0),
                    start=match.start(),
                    end=match.end(),
                    confidence=confidence,
                    source=source,
                    reason=reason,
                )
            )
    return sorted(
        matches,
        key=lambda item: (item.start, -(item.end - item.start), item.alias_value),
    )


def _matched_context_triggers(
    normalized_text: str, context_triggers: tuple[str, ...]
) -> tuple[str, ...]:
    if not context_triggers:
        return ()
    matched: list[str] = []
    for trigger in context_triggers:
        normalized_trigger = normalize_value(trigger)
        if not normalized_trigger:
            continue
        pattern = _alias_pattern(normalized_trigger)
        if re.search(pattern, normalized_text, flags=re.IGNORECASE):
            matched.append(normalized_trigger)
    return tuple(sorted(set(matched)))


def _normalize_context_triggers(values: list[str]) -> tuple[str, ...]:
    normalized = {normalize_value(str(value)) for value in values if str(value).strip()}
    return tuple(sorted(value for value in normalized if value))


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
    result: list[str] = []
    cursor = 0
    for match in matches:
        result.append(text[cursor : match.start])
        result.append(match.canonical_value)
        cursor = match.end
    result.append(text[cursor:])
    return "".join(result)


def _match_response(match: _CandidateMatch) -> TextCanonicalizeMatch:
    return TextCanonicalizeMatch(
        alias_value=match.alias_value,
        canonical_value=match.canonical_value,
        slot=match.slot,
        tags=list(match.tags),
        context_triggers=list(match.context_triggers),
        matched_context_triggers=list(match.matched_context_triggers),
        matched_text=match.matched_text,
        start=match.start,
        end=match.end,
        confidence=match.confidence,
        source=match.source,
    )


def _policy_decisions_for_matches(
    decisions: list[RuntimePolicyDecision], matches: list[_CandidateMatch]
) -> list[dict[str, object]]:
    matched_surfaces = {normalize_value(match.alias_value) for match in matches}
    return [
        decision.to_dict()
        for decision in decisions
        if decision.normalized_surface in matched_surfaces
    ]


def _tags_for_matches(matches: list[_CandidateMatch]) -> dict[str, list[str]]:
    tags: dict[str, set[str]] = {}
    for match in matches:
        if match.tags:
            tags.setdefault(match.canonical_value, set()).update(match.tags)
    return {canonical: sorted(values) for canonical, values in sorted(tags.items())}


def _tags_for_term(term: CanonicalTerm) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                tag.normalized_value
                for tag in getattr(term, "tags", [])
                if str(tag.normalized_value or "").strip()
            }
        )
    )


def _slots_for_matches(matches: list[_CandidateMatch]) -> dict[str, list[str]]:
    slots: dict[str, set[str]] = {}
    for match in matches:
        slots.setdefault(match.slot, set()).add(match.canonical_value)
    return {slot: sorted(values) for slot, values in sorted(slots.items())}
