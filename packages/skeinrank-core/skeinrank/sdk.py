"""Stable public SDK for dictionary-first extraction and canonicalization.

This module is intentionally lightweight: it does not import FastAPI,
SQLAlchemy, Celery, Elasticsearch clients, or optional ML dependencies.
It accepts the same dictionary JSON/YAML shape exported by the governance Console API
and used by ``skeinrank-migrate``.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .dictionary_spec import (
    DICTIONARY_SCHEMA_VERSION,
    is_supported_dictionary_schema_version,
    load_mapping_document,
    resolve_dictionary_schema_version,
)
from .text import (
    UnicodeNormalizationResult,
    UnicodeTextFinding,
    normalize_text_for_matching,
)

_RUNTIME_ALIAS_STATUSES = frozenset({"active", "deprecated"})
_RUNTIME_TERM_STATUSES = frozenset({"active", "deprecated"})
_STOP_TARGETS = frozenset({"alias", "canonical", "both"})


class DictionaryAlias(BaseModel):
    """Alias entry attached to one canonical term."""

    value: str
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    status: str = Field(default="active")
    notes: str | None = None

    @field_validator("value")
    @classmethod
    def _non_empty_value(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("alias value must not be empty")
        return normalized

    @field_validator("status")
    @classmethod
    def _normalize_status(cls, value: str) -> str:
        return _normalize_status(value)


class DictionaryTerm(BaseModel):
    """Canonical term plus its aliases."""

    canonical_value: str
    slot: str
    description: str | None = None
    status: str = Field(default="active")
    tags: list[str] = Field(default_factory=list)
    aliases: list[DictionaryAlias] = Field(default_factory=list)

    @field_validator("canonical_value")
    @classmethod
    def _non_empty_canonical(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("canonical_value must not be empty")
        return normalized

    @field_validator("slot")
    @classmethod
    def _non_empty_slot(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("slot must not be empty")
        return normalized

    @field_validator("status")
    @classmethod
    def _normalize_status(cls, value: str) -> str:
        return _normalize_status(value)

    @field_validator("tags")
    @classmethod
    def _normalize_tags(cls, values: list[str]) -> list[str]:
        return sorted(
            {
                " ".join(value.strip().lower().split())
                for value in values
                if value.strip()
            }
        )


class DictionaryStopListEntry(BaseModel):
    """Stop-list entry applied to aliases, canonical values, or both."""

    value: str
    target: str = Field(default="both")
    reason: str | None = None
    is_active: bool = True

    @field_validator("value")
    @classmethod
    def _non_empty_value(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("stop-list value must not be empty")
        return normalized

    @field_validator("target")
    @classmethod
    def _normalize_target(cls, value: str) -> str:
        normalized = value.strip().lower().replace("-", "_") or "both"
        if normalized not in _STOP_TARGETS:
            raise ValueError("stop-list target must be alias, canonical, or both")
        return normalized


class DictionaryValidationIssue(BaseModel):
    severity: str
    code: str
    message: str
    value: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class DictionaryValidationReport(BaseModel):
    ok: bool
    profile_name: str | None = None
    error_count: int
    warning_count: int
    issues: list[DictionaryValidationIssue] = Field(default_factory=list)

    def raise_for_errors(self) -> None:
        if self.error_count:
            raise ValueError(
                f"Dictionary validation failed with {self.error_count} error(s)"
            )


class Dictionary(BaseModel):
    """Runtime dictionary loaded from a governance migration/export JSON/YAML file."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    schema_version: str = Field(default=DICTIONARY_SCHEMA_VERSION)
    profile_name: str
    profile_description: str | None = None
    terms: list[DictionaryTerm] = Field(default_factory=list)
    profile_stop_list: list[DictionaryStopListEntry] = Field(default_factory=list)
    global_stop_list: list[DictionaryStopListEntry] = Field(default_factory=list)

    @field_validator("profile_name")
    @classmethod
    def _non_empty_profile_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("profile_name must not be empty")
        return normalized

    @classmethod
    def from_file(cls, path: str | Path) -> "Dictionary":
        """Load a dictionary from a JSON file."""

        return load_dictionary(path)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "Dictionary":
        """Load a dictionary from the Console API migration/export JSON shape."""

        return _dictionary_from_payload(payload)

    def validate(self) -> DictionaryValidationReport:
        """Validate this dictionary for deterministic local extraction."""

        return validate_dictionary(self)


class TermMatch(BaseModel):
    """One dictionary match found in text."""

    canonical_value: str
    slot: str
    alias: str
    matched_text: str
    start: int
    end: int
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    source: str = Field(default="dictionary")
    fragment: str
    highlighted_fragment: str


