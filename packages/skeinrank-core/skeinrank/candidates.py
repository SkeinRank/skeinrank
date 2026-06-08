"""Deterministic candidate discovery for dictionary suggestions and drift reports.

The candidate discovery engine is intentionally local and dependency-free. It
finds significant unmatched terms and phrases in documents so future workflows
can build reviewable dictionary drafts, terminology drift reports, and optional
agent-assisted grouping without changing runtime dictionaries automatically.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from .documents import extract_document_text
from .sdk import Dictionary, load_dictionary

_DEFAULT_STOP_WORDS = frozenset(
    {
        "a",
        "about",
        "above",
        "after",
        "again",
        "against",
        "all",
        "also",
        "am",
        "an",
        "and",
        "any",
        "are",
        "as",
        "at",
        "back",
        "be",
        "because",
        "been",
        "before",
        "being",
        "below",
        "between",
        "both",
        "but",
        "by",
        "can",
        "cannot",
        "case",
        "check",
        "could",
        "did",
        "do",
        "does",
        "doing",
        "done",
        "down",
        "during",
        "each",
        "error",
        "errors",
        "few",
        "for",
        "from",
        "had",
        "has",
        "have",
        "having",
        "he",
        "her",
        "here",
        "hers",
        "him",
        "his",
        "how",
        "i",
        "if",
        "in",
        "into",
        "is",
        "it",
        "its",
        "just",
        "log",
        "logs",
        "more",
        "most",
        "no",
        "nor",
        "not",
        "of",
        "off",
        "on",
        "once",
        "only",
        "or",
        "other",
        "our",
        "out",
        "over",
        "own",
        "same",
        "service",
        "services",
        "should",
        "so",
        "some",
        "status",
        "system",
        "than",
        "that",
        "the",
        "their",
        "them",
        "then",
        "there",
        "these",
        "they",
        "this",
        "those",
        "through",
        "to",
        "too",
        "under",
        "until",
        "up",
        "use",
        "used",
        "uses",
        "using",
        "was",
        "we",
        "were",
        "what",
        "when",
        "where",
        "which",
        "while",
        "who",
        "why",
        "will",
        "with",
        "within",
        "without",
        "would",
        "you",
        "your",
    }
)

_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9_])"
    r"([A-Za-z][A-Za-z0-9]*(?:[._:/-][A-Za-z0-9]+)*|[A-Z]{2,}[0-9]*|[A-Za-z]+[0-9][A-Za-z0-9]*)"
    r"(?![A-Za-z0-9_])"
)
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9]*(?:[._:/-][A-Za-z0-9]+)*")
_SEPARATOR_RE = re.compile(r"[\s._:/-]+")


class CandidateDiscoveryConfig(BaseModel):
    """Configuration for deterministic candidate discovery."""

    min_frequency: int = Field(default=2, ge=1)
    min_document_frequency: int = Field(default=1, ge=1)
    min_word_length: int = Field(default=5, ge=2)
    max_candidates: int = Field(default=50, ge=1)
    max_evidence_per_candidate: int = Field(default=3, ge=1)
    include_phrase_candidates: bool = True
    max_phrase_terms: int = Field(default=2, ge=2, le=3)
    stop_words: list[str] = Field(default_factory=lambda: sorted(_DEFAULT_STOP_WORDS))

    @field_validator("stop_words")
    @classmethod
    def _normalize_stop_words(cls, values: list[str]) -> list[str]:
        return sorted(
            {_normalize_text(value) for value in values if _normalize_text(value)}
        )

    @property
    def stop_word_set(self) -> set[str]:
        return set(self.stop_words)


class CandidateDiscoveryDocument(BaseModel):
    """Text document passed to the candidate discovery engine."""

    text: str
    source: str = "text"

    @field_validator("text")
    @classmethod
    def _non_empty_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("candidate discovery document text must not be empty")
        return value

    @field_validator("source")
    @classmethod
    def _non_empty_source(cls, value: str) -> str:
        cleaned = " ".join(str(value).strip().split())
        return cleaned or "text"


class CandidateEvidence(BaseModel):
    """One evidence snippet for a discovered candidate."""

    source: str
    line: int | None = None
    text: str

    @field_validator("source", "text")
    @classmethod
    def _clean_text(cls, value: str) -> str:
        cleaned = " ".join(str(value).strip().split())
        if not cleaned:
            raise ValueError("candidate evidence text must not be empty")
        return cleaned


class DiscoveredCandidate(BaseModel):
    """One unmatched term or phrase discovered in local text."""

    value: str
    normalized_value: str
    kind: str
    mention_count: int = Field(ge=1)
    document_count: int = Field(ge=1)
    score: float = Field(ge=0.0)
    evidence: list[CandidateEvidence] = Field(default_factory=list)

    @field_validator("value", "normalized_value", "kind")
    @classmethod
    def _non_empty_text(cls, value: str) -> str:
        cleaned = " ".join(str(value).strip().split())
        if not cleaned:
            raise ValueError("candidate fields must not be empty")
        return cleaned


class CandidateDiscoveryReport(BaseModel):
    """Result returned by deterministic candidate discovery."""

    document_count: int = Field(ge=0)
    candidate_count: int = Field(ge=0)
    total_mentions: int = Field(ge=0)
    known_term_count: int = Field(ge=0)
    candidates: list[DiscoveredCandidate] = Field(default_factory=list)

    @model_validator(mode="after")
    def _sync_counts(self) -> "CandidateDiscoveryReport":
        self.candidate_count = len(self.candidates)
        self.total_mentions = sum(
            candidate.mention_count for candidate in self.candidates
        )
        return self

    def top_candidates(self, limit: int = 10) -> list[DiscoveredCandidate]:
        """Return the top candidates by the report's deterministic ranking."""

        if limit <= 0:
            return []
        return self.candidates[:limit]


