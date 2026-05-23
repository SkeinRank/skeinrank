"""Runtime binding policy resolver for controlled alias interpretation.

The resolver keeps LLM/agent-proposed ambiguity out of the hot path until a
binding policy explicitly allows it. Active aliases remain the default runtime
source. Binding policies can then deny slots, restrict tags, prefer slots, and
select a canonical candidate for an ambiguous surface form.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from skeinrank_governance.models import (
    CanonicalTerm,
    ElasticsearchBinding,
    GovernanceAmbiguousAlias,
    GovernanceBindingPolicy,
    normalize_value,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from .runtime_snapshots import RuntimeAliasEntry


class _AliasLike(Protocol):
    alias_value: str
    normalized_alias: str
    canonical_value: str
    normalized_canonical: str
    slot: str
    confidence: float
    tags: tuple[str, ...]


@dataclass(frozen=True)
class RuntimePolicyDecision:
    """Explain one binding-policy decision made during runtime resolution."""

    surface: str
    normalized_surface: str
    selected_canonical: str | None
    selected_slot: str | None
    reason: str
    source: str
    candidates: tuple[dict[str, object], ...]

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable policy decision."""

        return {
            "surface": self.surface,
            "normalized_surface": self.normalized_surface,
            "selected_canonical": self.selected_canonical,
            "selected_slot": self.selected_slot,
            "reason": self.reason,
            "source": self.source,
            "candidates": list(self.candidates),
        }


@dataclass(frozen=True)
class RuntimePolicyResolution:
    """Runtime aliases after applying a binding policy."""

    alias_entries: list[RuntimeAliasEntry]
    decisions: list[RuntimePolicyDecision]
    warnings: list[str]


@dataclass(frozen=True)
class _RuntimeCandidate:
    alias_value: str
    normalized_alias: str
    canonical_value: str
    normalized_canonical: str
    slot: str
    confidence: float
    tags: tuple[str, ...]
    source: str
    status: str
    reason: str | None = None

    def to_entry(self) -> RuntimeAliasEntry:
        return RuntimeAliasEntry(
            alias_value=self.alias_value,
            normalized_alias=self.normalized_alias,
            canonical_value=self.canonical_value,
            normalized_canonical=self.normalized_canonical,
            slot=self.slot,
            confidence=self.confidence,
            tags=self.tags,
        )

    def to_summary(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "canonical_value": self.canonical_value,
            "normalized_canonical": self.normalized_canonical,
            "slot": self.slot,
            "tags": list(self.tags),
            "confidence": self.confidence,
            "source": self.source,
            "status": self.status,
        }
        if self.reason:
            payload["reason"] = self.reason
        return payload


def resolve_runtime_binding_policy(
    *,
    session: Session,
    binding: ElasticsearchBinding,
    alias_entries: list[_AliasLike],
) -> RuntimePolicyResolution:
    """Apply a binding policy to active/runtime aliases.

    The function is intentionally side-effect free. It reads the binding policy
    and ambiguous alias candidates, then returns a resolved alias list plus
    explainable decisions for API debug output.
    """

    policy = _active_binding_policy(binding)
    if policy is None:
        return RuntimePolicyResolution(
            alias_entries=[_alias_like_to_entry(item) for item in alias_entries],
            decisions=[],
            warnings=[],
        )

    candidate_groups = _candidate_groups_from_aliases(alias_entries)
    _extend_with_ambiguous_candidates(session, binding, candidate_groups)

    resolved_entries: list[RuntimeAliasEntry] = []
    decisions: list[RuntimePolicyDecision] = []
    warnings: list[str] = []
    for normalized_surface in sorted(candidate_groups):
        candidates = candidate_groups[normalized_surface]
        selected, decision = _select_candidate(
            policy=policy,
            normalized_surface=normalized_surface,
            candidates=candidates,
        )
        decisions.append(decision)
        if selected is not None:
            resolved_entries.append(selected.to_entry())
        else:
            warnings.append(
                "Binding policy excluded all runtime candidates for surface "
                f"{normalized_surface!r}."
            )

    return RuntimePolicyResolution(
        alias_entries=resolved_entries,
        decisions=decisions,
        warnings=warnings,
    )