class ExtractionResult(BaseModel):
    """Result returned by :func:`extract_terms`."""

    text: str
    profile_name: str
    matches: list[TermMatch] = Field(default_factory=list)
    canonical_values: list[str] = Field(default_factory=list)
    slots: list[str] = Field(default_factory=list)
    unicode_normalized: bool = False
    unicode_has_bidi_control: bool = False
    unicode_findings: list[UnicodeTextFinding] = Field(default_factory=list)

    @property
    def match_count(self) -> int:
        return len(self.matches)


class CanonicalizedText(BaseModel):
    """Text with matched aliases replaced by canonical values."""

    text: str
    profile_name: str
    replacements: list[TermMatch] = Field(default_factory=list)
    unicode_normalized: bool = False
    unicode_has_bidi_control: bool = False
    unicode_findings: list[UnicodeTextFinding] = Field(default_factory=list)


class _RuntimePattern(BaseModel):
    canonical_value: str
    slot: str
    alias: str
    confidence: float
    source: str
    pattern: re.Pattern[str]

    model_config = ConfigDict(arbitrary_types_allowed=True)


def load_dictionary(source: str | Path | Mapping[str, Any] | Dictionary) -> Dictionary:
    """Load a :class:`Dictionary` from a file path, mapping, or existing object.

    The accepted JSON/YAML shape matches the governance Console API export and
    the ``examples/migration/console_dictionary.example.json`` file.
    """

    if isinstance(source, Dictionary):
        return source
    if isinstance(source, Mapping):
        return _dictionary_from_payload(source)
    path = Path(source)
    payload = load_mapping_document(str(path))
    return _dictionary_from_payload(payload)


def validate_dictionary(
    source: str | Path | Mapping[str, Any] | Dictionary,
) -> DictionaryValidationReport:
    """Validate a dictionary payload before local extraction or publishing."""

    try:
        dictionary = load_dictionary(source)
    except Exception as exc:
        issue = DictionaryValidationIssue(
            severity="error",
            code="invalid_dictionary",
            message=str(exc),
        )
        return DictionaryValidationReport(
            ok=False,
            profile_name=None,
            error_count=1,
            warning_count=0,
            issues=[issue],
        )

    issues: list[DictionaryValidationIssue] = []
    canonical_seen: Counter[str] = Counter()
    alias_to_canonical: dict[str, tuple[str, str]] = {}
    stop_aliases, stop_canonicals = _stop_sets(dictionary)

    for term in dictionary.terms:
        normalized_canonical = _normalize_for_match(term.canonical_value)
        canonical_seen[normalized_canonical] += 1
        if term.status not in _RUNTIME_TERM_STATUSES:
            issues.append(
                DictionaryValidationIssue(
                    severity="warning",
                    code="non_runtime_term_status",
                    message="Term is not active/deprecated and will be ignored at runtime.",
                    value=term.canonical_value,
                    details={"status": term.status},
                )
            )
        if normalized_canonical in stop_canonicals:
            issues.append(
                DictionaryValidationIssue(
                    severity="warning",
                    code="canonical_blocked_by_stop_list",
                    message="Canonical value is blocked by a stop list.",
                    value=term.canonical_value,
                )
            )
        for alias in term.aliases:
            normalized_alias = _normalize_for_match(alias.value)
            if alias.status not in _RUNTIME_ALIAS_STATUSES:
                issues.append(
                    DictionaryValidationIssue(
                        severity="warning",
                        code="non_runtime_alias_status",
                        message="Alias is not active/deprecated and will be ignored at runtime.",
                        value=alias.value,
                        details={"status": alias.status},
                    )
                )
                continue
            if normalized_alias in stop_aliases:
                issues.append(
                    DictionaryValidationIssue(
                        severity="warning",
                        code="alias_blocked_by_stop_list",
                        message="Alias is blocked by a stop list.",
                        value=alias.value,
                    )
                )
                continue
            previous = alias_to_canonical.get(normalized_alias)
            if previous and previous != (normalized_canonical, term.slot):
                issues.append(
                    DictionaryValidationIssue(
                        severity="error",
                        code="alias_collision",
                        message="Alias maps to more than one canonical term or slot.",
                        value=alias.value,
                        details={
                            "first_canonical": previous[0],
                            "first_slot": previous[1],
                            "second_canonical": normalized_canonical,
                            "second_slot": term.slot,
                        },
                    )
                )
            else:
                alias_to_canonical[normalized_alias] = (normalized_canonical, term.slot)
            if _looks_like_replacement_form_mismatch(
                normalized_alias, normalized_canonical
            ):
                issues.append(
                    DictionaryValidationIssue(
                        severity="warning",
                        code="replacement_form_mismatch",
                        message=(
                            "Alias looks like a verb form of a noun canonical value; "
                            "replacement canonicalization may break prose grammar. "
                            "Prefer extraction/annotation mode for prose."
                        ),
                        value=alias.value,
                        details={
                            "canonical_value": term.canonical_value,
                            "recommended_mode": "extract",
                        },
                    )
                )

    for canonical, count in canonical_seen.items():
        if count > 1:
            issues.append(
                DictionaryValidationIssue(
                    severity="error",
                    code="duplicate_canonical_value",
                    message="Canonical value appears more than once.",
                    value=canonical,
                    details={"count": count},
                )
            )

    error_count = sum(1 for issue in issues if issue.severity == "error")
    warning_count = sum(1 for issue in issues if issue.severity == "warning")
    return DictionaryValidationReport(
        ok=error_count == 0,
        profile_name=dictionary.profile_name,
        error_count=error_count,
        warning_count=warning_count,
        issues=issues,
    )