class _CandidateAccumulator:
    def __init__(self, *, kind: str) -> None:
        self.kind = kind
        self.surfaces: Counter[str] = Counter()
        self.sources: set[str] = set()
        self.evidence: list[CandidateEvidence] = []

    def add(
        self,
        value: str,
        *,
        source: str,
        line: int | None,
        snippet: str,
        max_evidence: int,
    ) -> None:
        self.surfaces[value] += 1
        self.sources.add(source)
        if len(self.evidence) < max_evidence:
            self.evidence.append(
                CandidateEvidence(source=source, line=line, text=snippet)
            )

    @property
    def mention_count(self) -> int:
        return sum(self.surfaces.values())

    @property
    def document_count(self) -> int:
        return len(self.sources)

    @property
    def display_value(self) -> str:
        return sorted(self.surfaces.items(), key=lambda item: (-item[1], item[0]))[0][0]


def discover_candidates(
    documents: Sequence[str | Mapping[str, Any] | CandidateDiscoveryDocument],
    *,
    dictionary: str | Path | Mapping[str, Any] | Dictionary | None = None,
    config: CandidateDiscoveryConfig | Mapping[str, Any] | None = None,
) -> CandidateDiscoveryReport:
    """Find unmatched terminology candidates in text documents.

    The function is deterministic and local. It does not create dictionary terms,
    drafts, proposals, snapshots, or runtime bindings. Callers can reuse the same
    engine for cold-start dictionary suggestions and future terminology drift scans.
    """

    normalized_config = _coerce_config(config)
    normalized_documents = _coerce_documents(documents)
    known_terms = _known_terms(dictionary)
    accumulators: dict[str, _CandidateAccumulator] = {}

    for document in normalized_documents:
        _collect_unigram_candidates(
            document,
            config=normalized_config,
            known_terms=known_terms,
            accumulators=accumulators,
        )
        if normalized_config.include_phrase_candidates:
            _collect_phrase_candidates(
                document,
                config=normalized_config,
                known_terms=known_terms,
                accumulators=accumulators,
            )

    candidates = _rank_candidates(
        accumulators,
        config=normalized_config,
    )
    return CandidateDiscoveryReport(
        document_count=len(normalized_documents),
        candidate_count=len(candidates),
        total_mentions=sum(candidate.mention_count for candidate in candidates),
        known_term_count=len(known_terms),
        candidates=candidates,
    )


def discover_candidates_from_documents(
    paths: Sequence[str | Path],
    *,
    dictionary: str | Path | Mapping[str, Any] | Dictionary | None = None,
    config: CandidateDiscoveryConfig | Mapping[str, Any] | None = None,
) -> CandidateDiscoveryReport:
    """Extract text from local documents and run candidate discovery."""

    documents = [
        CandidateDiscoveryDocument(
            source=str(Path(path)),
            text=extract_document_text(path).text,
        )
        for path in paths
    ]
    return discover_candidates(documents, dictionary=dictionary, config=config)


