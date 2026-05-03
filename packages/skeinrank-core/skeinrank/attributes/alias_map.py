from __future__ import annotations

import re
from collections import deque
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any, Iterable, Protocol

from .normalize import normalize_value
from .types import AttributeSlot


@dataclass(frozen=True)
class AliasEntry:
    alias: str
    canonical: str
    slot: AttributeSlot
    confidence: float = 0.95

    @property
    def normalized_alias(self) -> str:
        return normalize_value(self.alias)

    @property
    def normalized_canonical(self) -> str:
        return normalize_value(self.canonical)


@dataclass(frozen=True)
class AliasMatch:
    slot: AttributeSlot
    canonical: str
    alias: str
    matched_text: str
    start: int
    end: int
    confidence: float
    source: str = "alias"
    reason: str | None = None


class AliasMatcher(Protocol):
    backend_name: str

    def find(self, normalized_text: str) -> list[AliasMatch]: ...


def _is_word_char(value: str) -> bool:
    return value.isalnum() or value == "_"


def _has_word_boundaries(text: str, start: int, end: int) -> bool:
    before_ok = start == 0 or not _is_word_char(text[start - 1])
    after_ok = end >= len(text) or not _is_word_char(text[end])
    return before_ok and after_ok


_FUZZY_TOKEN_STRIP = ".,;:!?()[]{}<>\"'`"
_DEFAULT_FUZZY_GENERIC_ALIASES = frozenset(
    {
        "api",
        "app",
        "application",
        "component",
        "data",
        "error",
        "issue",
        "job",
        "node",
        "problem",
        "service",
        "system",
        "worker",
    }
)


def _overlaps(span: tuple[int, int], spans: Iterable[tuple[int, int]]) -> bool:
    start, end = span
    return any(
        start < other_end and end > other_start for other_start, other_end in spans
    )


def _iter_fuzzy_tokens(
    normalized_text: str, *, min_length: int
) -> Iterable[tuple[str, int, int]]:
    for match in re.finditer(r"\S+", normalized_text):
        raw = match.group(0)
        stripped = raw.strip(_FUZZY_TOKEN_STRIP)
        if not stripped:
            continue
        leading = len(raw) - len(raw.lstrip(_FUZZY_TOKEN_STRIP))
        start = match.start() + leading
        end = start + len(stripped)
        if len(stripped) < min_length:
            continue
        if not any(char.isalnum() for char in stripped):
            continue
        yield stripped, start, end


class SimpleAliasMatcher:
    """Small deterministic matcher used as a safe fallback."""

    backend_name = "simple"

    def __init__(self, entries: Iterable[AliasEntry]):
        self._patterns: list[tuple[AliasEntry, re.Pattern[str]]] = []
        for entry in entries:
            pattern = re.compile(rf"(?<!\w){re.escape(entry.normalized_alias)}(?!\w)")
            self._patterns.append((entry, pattern))

    def find(self, normalized_text: str) -> list[AliasMatch]:
        matches: list[AliasMatch] = []
        for entry, pattern in self._patterns:
            for match in pattern.finditer(normalized_text):
                matches.append(
                    AliasMatch(
                        slot=entry.slot,
                        canonical=entry.normalized_canonical,
                        alias=entry.normalized_alias,
                        matched_text=match.group(0),
                        start=match.start(),
                        end=match.end(),
                        confidence=entry.confidence,
                    )
                )
        return matches


@dataclass
class _AutomatonNode:
    transitions: dict[str, int] = field(default_factory=dict)
    fail: int = 0
    outputs: list[AliasEntry] = field(default_factory=list)