def extract_terms(
    text: str,
    *,
    dictionary: str | Path | Mapping[str, Any] | Dictionary,
    max_matches: int | None = None,
    context_chars: int = 48,
) -> ExtractionResult:
    """Extract dictionary matches from text.

    This is a deterministic local SDK function. It does not call the governance
    API, Elasticsearch, or optional ML adapters.
    """

    runtime_dictionary = load_dictionary(dictionary)
    normalization = normalize_text_for_matching(text)
    search_views = _search_views(normalization)
    matches: list[TermMatch] = []
    occupied_spans: list[tuple[int, int]] = []
    seen_matches: set[tuple[int, int, str, str]] = set()
    for pattern in _runtime_patterns(runtime_dictionary):
        for search_text, index_map in search_views:
            for raw_match in pattern.pattern.finditer(search_text):
                normalized_start, normalized_end = raw_match.span()
                start, end = _original_span(index_map, normalized_start, normalized_end)
                identity = (start, end, pattern.canonical_value, pattern.alias)
                if identity in seen_matches:
                    continue
                seen_matches.add(identity)
                if _overlaps((start, end), occupied_spans):
                    continue
                matched_text = text[start:end]
                match = TermMatch(
                    canonical_value=pattern.canonical_value,
                    slot=pattern.slot,
                    alias=pattern.alias,
                    matched_text=matched_text,
                    start=start,
                    end=end,
                    confidence=pattern.confidence,
                    source=pattern.source,
                    fragment=_fragment(text, start, end, context_chars=context_chars),
                    highlighted_fragment=_highlighted_fragment(
                        text, start, end, context_chars=context_chars
                    ),
                )
                matches.append(match)
                occupied_spans.append((start, end))
                if max_matches is not None and len(matches) >= max_matches:
                    return _extraction_result(
                        text, runtime_dictionary, matches, normalization
                    )

    matches.sort(key=lambda item: (item.start, item.end, item.canonical_value))
    return _extraction_result(text, runtime_dictionary, matches, normalization)


def canonicalize_text(
    text: str,
    *,
    dictionary: str | Path | Mapping[str, Any] | Dictionary,
    max_matches: int | None = None,
    context_chars: int = 48,
) -> CanonicalizedText:
    """Replace matched aliases in text with canonical values.

    Overlapping matches are resolved by the same deterministic matcher used by
    :func:`extract_terms`.
    """

    result = extract_terms(
        text,
        dictionary=dictionary,
        max_matches=max_matches,
        context_chars=context_chars,
    )
    if not result.matches:
        runtime_dictionary = load_dictionary(dictionary)
        return CanonicalizedText(
            text=text,
            profile_name=runtime_dictionary.profile_name,
            unicode_normalized=result.unicode_normalized,
            unicode_has_bidi_control=result.unicode_has_bidi_control,
            unicode_findings=result.unicode_findings,
        )

    pieces: list[str] = []
    cursor = 0
    for match in result.matches:
        pieces.append(text[cursor : match.start])
        pieces.append(match.canonical_value)
        cursor = match.end
    pieces.append(text[cursor:])
    return CanonicalizedText(
        text="".join(pieces),
        profile_name=result.profile_name,
        replacements=result.matches,
        unicode_normalized=result.unicode_normalized,
        unicode_has_bidi_control=result.unicode_has_bidi_control,
        unicode_findings=result.unicode_findings,
    )