def _coerce_config(
    config: CandidateDiscoveryConfig | Mapping[str, Any] | None,
) -> CandidateDiscoveryConfig:
    if config is None:
        return CandidateDiscoveryConfig()
    if isinstance(config, CandidateDiscoveryConfig):
        return config
    return CandidateDiscoveryConfig.model_validate(dict(config))


def _coerce_documents(
    documents: Sequence[str | Mapping[str, Any] | CandidateDiscoveryDocument],
) -> list[CandidateDiscoveryDocument]:
    out: list[CandidateDiscoveryDocument] = []
    for index, document in enumerate(documents, start=1):
        if isinstance(document, CandidateDiscoveryDocument):
            out.append(document)
            continue
        if isinstance(document, str):
            out.append(
                CandidateDiscoveryDocument(source=f"text-{index}", text=document)
            )
            continue
        if isinstance(document, Mapping):
            text = (
                document.get("text") or document.get("content") or document.get("body")
            )
            if not isinstance(text, str):
                raise ValueError(
                    "candidate discovery mappings must include text/content/body"
                )
            source = document.get("source") or document.get("path") or f"text-{index}"
            out.append(CandidateDiscoveryDocument(source=str(source), text=text))
            continue
        raise TypeError(
            "documents must be strings, mappings, or CandidateDiscoveryDocument"
        )
    return out


def _known_terms(
    dictionary: str | Path | Mapping[str, Any] | Dictionary | None,
) -> set[str]:
    if dictionary is None:
        return set()
    loaded = load_dictionary(dictionary)
    known: set[str] = set()
    for term in loaded.terms:
        known.add(_normalize_text(term.canonical_value))
        for alias in term.aliases:
            known.add(_normalize_text(alias.value))
    return {value for value in known if value}


def _collect_unigram_candidates(
    document: CandidateDiscoveryDocument,
    *,
    config: CandidateDiscoveryConfig,
    known_terms: set[str],
    accumulators: dict[str, _CandidateAccumulator],
) -> None:
    for line_number, line in enumerate(
        document.text.splitlines() or [document.text], start=1
    ):
        for match in _TOKEN_RE.finditer(line):
            surface = match.group(1)
            normalized = _normalize_text(surface)
            if not normalized or normalized in known_terms:
                continue
            kind = _candidate_kind(surface, config=config)
            if kind is None:
                continue
            if _is_stop_candidate(normalized, config=config):
                continue
            _add_candidate(
                normalized,
                surface,
                kind=kind,
                source=document.source,
                line=line_number,
                snippet=_snippet(line),
                config=config,
                accumulators=accumulators,
            )


def _collect_phrase_candidates(
    document: CandidateDiscoveryDocument,
    *,
    config: CandidateDiscoveryConfig,
    known_terms: set[str],
    accumulators: dict[str, _CandidateAccumulator],
) -> None:
    for line_number, line in enumerate(
        document.text.splitlines() or [document.text], start=1
    ):
        tokens = [match.group(0) for match in _WORD_RE.finditer(line)]
        if len(tokens) < 2:
            continue
        for width in range(2, config.max_phrase_terms + 1):
            for offset in range(0, len(tokens) - width + 1):
                phrase_tokens = tokens[offset : offset + width]
                normalized_tokens = [_normalize_text(token) for token in phrase_tokens]
                if any(not token for token in normalized_tokens):
                    continue
                if all(token in config.stop_word_set for token in normalized_tokens):
                    continue
                phrase = " ".join(phrase_tokens)
                normalized = " ".join(normalized_tokens)
                if normalized in known_terms:
                    continue
                if not _phrase_has_signal(
                    phrase_tokens, config=config, known_terms=known_terms
                ):
                    continue
                _add_candidate(
                    normalized,
                    phrase,
                    kind="phrase",
                    source=document.source,
                    line=line_number,
                    snippet=_snippet(line),
                    config=config,
                    accumulators=accumulators,
                )