def _active_binding_policy(
    binding: ElasticsearchBinding,
) -> GovernanceBindingPolicy | None:
    policy = getattr(binding, "policy", None)
    if policy is None:
        return None
    if str(policy.status or "").strip().lower() != "active":
        return None
    return policy


def _alias_like_to_entry(alias: _AliasLike) -> RuntimeAliasEntry:
    return RuntimeAliasEntry(
        alias_value=alias.alias_value,
        normalized_alias=alias.normalized_alias,
        canonical_value=alias.canonical_value,
        normalized_canonical=alias.normalized_canonical,
        slot=alias.slot,
        confidence=alias.confidence,
        tags=tuple(alias.tags or ()),
    )


def _candidate_groups_from_aliases(
    alias_entries: list[_AliasLike],
) -> dict[str, list[_RuntimeCandidate]]:
    groups: dict[str, list[_RuntimeCandidate]] = {}
    for entry in alias_entries:
        candidate = _RuntimeCandidate(
            alias_value=entry.alias_value,
            normalized_alias=entry.normalized_alias,
            canonical_value=entry.canonical_value,
            normalized_canonical=entry.normalized_canonical,
            slot=entry.slot,
            confidence=entry.confidence,
            tags=tuple(entry.tags or ()),
            source="active_alias",
            status="active",
        )
        groups.setdefault(candidate.normalized_alias, []).append(candidate)
    return groups


def _extend_with_ambiguous_candidates(
    session: Session,
    binding: ElasticsearchBinding,
    groups: dict[str, list[_RuntimeCandidate]],
) -> None:
    ambiguous_aliases = list(
        session.scalars(
            select(GovernanceAmbiguousAlias).where(
                GovernanceAmbiguousAlias.profile_id == binding.profile_id,
                GovernanceAmbiguousAlias.status == "open",
            )
        )
    )
    if not ambiguous_aliases:
        return

    term_tags = _term_tags_by_id(session, binding.profile_id)
    for ambiguous_alias in ambiguous_aliases:
        normalized_surface = ambiguous_alias.normalized_surface
        for candidate in sorted(
            ambiguous_alias.candidates,
            key=lambda item: (item.normalized_canonical, item.slot),
        ):
            if candidate.status == "rejected":
                continue
            tags = term_tags.get(candidate.term_id or -1, ())
            item = _RuntimeCandidate(
                alias_value=ambiguous_alias.surface_value,
                normalized_alias=normalized_surface,
                canonical_value=candidate.canonical_value,
                normalized_canonical=candidate.normalized_canonical,
                slot=candidate.slot,
                confidence=candidate.confidence,
                tags=tags,
                source=f"ambiguous_{candidate.source}",
                status=candidate.status,
            )
            _append_unique_candidate(groups.setdefault(normalized_surface, []), item)


def _term_tags_by_id(session: Session, profile_id: int) -> dict[int, tuple[str, ...]]:
    terms = list(
        session.scalars(
            select(CanonicalTerm).where(CanonicalTerm.profile_id == profile_id)
        )
    )
    result: dict[int, tuple[str, ...]] = {}
    for term in terms:
        result[int(term.id)] = tuple(
            sorted(
                {
                    tag.normalized_value
                    for tag in getattr(term, "tags", [])
                    if str(tag.normalized_value or "").strip()
                }
            )
        )
    return result


def _append_unique_candidate(
    candidates: list[_RuntimeCandidate], candidate: _RuntimeCandidate
) -> None:
    key = (candidate.normalized_canonical, candidate.slot)
    for existing in candidates:
        if (existing.normalized_canonical, existing.slot) == key:
            return
    candidates.append(candidate)


