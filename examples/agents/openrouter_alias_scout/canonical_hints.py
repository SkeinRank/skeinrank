"""Canonical hint helpers for the OpenRouter alias scout example.

Patch 41A keeps the alias scout deterministic before LLM review by giving the
model a compact list of known canonical terms and alias-to-canonical hints. The
hints are local config data in this reference implementation; a later production
patch can source the same shape from SkeinRank profiles/snapshots.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

JsonDict = dict[str, Any]


@dataclass(frozen=True)
class CanonicalTermHint:
    """A known canonical term and its configured alias hints."""

    canonical_value: str
    slot: str | None = None
    aliases: tuple[str, ...] = field(default_factory=tuple)
    tags: tuple[str, ...] = field(default_factory=tuple)
    description: str | None = None

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "CanonicalTermHint":
        """Create a term hint from config JSON."""

        canonical = str(
            raw.get("canonical_value") or raw.get("canonical") or ""
        ).strip()
        if not canonical:
            raise ValueError("canonical_hints.terms[].canonical_value is required")
        return cls(
            canonical_value=canonical,
            slot=_optional_string(raw.get("slot")),
            aliases=_string_tuple(raw.get("aliases")),
            tags=_string_tuple(raw.get("tags")),
            description=_optional_string(raw.get("description")),
        )

    def to_dict(self) -> JsonDict:
        """Return a compact JSON-serializable canonical term hint."""

        payload: JsonDict = {"canonical_value": self.canonical_value}
        if self.slot:
            payload["slot"] = self.slot
        if self.aliases:
            payload["aliases"] = list(self.aliases)
        if self.tags:
            payload["tags"] = list(self.tags)
        if self.description:
            payload["description"] = self.description
        return payload


@dataclass(frozen=True)
class CanonicalHintsConfig:
    """Local canonical hints included in LLM review packs."""

    terms: tuple[CanonicalTermHint, ...] = ()
    known_conflicts: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    max_known_canonicals_in_pack: int = 20

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any] | None) -> "CanonicalHintsConfig":
        """Create config from optional JSON config values."""

        if not raw:
            return cls()
        terms_raw = raw.get("terms", [])
        if not isinstance(terms_raw, list):
            raise ValueError("canonical_hints.terms must be a list")
        terms = tuple(
            CanonicalTermHint.from_mapping(item)
            for item in terms_raw
            if isinstance(item, Mapping)
        )
        if len(terms) != len(terms_raw):
            raise ValueError("canonical_hints.terms entries must be objects")

        conflicts_raw = raw.get("known_conflicts", {})
        if not isinstance(conflicts_raw, Mapping):
            raise ValueError("canonical_hints.known_conflicts must be an object")
        conflicts = {
            _normalize_surface(str(surface)): tuple(
                _clean_string(item) for item in values if _clean_string(item)
            )
            for surface, values in conflicts_raw.items()
            if isinstance(values, list)
        }
        return cls(
            terms=terms,
            known_conflicts=conflicts,
            max_known_canonicals_in_pack=int(
                raw.get(
                    "max_known_canonicals_in_pack", cls.max_known_canonicals_in_pack
                )
            ),
        )

    def to_report(self) -> JsonDict:
        """Return a compact report-friendly representation."""

        return {
            "terms_loaded": len(self.terms),
            "aliases_loaded": len(self.alias_lookup()),
            "conflict_surfaces": sorted(self.known_conflicts),
            "max_known_canonicals_in_pack": self.max_known_canonicals_in_pack,
        }

    def alias_lookup(self) -> dict[str, list[CanonicalTermHint]]:
        """Build normalized alias surface -> possible canonical terms mapping."""

        lookup: dict[str, list[CanonicalTermHint]] = {}
        for term in self.terms:
            surfaces = [term.canonical_value, *term.aliases]
            for surface in surfaces:
                normalized = _normalize_surface(surface)
                if not normalized:
                    continue
                lookup.setdefault(normalized, []).append(term)
        return lookup

    def canonical_choices(self) -> list[JsonDict]:
        """Return the compact canonical choice list exposed to the LLM."""

        return [
            term.to_dict()
            for term in self.terms[: max(self.max_known_canonicals_in_pack, 0)]
        ]


def enrich_candidate_pack_with_canonical_hints(
    candidate_pack: Mapping[str, Any],
    config: CanonicalHintsConfig | None,
) -> JsonDict:
    """Add canonical hints to an existing LLM candidate pack.

    The function never invents a mapping. It only mirrors explicit config hints
    and keeps ambiguity visible through ``canonical_candidates`` and
    ``known_conflicts``.
    """

    cfg = config or CanonicalHintsConfig()
    pack: JsonDict = dict(candidate_pack)
    candidate_alias = str(pack.get("candidate_alias", "")).strip()
    normalized_alias = _normalize_surface(candidate_alias)
    known_canonicals = cfg.canonical_choices()
    if known_canonicals:
        pack["known_canonicals"] = known_canonicals

    alias_matches = cfg.alias_lookup().get(normalized_alias, [])
    canonical_candidates = [term.to_dict() for term in alias_matches]
    if canonical_candidates:
        pack["canonical_candidates"] = canonical_candidates
        pack["canonical_hint"] = {
            "matched_alias": candidate_alias,
            "candidate_count": len(canonical_candidates),
            "confidence": 0.9 if len(canonical_candidates) == 1 else 0.55,
            "reason": (
                "single_configured_alias_match"
                if len(canonical_candidates) == 1
                else "multiple_configured_alias_matches"
            ),
        }
    elif known_canonicals:
        pack["canonical_hint"] = {
            "matched_alias": candidate_alias,
            "candidate_count": 0,
            "confidence": 0.0,
            "reason": "no_configured_alias_match",
        }

    if len(alias_matches) == 1:
        term = alias_matches[0]
        pack["possible_canonical"] = (
            pack.get("possible_canonical") or term.canonical_value
        )
        pack["slot"] = pack.get("slot") or term.slot

    conflicts = list(pack.get("known_conflicts") or [])
    configured_conflicts = list(cfg.known_conflicts.get(normalized_alias, ()))
    merged_conflicts = _dedupe_strings([*conflicts, *configured_conflicts])
    if merged_conflicts:
        pack["known_conflicts"] = merged_conflicts

    return pack


def build_canonical_hints_report(config: CanonicalHintsConfig) -> JsonDict:
    """Build an offline CLI report for local validation."""

    return {
        "schema_version": "skeinrank.agent_canonical_hints.v1",
        "runner": "openrouter_alias_scout",
        "llm_enabled": False,
        "openrouter_calls": False,
        "skeinrank_api_calls": False,
        "canonical_hints": config.to_report(),
        "known_canonicals": config.canonical_choices(),
    }


def _normalize_surface(value: str) -> str:
    return " ".join(value.strip().lower().split())


def _string_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError("canonical hint string collections must be string lists")
    return tuple(item.strip() for item in value if item.strip())


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _clean_string(value: Any) -> str:
    return str(value).strip()


def _dedupe_strings(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        cleaned = value.strip()
        key = cleaned.lower()
        if not cleaned or key in seen:
            continue
        seen.add(key)
        result.append(cleaned)
    return result