def _dictionary_from_payload(payload: Mapping[str, Any]) -> Dictionary:
    schema_version = resolve_dictionary_schema_version(payload)
    if not is_supported_dictionary_schema_version(payload):
        raise ValueError(
            "Unsupported dictionary schema_version: "
            f"{schema_version}. Supported version: {DICTIONARY_SCHEMA_VERSION}."
        )
    terms_payload = payload.get("terms") or payload.get("canonical_terms") or []
    if not isinstance(terms_payload, Sequence) or isinstance(
        terms_payload, (str, bytes)
    ):
        raise ValueError("terms must be a list")
    terms = [_term_from_payload(item) for item in terms_payload]
    return Dictionary(
        schema_version=schema_version,
        profile_name=str(
            payload.get("profile_name") or payload.get("profile_id") or ""
        ),
        profile_description=payload.get("profile_description")
        or payload.get("description"),
        terms=terms,
        profile_stop_list=_stop_list_from_payload(payload.get("profile_stop_list", [])),
        global_stop_list=_stop_list_from_payload(payload.get("global_stop_list", [])),
    )


def _term_from_payload(raw: Any) -> DictionaryTerm:
    if not isinstance(raw, Mapping):
        raise ValueError("term entries must be objects")
    aliases = [_alias_from_payload(item) for item in raw.get("aliases", [])]
    return DictionaryTerm(
        canonical_value=str(raw.get("canonical_value") or raw.get("canonical") or ""),
        slot=str(raw.get("slot") or ""),
        description=raw.get("description"),
        status=_normalize_status(str(raw.get("status", "active"))),
        tags=[str(item) for item in raw.get("tags", [])],
        aliases=aliases,
    )


def _alias_from_payload(raw: Any) -> DictionaryAlias:
    if isinstance(raw, str):
        return DictionaryAlias(value=raw)
    if not isinstance(raw, Mapping):
        raise ValueError("alias entries must be strings or objects")
    return DictionaryAlias(
        value=str(raw.get("value") or raw.get("alias_value") or raw.get("alias") or ""),
        confidence=float(raw.get("confidence", 1.0)),
        status=_normalize_status(str(raw.get("status", "active"))),
        notes=raw.get("notes"),
    )


def _stop_list_from_payload(raw_entries: Any) -> list[DictionaryStopListEntry]:
    if raw_entries is None:
        return []
    if not isinstance(raw_entries, Sequence) or isinstance(raw_entries, (str, bytes)):
        raise ValueError("stop list must be a list")
    entries: list[DictionaryStopListEntry] = []
    for raw in raw_entries:
        if isinstance(raw, str):
            entries.append(DictionaryStopListEntry(value=raw))
            continue
        if not isinstance(raw, Mapping):
            raise ValueError("stop-list entries must be strings or objects")
        entries.append(
            DictionaryStopListEntry(
                value=str(raw.get("value") or ""),
                target=str(raw.get("target", "both")),
                reason=raw.get("reason"),
                is_active=bool(raw.get("is_active", True)),
            )
        )
    return entries


def _runtime_patterns(dictionary: Dictionary) -> list[_RuntimePattern]:
    stop_aliases, stop_canonicals = _stop_sets(dictionary)
    patterns: list[_RuntimePattern] = []
    seen_aliases: set[str] = set()
    for term in dictionary.terms:
        if term.status not in _RUNTIME_TERM_STATUSES:
            continue
        normalized_canonical = _normalize_for_match(term.canonical_value)
        if normalized_canonical in stop_canonicals:
            continue
        values = [
            DictionaryAlias(
                value=term.canonical_value,
                confidence=1.0,
                status=term.status,
            ),
            *term.aliases,
        ]
        for alias in values:
            if alias.status not in _RUNTIME_ALIAS_STATUSES:
                continue
            normalized_alias = _normalize_for_match(alias.value)
            if not normalized_alias or normalized_alias in stop_aliases:
                continue
            if normalized_alias in seen_aliases:
                continue
            seen_aliases.add(normalized_alias)
            patterns.append(
                _RuntimePattern(
                    canonical_value=_normalize_for_match(term.canonical_value),
                    slot=term.slot,
                    alias=normalized_alias,
                    confidence=alias.confidence,
                    source="canonical"
                    if normalized_alias == normalized_canonical
                    else "alias",
                    pattern=_compile_alias_pattern(normalized_alias),
                )
            )
    # Longest aliases first avoids accepting "kube" before "kube api" when both
    # are present. Later result sorting restores text order for callers.
    patterns.sort(key=lambda item: (-len(item.alias), item.alias, item.canonical_value))
    return patterns