def _phrase_has_signal(
    tokens: Sequence[str],
    *,
    config: CandidateDiscoveryConfig,
    known_terms: set[str],
) -> bool:
    has_known_context = any(_normalize_text(token) in known_terms for token in tokens)
    has_candidate_token = any(
        _candidate_kind(token, config=config) is not None for token in tokens
    )
    if has_known_context and has_candidate_token:
        return True
    return has_candidate_token and not all(
        _normalize_text(token) in config.stop_word_set for token in tokens
    )


def _add_candidate(
    normalized: str,
    surface: str,
    *,
    kind: str,
    source: str,
    line: int | None,
    snippet: str,
    config: CandidateDiscoveryConfig,
    accumulators: dict[str, _CandidateAccumulator],
) -> None:
    accumulator = accumulators.get(normalized)
    if accumulator is None:
        accumulator = _CandidateAccumulator(kind=kind)
        accumulators[normalized] = accumulator
    elif accumulator.kind != kind and accumulator.kind != "phrase":
        accumulator.kind = _prefer_kind(accumulator.kind, kind)
    accumulator.add(
        surface,
        source=source,
        line=line,
        snippet=snippet,
        max_evidence=config.max_evidence_per_candidate,
    )


def _rank_candidates(
    accumulators: Mapping[str, _CandidateAccumulator],
    *,
    config: CandidateDiscoveryConfig,
) -> list[DiscoveredCandidate]:
    candidates: list[DiscoveredCandidate] = []
    for normalized, accumulator in accumulators.items():
        if accumulator.mention_count < config.min_frequency:
            continue
        if accumulator.document_count < config.min_document_frequency:
            continue
        score = _score_candidate(accumulator)
        candidates.append(
            DiscoveredCandidate(
                value=accumulator.display_value,
                normalized_value=normalized,
                kind=accumulator.kind,
                mention_count=accumulator.mention_count,
                document_count=accumulator.document_count,
                score=score,
                evidence=accumulator.evidence,
            )
        )
    candidates.sort(
        key=lambda candidate: (
            -candidate.score,
            -candidate.document_count,
            -candidate.mention_count,
            candidate.normalized_value,
        )
    )
    return candidates[: config.max_candidates]


def _score_candidate(accumulator: _CandidateAccumulator) -> float:
    kind_boost = {
        "acronym": 2.0,
        "alphanumeric": 1.8,
        "compound": 1.7,
        "camel_case": 1.6,
        "phrase": 1.35,
        "term": 1.0,
    }.get(accumulator.kind, 1.0)
    return round(
        (accumulator.mention_count * 1.0 + accumulator.document_count * 1.5)
        * kind_boost,
        4,
    )


def _candidate_kind(
    token: str,
    *,
    config: CandidateDiscoveryConfig,
) -> str | None:
    cleaned = token.strip()
    normalized = _normalize_text(cleaned)
    if not normalized or normalized in config.stop_word_set:
        return None
    if any(separator in cleaned for separator in ("_", ".", "/", ":", "-")):
        return "compound"
    if re.fullmatch(r"[A-Z]{2,}[0-9]*", cleaned):
        return "acronym"
    if re.search(r"[A-Za-z]+[0-9]|[0-9]+[A-Za-z]", cleaned):
        return "alphanumeric"
    if re.search(r"[a-z][A-Z]", cleaned) or re.search(r"[A-Z][a-z]+[A-Z]", cleaned):
        return "camel_case"
    if cleaned.isalpha() and len(cleaned) >= config.min_word_length:
        return "term"
    return None


def _prefer_kind(left: str, right: str) -> str:
    rank = {
        "acronym": 5,
        "alphanumeric": 4,
        "compound": 3,
        "camel_case": 2,
        "phrase": 1,
        "term": 0,
    }
    return left if rank.get(left, 0) >= rank.get(right, 0) else right


def _is_stop_candidate(normalized: str, *, config: CandidateDiscoveryConfig) -> bool:
    if normalized in config.stop_word_set:
        return True
    parts = normalized.split()
    return bool(parts) and all(part in config.stop_word_set for part in parts)


def _normalize_text(value: str) -> str:
    return " ".join(
        part for part in _SEPARATOR_RE.split(str(value).strip().casefold()) if part
    )


def _snippet(line: str, *, max_length: int = 180) -> str:
    cleaned = " ".join(line.strip().split())
    if len(cleaned) <= max_length:
        return cleaned
    return cleaned[: max_length - 1].rstrip() + "…"