class AhoCorasickAliasMatcher:
    """Pure-Python Aho-Corasick matcher for fast in-memory alias lookup.

    It intentionally keeps the same word-boundary behavior as the simple regex
    matcher so existing extraction semantics do not change when the backend is
    switched from ``simple`` to ``aho_corasick``.
    """

    backend_name = "aho_corasick"

    def __init__(self, entries: Iterable[AliasEntry]):
        self._nodes = [_AutomatonNode()]
        self._build_trie(list(entries))
        self._build_failure_links()

    def _build_trie(self, entries: list[AliasEntry]) -> None:
        for entry in entries:
            alias = entry.normalized_alias
            if not alias:
                continue
            node_index = 0
            for char in alias:
                node = self._nodes[node_index]
                next_index = node.transitions.get(char)
                if next_index is None:
                    next_index = len(self._nodes)
                    node.transitions[char] = next_index
                    self._nodes.append(_AutomatonNode())
                node_index = next_index
            self._nodes[node_index].outputs.append(entry)

    def _build_failure_links(self) -> None:
        queue: deque[int] = deque()
        for child_index in self._nodes[0].transitions.values():
            self._nodes[child_index].fail = 0
            queue.append(child_index)

        while queue:
            current_index = queue.popleft()
            current = self._nodes[current_index]
            for char, child_index in current.transitions.items():
                fail_index = current.fail
                while fail_index and char not in self._nodes[fail_index].transitions:
                    fail_index = self._nodes[fail_index].fail
                self._nodes[child_index].fail = self._nodes[fail_index].transitions.get(
                    char, 0
                )
                self._nodes[child_index].outputs.extend(
                    self._nodes[self._nodes[child_index].fail].outputs
                )
                queue.append(child_index)

    def find(self, normalized_text: str) -> list[AliasMatch]:
        matches: list[AliasMatch] = []
        node_index = 0
        for position, char in enumerate(normalized_text):
            while node_index and char not in self._nodes[node_index].transitions:
                node_index = self._nodes[node_index].fail
            node_index = self._nodes[node_index].transitions.get(char, 0)

            if not self._nodes[node_index].outputs:
                continue

            for entry in self._nodes[node_index].outputs:
                alias = entry.normalized_alias
                end = position + 1
                start = end - len(alias)
                if start < 0 or not _has_word_boundaries(normalized_text, start, end):
                    continue
                matches.append(
                    AliasMatch(
                        slot=entry.slot,
                        canonical=entry.normalized_canonical,
                        alias=alias,
                        matched_text=normalized_text[start:end],
                        start=start,
                        end=end,
                        confidence=entry.confidence,
                    )
                )
        return matches


def expand_profile_aliases(raw_aliases: Iterable[dict[str, Any]]) -> list[AliasEntry]:
    """Normalize supported profile alias formats into AliasEntry objects.

    SkeinRank accepts both the original flat snapshot format::

        {"alias": "k8s", "canonical": "kubernetes", "slot": "TOOL"}

    and a more user-friendly grouped format::

        {"canonical": "kubernetes", "slot": "TOOL", "aliases": ["k8s", "kube"]}

    The grouped format is expanded at load time so the runtime matcher keeps a
    single simple internal representation.
    """
    entries: list[AliasEntry] = []
    for item in raw_aliases:
        canonical = str(item["canonical"])
        slot = AttributeSlot(str(item["slot"]))
        default_confidence = float(item.get("confidence", 0.95))

        if "alias" in item:
            entries.append(
                AliasEntry(
                    alias=str(item["alias"]),
                    canonical=canonical,
                    slot=slot,
                    confidence=default_confidence,
                )
            )
            continue

        if "aliases" not in item:
            raise ValueError(
                "Alias profile entries must define either 'alias' or 'aliases'"
            )

        raw_values = item["aliases"]
        if isinstance(raw_values, str):
            raw_values = [raw_values]

        for raw_value in raw_values:
            alias_confidence = default_confidence
            if isinstance(raw_value, dict):
                alias = raw_value.get("alias", raw_value.get("value"))
                if alias is None:
                    raise ValueError(
                        "Grouped alias objects must define 'alias' or 'value'"
                    )
                alias_confidence = float(
                    raw_value.get("confidence", default_confidence)
                )
            else:
                alias = raw_value
            entries.append(
                AliasEntry(
                    alias=str(alias),
                    canonical=canonical,
                    slot=slot,
                    confidence=alias_confidence,
                )
            )
    return entries