def _select_candidate(
    *,
    policy: GovernanceBindingPolicy,
    normalized_surface: str,
    candidates: list[_RuntimeCandidate],
) -> tuple[_RuntimeCandidate | None, RuntimePolicyDecision]:
    denied_slots = set(policy.deny_slots or [])
    allowed_tags = set(policy.allowed_tags or [])
    preferred_slots = list(policy.preferred_slots or [])
    context_rules = list(policy.context_rules or [])

    hard_filtered: list[_RuntimeCandidate] = []
    for candidate in candidates:
        if candidate.slot in denied_slots:
            continue
        if allowed_tags and not allowed_tags.intersection(candidate.tags):
            continue
        hard_filtered.append(candidate)

    selected: _RuntimeCandidate | None = None
    reason = "active_alias_default"
    source = "active_alias"

    rule = _context_rule_for_surface(context_rules, normalized_surface)
    if rule is not None:
        selected = _candidate_for_context_rule(hard_filtered, rule)
        reason = "binding_policy.context_rule"
        source = "binding_policy"
    if selected is None:
        selected = _preferred_status_candidate(hard_filtered)
        if selected is not None:
            reason = "ambiguous_candidate.preferred"
            source = selected.source
    if selected is None and preferred_slots:
        selected = _candidate_for_preferred_slots(hard_filtered, preferred_slots)
        if selected is not None:
            reason = "binding_policy.preferred_slots"
            source = "binding_policy"
    if selected is None:
        selected = _active_alias_candidate(hard_filtered)
        if selected is not None:
            reason = "active_alias_default"
            source = selected.source
    if selected is None and hard_filtered:
        selected = sorted(
            hard_filtered,
            key=lambda item: (
                -item.confidence,
                item.normalized_canonical,
                item.slot,
                item.source,
            ),
        )[0]
        reason = "candidate_confidence_fallback"
        source = selected.source
    if selected is None:
        reason = "binding_policy.no_allowed_candidate"
        source = "binding_policy"

    surface = candidates[0].alias_value if candidates else normalized_surface
    return selected, RuntimePolicyDecision(
        surface=surface,
        normalized_surface=normalized_surface,
        selected_canonical=selected.canonical_value if selected else None,
        selected_slot=selected.slot if selected else None,
        reason=reason,
        source=source,
        candidates=tuple(candidate.to_summary() for candidate in candidates),
    )


def _context_rule_for_surface(
    rules: list[dict[str, object]], normalized_surface: str
) -> dict[str, object] | None:
    for rule in rules:
        if str(rule.get("normalized_surface") or "") == normalized_surface:
            return rule
        raw_surface = str(rule.get("surface") or "").strip()
        if raw_surface and normalize_value(raw_surface) == normalized_surface:
            return rule
    return None


def _candidate_for_context_rule(
    candidates: list[_RuntimeCandidate], rule: dict[str, object]
) -> _RuntimeCandidate | None:
    preferred_canonical = str(rule.get("normalized_prefer") or "").strip()
    if not preferred_canonical:
        preferred_canonical = normalize_value(str(rule.get("prefer") or ""))
    slot_value = rule.get("slot")
    preferred_slot = str(slot_value or "").strip().upper() if slot_value else None
    for candidate in candidates:
        if candidate.normalized_canonical != preferred_canonical:
            continue
        if preferred_slot is not None and candidate.slot != preferred_slot:
            continue
        return candidate
    return None


def _preferred_status_candidate(
    candidates: list[_RuntimeCandidate],
) -> _RuntimeCandidate | None:
    preferred = [
        candidate for candidate in candidates if candidate.status == "preferred"
    ]
    if not preferred:
        return None
    return sorted(
        preferred,
        key=lambda item: (-item.confidence, item.normalized_canonical, item.slot),
    )[0]


def _candidate_for_preferred_slots(
    candidates: list[_RuntimeCandidate], preferred_slots: list[str]
) -> _RuntimeCandidate | None:
    for slot in preferred_slots:
        slot_candidates = [
            candidate for candidate in candidates if candidate.slot == slot
        ]
        if slot_candidates:
            return sorted(
                slot_candidates,
                key=lambda item: (-item.confidence, item.normalized_canonical),
            )[0]
    return None


def _active_alias_candidate(
    candidates: list[_RuntimeCandidate],
) -> _RuntimeCandidate | None:
    active = [
        candidate for candidate in candidates if candidate.source == "active_alias"
    ]
    if not active:
        return None
    return sorted(
        active,
        key=lambda item: (-item.confidence, item.normalized_canonical, item.slot),
    )[0]