def _stop_sets(dictionary: Dictionary) -> tuple[set[str], set[str]]:
    alias_values: set[str] = set()
    canonical_values: set[str] = set()
    for entry in [*dictionary.global_stop_list, *dictionary.profile_stop_list]:
        if not entry.is_active:
            continue
        normalized = _normalize_for_match(entry.value)
        if entry.target in {"alias", "both"}:
            alias_values.add(normalized)
        if entry.target in {"canonical", "both"}:
            canonical_values.add(normalized)
    return alias_values, canonical_values


def _compile_alias_pattern(alias: str) -> re.Pattern[str]:
    return re.compile(rf"(?<!\w){re.escape(alias)}(?!\w)")


def _normalize_status(value: str) -> str:
    return value.strip().lower().replace("-", "_") or "active"


def _normalize_for_match(value: str) -> str:
    normalization = normalize_text_for_matching(value)
    normalized_text, _ = _lower_with_map(
        normalization.normalized_text, normalization.index_map
    )
    return normalized_text.strip()


def _search_views(
    normalization: UnicodeNormalizationResult,
) -> tuple[tuple[str, tuple[int, ...]], ...]:
    primary = _lower_with_map(normalization.normalized_text, normalization.index_map)
    compact = _lower_with_map(
        normalization.compact_text, normalization.compact_index_map
    )
    if compact == primary:
        return (primary,)
    return (primary, compact)


def _lower_with_map(
    text: str, index_map: tuple[int, ...]
) -> tuple[str, tuple[int, ...]]:
    lowered_chars: list[str] = []
    lowered_map: list[int] = []
    for char, source_index in zip(text, index_map):
        lowered = char.lower()
        for lowered_char in lowered:
            lowered_chars.append(lowered_char)
            lowered_map.append(source_index)
    return "".join(lowered_chars), tuple(lowered_map)


def _original_span(index_map: tuple[int, ...], start: int, end: int) -> tuple[int, int]:
    if start < 0 or end <= start or end > len(index_map):
        raise ValueError("normalized match span is outside the input text")
    return index_map[start], index_map[end - 1] + 1


def _looks_like_replacement_form_mismatch(alias: str, canonical: str) -> bool:
    if (
        alias == canonical
        or not alias.isascii()
        or not canonical.isascii()
        or not alias.isalpha()
        or not canonical.isalpha()
    ):
        return False

    candidates: set[str] = set()
    if canonical.endswith("ment") and len(canonical) > len("ment") + 2:
        candidates.add(canonical[: -len("ment")])
    if canonical.endswith("ization") and len(canonical) > len("ization") + 2:
        candidates.add(f"{canonical[: -len('ization')]}ize")
    if canonical.endswith("isation") and len(canonical) > len("isation") + 2:
        candidates.add(f"{canonical[: -len('isation')]}ise")
    if canonical.endswith("ation") and len(canonical) > len("ation") + 2:
        stem = canonical[: -len("ation")]
        candidates.update({f"{stem}ate", f"{stem}e"})
    if canonical.endswith("ing") and len(canonical) > len("ing") + 2:
        stem = canonical[: -len("ing")]
        candidates.update({stem, f"{stem}e"})
    return alias in candidates


def _overlaps(span: tuple[int, int], spans: Sequence[tuple[int, int]]) -> bool:
    start, end = span
    return any(
        start < other_end and end > other_start for other_start, other_end in spans
    )


def _fragment(text: str, start: int, end: int, *, context_chars: int) -> str:
    left = max(0, start - context_chars)
    right = min(len(text), end + context_chars)
    prefix = "…" if left > 0 else ""
    suffix = "…" if right < len(text) else ""
    return f"{prefix}{text[left:right]}{suffix}"


def _highlighted_fragment(
    text: str, start: int, end: int, *, context_chars: int
) -> str:
    left = max(0, start - context_chars)
    right = min(len(text), end + context_chars)
    prefix = "…" if left > 0 else ""
    suffix = "…" if right < len(text) else ""
    before = text[left:start]
    matched = text[start:end]
    after = text[end:right]
    return f"{prefix}{before}<mark>{matched}</mark>{after}{suffix}"


def _extraction_result(
    text: str,
    dictionary: Dictionary,
    matches: list[TermMatch],
    normalization: UnicodeNormalizationResult,
) -> ExtractionResult:
    canonical_values = _unique_in_order(match.canonical_value for match in matches)
    slots = _unique_in_order(match.slot for match in matches)
    return ExtractionResult(
        text=text,
        profile_name=dictionary.profile_name,
        matches=matches,
        canonical_values=canonical_values,
        slots=slots,
        unicode_normalized=normalization.changed,
        unicode_has_bidi_control=normalization.has_bidi_control,
        unicode_findings=list(normalization.findings),
    )


def _unique_in_order(values: Sequence[str] | Any) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