class AliasMap:
    def __init__(
        self, entries: Iterable[AliasEntry], *, matcher_backend: str = "simple"
    ):
        self._entries = list(entries)
        self._by_slot_alias: dict[tuple[AttributeSlot, str], AliasEntry] = {}
        self._by_alias: dict[str, AliasEntry] = {}
        for entry in self._entries:
            self._by_slot_alias[(entry.slot, entry.normalized_alias)] = entry
            self._by_alias[entry.normalized_alias] = entry
        self._matcher = self._build_matcher(matcher_backend)

    @classmethod
    def from_profile(
        cls, raw_aliases: Iterable[dict[str, Any]], *, matcher_backend: str = "simple"
    ) -> "AliasMap":
        entries = expand_profile_aliases(raw_aliases)
        return cls(entries, matcher_backend=matcher_backend)

    @property
    def matcher_backend(self) -> str:
        return self._matcher.backend_name

    @property
    def entries(self) -> tuple[AliasEntry, ...]:
        return tuple(self._entries)

    def _build_matcher(self, matcher_backend: str) -> AliasMatcher:
        normalized_backend = matcher_backend.strip().lower().replace("-", "_")
        if normalized_backend in {"aho", "aho_corasick", "ahocorasick"}:
            return AhoCorasickAliasMatcher(self._entries)
        if normalized_backend == "simple":
            return SimpleAliasMatcher(self._entries)
        return SimpleAliasMatcher(self._entries)

    def canonicalize_value(
        self, value: str, *, slot: AttributeSlot | None = None
    ) -> tuple[str, str | None, float | None]:
        normalized = normalize_value(value)
        if slot is not None:
            entry = self._by_slot_alias.get((slot, normalized))
            if entry is not None:
                return (
                    entry.normalized_canonical,
                    entry.normalized_alias,
                    entry.confidence,
                )
        entry = self._by_alias.get(normalized)
        if entry is not None and (slot is None or entry.slot == slot):
            return entry.normalized_canonical, entry.normalized_alias, entry.confidence
        return normalized, None, None

    def find(self, normalized_text: str) -> list[AliasMatch]:
        return self._matcher.find(normalized_text)

    def find_fuzzy(
        self,
        normalized_text: str,
        *,
        threshold: float = 0.9,
        min_length: int = 4,
        generic_aliases: Iterable[str] | None = None,
        excluded_spans: Iterable[tuple[int, int]] = (),
    ) -> list[AliasMatch]:
        """Find typo-like aliases with conservative string similarity.

        Fuzzy matching is intentionally opt-in and conservative. It ignores
        short aliases, multi-word aliases, and generic aliases so terms such as
        ``api`` or ``pg`` do not become noisy fuzzy candidates. Exact matching
        should always run first; ``excluded_spans`` can be used to skip text
        spans already covered by exact alias matches.
        """
        if threshold <= 0 or threshold > 1:
            raise ValueError("fuzzy threshold must be in the range (0, 1]")
        if min_length < 1:
            raise ValueError("fuzzy min_length must be >= 1")

        generic = {normalize_value(value) for value in (generic_aliases or [])}
        if not generic_aliases:
            generic = set(_DEFAULT_FUZZY_GENERIC_ALIASES)
        excluded = tuple(excluded_spans)

        candidates = [
            entry
            for entry in self._entries
            if len(entry.normalized_alias) >= min_length
            and " " not in entry.normalized_alias
            and entry.normalized_alias not in generic
        ]
        if not candidates:
            return []

        matches: list[AliasMatch] = []
        for token, start, end in _iter_fuzzy_tokens(
            normalized_text, min_length=min_length
        ):
            if _overlaps((start, end), excluded):
                continue

            best_entry: AliasEntry | None = None
            best_score = 0.0
            for entry in candidates:
                alias = entry.normalized_alias
                if token == alias:
                    continue
                score = SequenceMatcher(None, token, alias).ratio()
                if score < threshold:
                    continue
                if (
                    best_entry is None
                    or score > best_score
                    or (
                        score == best_score
                        and len(alias) > len(best_entry.normalized_alias)
                    )
                ):
                    best_entry = entry
                    best_score = score

            if best_entry is None:
                continue

            matches.append(
                AliasMatch(
                    slot=best_entry.slot,
                    canonical=best_entry.normalized_canonical,
                    alias=best_entry.normalized_alias,
                    matched_text=token,
                    start=start,
                    end=end,
                    confidence=min(best_entry.confidence, best_score),
                    source="fuzzy_alias",
                    reason="fuzzy_match",
                )
            )
        return matches
