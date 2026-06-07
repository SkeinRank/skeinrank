"""Zero-friction public facade for local SkeinRank canonicalization.

The facade is intentionally deterministic and dependency-light. It does not call
OpenRouter, the Governance API, Elasticsearch, Celery, or optional ML adapters.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .dictionary_spec import DICTIONARY_SCHEMA_VERSION
from .sdk import (
    CanonicalizedText,
    Dictionary,
    ExtractionResult,
    canonicalize_text,
    extract_terms,
    load_dictionary,
)

DictionarySource = str | Path | Mapping[str, Any] | Dictionary | None
SimpleDictionaryValue = str | Sequence[str] | Mapping[str, Any]
SimpleDictionary = Mapping[str, SimpleDictionaryValue]

_DEMO_DICTIONARY_PAYLOAD: dict[str, Any] = {
    "schema_version": DICTIONARY_SCHEMA_VERSION,
    "profile_name": "platform_ops_demo",
    "profile_description": (
        "Built-in demo terminology for zero-friction SkeinRank SDK examples."
    ),
    "terms": [
        {
            "canonical_value": "kubernetes",
            "slot": "TECHNOLOGY",
            "tags": ["infrastructure", "orchestration"],
            "aliases": ["k8s", "kube", "kuber"],
        },
        {
            "canonical_value": "postgresql",
            "slot": "DATABASE",
            "tags": ["database", "storage"],
            "aliases": ["pg", "postgres", "psql"],
        },
        {
            "canonical_value": "redis",
            "slot": "CACHE",
            "tags": ["cache", "storage"],
            "aliases": ["redis cache", "cache"],
        },
        {
            "canonical_value": "elasticsearch",
            "slot": "SEARCH_BACKEND",
            "tags": ["search", "index"],
            "aliases": ["es", "elastic"],
        },
        {
            "canonical_value": "opensearch",
            "slot": "SEARCH_BACKEND",
            "tags": ["search", "index"],
            "aliases": ["os search", "open search"],
        },
        {
            "canonical_value": "api server",
            "slot": "COMPONENT",
            "tags": ["backend", "service"],
            "aliases": ["api-server", "apiserver"],
        },
        {
            "canonical_value": "authentication",
            "slot": "SECURITY_CONCEPT",
            "tags": ["security", "identity"],
            "aliases": ["authn"],
        },
        {
            "canonical_value": "authorization",
            "slot": "SECURITY_CONCEPT",
            "tags": ["security", "identity"],
            "aliases": ["authz"],
        },
        {
            "canonical_value": "github actions",
            "slot": "CI_SYSTEM",
            "tags": ["ci", "automation"],
            "aliases": ["gh actions", "gha"],
        },
        {
            "canonical_value": "critical incident",
            "slot": "SEVERITY",
            "tags": ["incident", "priority"],
            "aliases": ["sev1", "sev-1", "p0"],
        },
        {
            "canonical_value": "deployment",
            "slot": "CHANGE_TYPE",
            "tags": ["release", "operations"],
            "aliases": ["deploy", "rollout"],
        },
        {
            "canonical_value": "rollback",
            "slot": "CHANGE_ACTION",
            "tags": ["release", "operations"],
            "aliases": ["revert", "roll back"],
        },
        {
            "canonical_value": "timeout",
            "slot": "SYMPTOM",
            "tags": ["incident", "latency"],
            "aliases": ["timed out", "time out"],
        },
        {
            "canonical_value": "latency",
            "slot": "SYMPTOM",
            "tags": ["incident", "performance"],
            "aliases": ["slow", "slowness"],
        },
    ],
    "profile_stop_list": [
        {
            "value": "app",
            "target": "alias",
            "reason": "too generic for the built-in demo matcher",
        },
        {
            "value": "service",
            "target": "alias",
            "reason": "too generic for the built-in demo matcher",
        },
    ],
}


class SkeinRank:
    """Small deterministic facade for local canonicalization.

    Parameters
    ----------
    dictionary:
        Omit this argument to use the built-in demo dictionary. Pass a simple
        ``{canonical: [aliases...]}`` mapping for quick experiments, a full
        SkeinRank dictionary payload, a file path, or an existing ``Dictionary``.
    profile_name:
        Profile name used when a simple Python mapping is converted into a
        SkeinRank dictionary.
    default_slot:
        Slot assigned to simple mapping entries that do not specify one.
    """

    def __init__(
        self,
        dictionary: DictionarySource = None,
        *,
        profile_name: str = "inline_terms",
        default_slot: str = "TERM",
    ) -> None:
        self.dictionary = _coerce_dictionary(
            dictionary,
            profile_name=profile_name,
            default_slot=default_slot,
        )

    @classmethod
    def demo(cls) -> "SkeinRank":
        """Return a facade backed by the built-in platform-ops demo dictionary."""

        return cls(demo_dictionary())

    @classmethod
    def from_file(cls, path: str | Path) -> "SkeinRank":
        """Load a SkeinRank dictionary JSON/YAML file."""

        return cls(load_dictionary(path))

    def canonicalize(
        self,
        text: str,
        *,
        explain: bool = False,
        max_matches: int | None = None,
        context_chars: int = 48,
    ) -> str | CanonicalizedText:
        """Canonicalize text with this facade's dictionary.

        Returns a plain string by default. Pass ``explain=True`` to get the
        full ``CanonicalizedText`` object with replacement metadata.
        """

        result = canonicalize_text(
            text,
            dictionary=self.dictionary,
            max_matches=max_matches,
            context_chars=context_chars,
        )
        return result if explain else result.text

    def extract(
        self,
        text: str,
        *,
        explain: bool = False,
        max_matches: int | None = None,
        context_chars: int = 48,
    ) -> list[str] | ExtractionResult:
        """Extract canonical values from text.

        Returns ``list[str]`` by default. Pass ``explain=True`` to get the full
        ``ExtractionResult`` with offsets and highlighted evidence fragments.
        """

        result = extract_terms(
            text,
            dictionary=self.dictionary,
            max_matches=max_matches,
            context_chars=context_chars,
        )
        return result if explain else result.canonical_values


def canonicalize(
    text: str,
    *,
    dictionary: DictionarySource = None,
    explain: bool = False,
    max_matches: int | None = None,
    context_chars: int = 48,
) -> str | CanonicalizedText:
    """Canonicalize text with a demo or caller-supplied dictionary.

    This is the lowest-friction entrypoint:

    ``skeinrank.canonicalize("k8s pg timeout")``
    """

    return SkeinRank(dictionary).canonicalize(
        text,
        explain=explain,
        max_matches=max_matches,
        context_chars=context_chars,
    )


def extract(
    text: str,
    *,
    dictionary: DictionarySource = None,
    explain: bool = False,
    max_matches: int | None = None,
    context_chars: int = 48,
) -> list[str] | ExtractionResult:
    """Extract canonical values with a demo or caller-supplied dictionary."""

    return SkeinRank(dictionary).extract(
        text,
        explain=explain,
        max_matches=max_matches,
        context_chars=context_chars,
    )


def demo_dictionary() -> Dictionary:
    """Return a fresh built-in demo dictionary for platform-ops examples."""

    return load_dictionary(_DEMO_DICTIONARY_PAYLOAD)


def demo_dictionary_payload() -> dict[str, Any]:
    """Return a deep copy of the built-in demo dictionary payload."""

    return copy.deepcopy(_DEMO_DICTIONARY_PAYLOAD)


def _coerce_dictionary(
    source: DictionarySource,
    *,
    profile_name: str,
    default_slot: str,
) -> Dictionary:
    if source is None:
        return demo_dictionary()
    if isinstance(source, Dictionary):
        return source
    if isinstance(source, (str, Path)):
        return load_dictionary(source)
    if isinstance(source, Mapping):
        if _looks_like_dictionary_payload(source):
            return load_dictionary(source)
        return load_dictionary(
            _simple_mapping_to_dictionary_payload(
                source,
                profile_name=profile_name,
                default_slot=default_slot,
            )
        )
    raise TypeError(
        "dictionary must be omitted, a path, a Dictionary, a full dictionary "
        "payload, or a simple {canonical: aliases} mapping"
    )


def _looks_like_dictionary_payload(source: Mapping[str, Any]) -> bool:
    return any(
        key in source
        for key in (
            "schema_version",
            "profile_name",
            "profile_id",
            "terms",
            "canonical_terms",
        )
    )


def _simple_mapping_to_dictionary_payload(
    source: SimpleDictionary,
    *,
    profile_name: str,
    default_slot: str,
) -> dict[str, Any]:
    terms: list[dict[str, Any]] = []
    for canonical, raw_value in source.items():
        term = _simple_mapping_term(
            str(canonical),
            raw_value,
            default_slot=default_slot,
        )
        terms.append(term)
    return {
        "schema_version": DICTIONARY_SCHEMA_VERSION,
        "profile_name": profile_name,
        "terms": terms,
    }


def _simple_mapping_term(
    canonical: str,
    raw_value: SimpleDictionaryValue,
    *,
    default_slot: str,
) -> dict[str, Any]:
    if isinstance(raw_value, Mapping):
        aliases = raw_value.get("aliases", [])
        if isinstance(aliases, str):
            aliases = [aliases]
        return {
            "canonical_value": canonical,
            "slot": str(
                raw_value.get("slot") or raw_value.get("primary_slot") or default_slot
            ),
            "description": raw_value.get("description"),
            "tags": _string_list(raw_value.get("tags", [])),
            "aliases": _string_list(aliases),
        }
    if isinstance(raw_value, str):
        aliases = [raw_value]
    else:
        aliases = list(raw_value)
    return {
        "canonical_value": canonical,
        "slot": default_slot,
        "aliases": aliases,
    }


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, Sequence):
        return [str(item) for item in value]
    return [str(value)]
