"""Deterministic candidate discovery for dictionary suggestions and drift reports.

The candidate discovery engine is intentionally local and dependency-free. It
finds significant unmatched terms and phrases in documents so future workflows
can build reviewable dictionary drafts, terminology drift reports, and optional
agent-assisted grouping without changing runtime dictionaries automatically.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .discovery_context import (
    LINE_CONTEXT_VERSION,
    PROSE_CONTEXTS,
    DocumentContextClassifier,
    LineContext,
)
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
        "changelog",
        "conditions",
        "copyright",
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
        "kind",
        "license",
        "log",
        "logs",
        "merchantability",
        "more",
        "most",
        "no",
        "nor",
        "not",
        "notice",
        "of",
        "off",
        "on",
        "once",
        "only",
        "or",
        "other",
        "our",
        "out",
        "readme",
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
        "warranties",
        "warranty",
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

# A compact, dependency-free background vocabulary used as the default proxy for
# "common public/documentation language". Teams can replace it with a corpus-
# derived list through CandidateDiscoveryConfig.background_terms.
_DEFAULT_BACKGROUND_TERMS = frozenset(
    {
        "alert",
        "api",
        "application",
        "auth",
        "backend",
        "batch",
        "browser",
        "cache",
        "client",
        "cluster",
        "code",
        "component",
        "config",
        "connection",
        "container",
        "cron",
        "dashboard",
        "data",
        "database",
        "debug",
        "deploy",
        "deployment",
        "disk",
        "docker",
        "endpoint",
        "event",
        "exception",
        "failure",
        "feature",
        "file",
        "gateway",
        "health",
        "host",
        "http",
        "index",
        "job",
        "json",
        "latency",
        "library",
        "message",
        "metric",
        "migration",
        "module",
        "node",
        "pipeline",
        "pod",
        "process",
        "proxy",
        "query",
        "queue",
        "region",
        "readme",
        "release",
        "request",
        "response",
        "route",
        "runtime",
        "schema",
        "script",
        "search",
        "server",
        "session",
        "shard",
        "storage",
        "stream",
        "table",
        "task",
        "tenant",
        "thread",
        "timeout",
        "token",
        "trace",
        "traffic",
        "version",
        "worker",
    }
)

_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9_])"
    r"([A-Za-z][A-Za-z0-9]*(?:[._:/-][A-Za-z0-9]+)*|[A-Z]{2,}[0-9]*|[A-Za-z]+[0-9][A-Za-z0-9]*)"
    r"(?![A-Za-z0-9_])"
)
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9]*(?:[._:/-][A-Za-z0-9]+)*")
_SEPARATOR_RE = re.compile(r"[\s._:/+#-]+")
_TICKET_ID_RE = re.compile(r"[A-Z][A-Z0-9]{1,12}-\d{1,8}")
_SNAKE_CASE_RE = re.compile(r"[A-Za-z][A-Za-z0-9]*(?:_[A-Za-z0-9]+)+")
_KEBAB_CASE_RE = re.compile(r"[A-Za-z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)+")
_VERSIONED_NAME_RE = re.compile(
    r"[A-Za-z][A-Za-z0-9]*(?:[._/-][A-Za-z0-9]+)*(?:[._/-]v\d+|v\d+)"
)
_QUALIFIED_NAME_RE = re.compile(
    r"[A-Za-z][A-Za-z0-9]*(?::|/)[A-Za-z0-9][A-Za-z0-9:/._-]*"
)
_ALL_CAPS_RE = re.compile(r"[A-Z]{2,}(?:_[A-Z0-9]+)*[0-9]*")
_RST_DIRECTIVE_LINE_RE = re.compile(r"^\.\.\s+[\w:-]+::")
_RST_OPTION_LINE_RE = re.compile(r"^:[\w-]+:")

_BOILERPLATE_MIN_LINE_LENGTH = 12


class CandidateTokenizerSignal(BaseModel):
    """Optional tokenizer analysis for one candidate surface.

    Providers can populate this model from an embedding tokenizer or an external
    precomputed signal. Candidate discovery never imports a tokenizer directly,
    keeping the core package dependency-light.
    """

    token_count: int = Field(default=0, ge=0)
    subtoken_count: int = Field(default=0, ge=0)
    unknown_token_count: int = Field(default=0, ge=0)
    fragmentation_score: float = Field(default=0.0, ge=0.0, le=1.0)
    oov_score: float = Field(default=0.0, ge=0.0, le=1.0)
    reasons: list[str] = Field(default_factory=list)

    @field_validator("reasons")
    @classmethod
    def _clean_reasons(cls, values: list[str]) -> list[str]:
        return sorted({str(value).strip() for value in values if str(value).strip()})


class TokenizerSignalProvider(Protocol):
    """Protocol for optional tokenizer-aware candidate scoring.

    Implementations may wrap a Hugging Face tokenizer, a hosted tokenizer
    service, or precomputed tokenization metadata. The discovery engine treats
    this provider as optional input and never creates heavy tokenizer objects by
    itself.
    """

    def analyze(self, surface: str) -> CandidateTokenizerSignal | Mapping[str, Any]:
        """Return tokenizer signal for a candidate surface."""


class CandidateDiscoveryConfig(BaseModel):
    """Configuration for deterministic candidate discovery."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    min_frequency: int = Field(default=2, ge=1)
    min_document_frequency: int = Field(default=1, ge=1)
    min_word_length: int = Field(default=5, ge=2)
    max_candidates: int = Field(default=50, ge=1)
    max_evidence_per_candidate: int = Field(default=3, ge=1)
    include_phrase_candidates: bool = True
    max_phrase_terms: int = Field(default=3, ge=2, le=3)
    include_code_style_candidates: bool = True
    skip_boilerplate_lines: bool = True
    boilerplate_min_documents: int = Field(default=3, ge=2)
    boilerplate_document_share: float = Field(default=0.25, ge=0.0, le=1.0)
    skip_rst_markup: bool = True
    stop_words: list[str] = Field(default_factory=lambda: sorted(_DEFAULT_STOP_WORDS))
    background_terms: list[str] = Field(
        default_factory=lambda: sorted(_DEFAULT_BACKGROUND_TERMS)
    )
    jargon_weight: float = Field(default=1.25, ge=0.0)
    code_shape_weight: float = Field(default=0.75, ge=0.0)
    surface_risk_weight: float = Field(default=0.5, ge=0.0)
    tokenizer_signal_weight: float = Field(default=0.75, ge=0.0)
    background_penalty_weight: float = Field(default=0.75, ge=0.0)
    context_weight: float = Field(default=0.75, ge=0.0)
    tokenizer_signal_provider: Any | None = Field(default=None, exclude=True)

    @field_validator("stop_words", "background_terms")
    @classmethod
    def _normalize_word_list(cls, values: list[str]) -> list[str]:
        return sorted(
            {_normalize_text(value) for value in values if _normalize_text(value)}
        )

    @property
    def stop_word_set(self) -> set[str]:
        return set(self.stop_words)

    @property
    def background_term_set(self) -> set[str]:
        return set(self.background_terms)


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
    context: str | None = None

    @field_validator("source", "text")
    @classmethod
    def _clean_text(cls, value: str) -> str:
        cleaned = " ".join(str(value).strip().split())
        if not cleaned:
            raise ValueError("candidate evidence text must not be empty")
        return cleaned

    @field_validator("context")
    @classmethod
    def _clean_context(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = str(value).strip().casefold()
        return cleaned or None


class CandidateScoreBreakdown(BaseModel):
    """Explainable components behind a discovered candidate score."""

    frequency_score: float = Field(ge=0.0)
    document_frequency_score: float = Field(ge=0.0)
    kind_boost: float = Field(ge=0.0)
    jargon_score: float = Field(ge=0.0, le=1.0)
    code_shape_score: float = Field(ge=0.0, le=1.0)
    surface_risk_score: float = Field(default=0.0, ge=0.0, le=1.0)
    token_fragmentation_score: float | None = Field(default=None, ge=0.0, le=1.0)
    oov_score: float | None = Field(default=None, ge=0.0, le=1.0)
    tokenizer_signal_status: str = "unavailable"
    background_penalty: float = Field(ge=0.0, le=1.0)
    context_score: float = Field(default=0.0, ge=0.0, le=1.0)
    context_adjustment: float = Field(default=0.0, ge=0.0)
    context_counts: dict[str, int] = Field(default_factory=dict)
    surface_class: str | None = None
    reasons: list[str] = Field(default_factory=list)


class DiscoveredCandidate(BaseModel):
    """One unmatched term or phrase discovered in local text."""

    value: str
    normalized_value: str
    kind: str
    mention_count: int = Field(ge=1)
    document_count: int = Field(ge=1)
    score: float = Field(ge=0.0)
    score_breakdown: CandidateScoreBreakdown | None = None
    evidence: list[CandidateEvidence] = Field(default_factory=list)

    @field_validator("value", "normalized_value", "kind")
    @classmethod
    def _non_empty_text(cls, value: str) -> str:
        cleaned = " ".join(str(value).strip().split())
        if not cleaned:
            raise ValueError("candidate fields must not be empty")
        return cleaned


class CandidateCluster(BaseModel):
    """Deterministic group of related candidate surfaces for review."""

    cluster_id: str
    representative_value: str
    normalized_representative: str
    surface_values: list[str] = Field(default_factory=list)
    candidate_count: int = Field(ge=1)
    total_mentions: int = Field(ge=1)
    document_count: int = Field(ge=1)
    score: float = Field(ge=0.0)
    reasons: list[str] = Field(default_factory=list)
    evidence: list[CandidateEvidence] = Field(default_factory=list)

    @field_validator("cluster_id", "representative_value", "normalized_representative")
    @classmethod
    def _non_empty_text(cls, value: str) -> str:
        cleaned = " ".join(str(value).strip().split())
        if not cleaned:
            raise ValueError("candidate cluster fields must not be empty")
        return cleaned


class CandidateDiscoveryReport(BaseModel):
    """Result returned by deterministic candidate discovery."""

    document_count: int = Field(ge=0)
    candidate_count: int = Field(ge=0)
    cluster_count: int = Field(default=0, ge=0)
    total_mentions: int = Field(ge=0)
    known_term_count: int = Field(ge=0)
    input_line_count: int = Field(default=0, ge=0)
    scanned_line_count: int = Field(default=0, ge=0)
    skipped_line_count: int = Field(default=0, ge=0)
    skipped_lines_by_reason: dict[str, int] = Field(default_factory=dict)
    boilerplate_line_pattern_count: int = Field(default=0, ge=0)
    line_context_version: str = LINE_CONTEXT_VERSION
    candidates: list[DiscoveredCandidate] = Field(default_factory=list)
    candidate_clusters: list[CandidateCluster] = Field(default_factory=list)

    @model_validator(mode="after")
    def _sync_counts(self) -> "CandidateDiscoveryReport":
        self.candidate_count = len(self.candidates)
        self.cluster_count = len(self.candidate_clusters)
        self.total_mentions = sum(
            candidate.mention_count for candidate in self.candidates
        )
        self.skipped_line_count = sum(self.skipped_lines_by_reason.values())
        return self

    def top_candidates(self, limit: int = 10) -> list[DiscoveredCandidate]:
        """Return the top candidates by the report's deterministic ranking."""

        if limit <= 0:
            return []
        return self.candidates[:limit]

    def top_clusters(self, limit: int = 10) -> list[CandidateCluster]:
        """Return the top review clusters by deterministic ranking."""

        if limit <= 0:
            return []
        return self.candidate_clusters[:limit]


class _CandidateAccumulator:
    def __init__(self, *, kind: str) -> None:
        self.kind = kind
        self.surfaces: Counter[str] = Counter()
        self.sources: set[str] = set()
        self.evidence: list[CandidateEvidence] = []
        self.contexts: Counter[str] = Counter()

    def add(
        self,
        value: str,
        *,
        source: str,
        line: int | None,
        snippet: str,
        context: LineContext,
        max_evidence: int,
    ) -> None:
        self.surfaces[value] += 1
        self.sources.add(source)
        self.contexts[context.value] += 1
        if len(self.evidence) < max_evidence:
            self.evidence.append(
                CandidateEvidence(
                    source=source,
                    line=line,
                    text=snippet,
                    context=context.value,
                )
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


@dataclass(frozen=True, slots=True)
class _DiscoveryLine:
    line_number: int
    text: str
    context: LineContext


@dataclass(slots=True)
class _DiscoveryScanStats:
    input_line_count: int = 0
    scanned_line_count: int = 0
    skipped_lines_by_reason: Counter[str] = field(default_factory=Counter)


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
    stats = _DiscoveryScanStats()
    boilerplate_lines = (
        _detect_boilerplate_lines(normalized_documents, config=normalized_config)
        if normalized_config.skip_boilerplate_lines
        else frozenset()
    )

    for document in normalized_documents:
        lines = _prepare_document_lines(
            document,
            config=normalized_config,
            boilerplate_lines=boilerplate_lines,
            stats=stats,
        )
        _collect_unigram_candidates(
            lines,
            source=document.source,
            config=normalized_config,
            known_terms=known_terms,
            accumulators=accumulators,
        )
        if normalized_config.include_phrase_candidates:
            _collect_phrase_candidates(
                lines,
                source=document.source,
                config=normalized_config,
                known_terms=known_terms,
                accumulators=accumulators,
            )

    candidates = _rank_candidates(
        accumulators,
        config=normalized_config,
    )
    clusters = _cluster_candidates(candidates)
    return CandidateDiscoveryReport(
        document_count=len(normalized_documents),
        candidate_count=len(candidates),
        cluster_count=len(clusters),
        total_mentions=sum(candidate.mention_count for candidate in candidates),
        known_term_count=len(known_terms),
        input_line_count=stats.input_line_count,
        scanned_line_count=stats.scanned_line_count,
        skipped_lines_by_reason=dict(sorted(stats.skipped_lines_by_reason.items())),
        boilerplate_line_pattern_count=len(boilerplate_lines),
        candidates=candidates,
        candidate_clusters=clusters,
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


def _prepare_document_lines(
    document: CandidateDiscoveryDocument,
    *,
    config: CandidateDiscoveryConfig,
    boilerplate_lines: frozenset[str],
    stats: _DiscoveryScanStats,
) -> list[_DiscoveryLine]:
    classifier = DocumentContextClassifier(source=document.source)
    prepared: list[_DiscoveryLine] = []
    for line_number, raw_line in enumerate(
        document.text.splitlines() or [document.text], start=1
    ):
        line = raw_line.strip()
        if not line:
            continue
        stats.input_line_count += 1
        context = classifier.classify(line)
        normalized_line = _normalize_line(line)
        if normalized_line in boilerplate_lines:
            stats.skipped_lines_by_reason["boilerplate"] += 1
            continue
        if config.skip_rst_markup and _RST_DIRECTIVE_LINE_RE.match(line):
            stats.skipped_lines_by_reason["rst_directive"] += 1
            continue
        if config.skip_rst_markup and _RST_OPTION_LINE_RE.match(line):
            stats.skipped_lines_by_reason["rst_option"] += 1
            continue
        stats.scanned_line_count += 1
        prepared.append(
            _DiscoveryLine(line_number=line_number, text=line, context=context)
        )
    return prepared


def _detect_boilerplate_lines(
    documents: Sequence[CandidateDiscoveryDocument],
    *,
    config: CandidateDiscoveryConfig,
) -> frozenset[str]:
    """Return normalized lines repeated verbatim across many documents."""

    total_documents = len(documents)
    if total_documents < config.boilerplate_min_documents:
        return frozenset()
    line_documents: dict[str, set[str]] = {}
    for index, document in enumerate(documents, start=1):
        document_key = f"{index}:{document.source}"
        seen_in_document: set[str] = set()
        for raw_line in document.text.splitlines():
            normalized = _normalize_line(raw_line)
            if (
                len(normalized) < _BOILERPLATE_MIN_LINE_LENGTH
                or normalized in seen_in_document
            ):
                continue
            seen_in_document.add(normalized)
            line_documents.setdefault(normalized, set()).add(document_key)
    threshold = max(
        config.boilerplate_min_documents,
        math.ceil(config.boilerplate_document_share * total_documents),
    )
    return frozenset(
        line for line, sources in line_documents.items() if len(sources) >= threshold
    )


def _normalize_line(line: str) -> str:
    return " ".join(line.strip().casefold().split())


def _collect_unigram_candidates(
    lines: Sequence[_DiscoveryLine],
    *,
    source: str,
    config: CandidateDiscoveryConfig,
    known_terms: set[str],
    accumulators: dict[str, _CandidateAccumulator],
) -> None:
    for item in lines:
        for match in _TOKEN_RE.finditer(item.text):
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
                source=source,
                line=item.line_number,
                snippet=_snippet(item.text),
                context=item.context,
                config=config,
                accumulators=accumulators,
            )


def _collect_phrase_candidates(
    lines: Sequence[_DiscoveryLine],
    *,
    source: str,
    config: CandidateDiscoveryConfig,
    known_terms: set[str],
    accumulators: dict[str, _CandidateAccumulator],
) -> None:
    for item in lines:
        tokens = [match.group(0) for match in _WORD_RE.finditer(item.text)]
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
                    source=source,
                    line=item.line_number,
                    snippet=_snippet(item.text),
                    context=item.context,
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
    context: LineContext,
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
        context=context,
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
        score, breakdown = _score_candidate(accumulator, config=config)
        candidates.append(
            DiscoveredCandidate(
                value=accumulator.display_value,
                normalized_value=normalized,
                kind=accumulator.kind,
                mention_count=accumulator.mention_count,
                document_count=accumulator.document_count,
                score=score,
                score_breakdown=breakdown,
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


def _cluster_candidates(
    candidates: Sequence[DiscoveredCandidate],
) -> list[CandidateCluster]:
    """Build small deterministic review clusters from ranked candidates."""

    groups: list[list[DiscoveredCandidate]] = []
    for candidate in candidates:
        for group in groups:
            if any(
                _candidate_similarity(candidate, existing) >= 0.5 for existing in group
            ):
                group.append(candidate)
                break
        else:
            groups.append([candidate])

    clusters: list[CandidateCluster] = []
    for index, group in enumerate(groups, start=1):
        ordered = sorted(
            group,
            key=lambda item: (
                -item.score,
                -item.document_count,
                -item.mention_count,
                item.normalized_value,
            ),
        )
        representative = ordered[0]
        evidence: list[CandidateEvidence] = []
        for candidate in ordered:
            for item in candidate.evidence:
                if len(evidence) >= 5:
                    break
                evidence.append(item)
            if len(evidence) >= 5:
                break
        clusters.append(
            CandidateCluster(
                cluster_id=f"candidate-cluster-{index:03d}",
                representative_value=representative.value,
                normalized_representative=representative.normalized_value,
                surface_values=[candidate.value for candidate in ordered],
                candidate_count=len(ordered),
                total_mentions=sum(candidate.mention_count for candidate in ordered),
                document_count=len(
                    {
                        item.source
                        for candidate in ordered
                        for item in candidate.evidence
                    }
                )
                or max(candidate.document_count for candidate in ordered),
                score=round(sum(candidate.score for candidate in ordered), 4),
                reasons=_cluster_reasons(ordered),
                evidence=evidence,
            )
        )
    clusters.sort(
        key=lambda item: (
            -item.score,
            -item.document_count,
            -item.total_mentions,
            item.normalized_representative,
        )
    )
    for index, cluster in enumerate(clusters, start=1):
        cluster.cluster_id = f"candidate-cluster-{index:03d}"
    return clusters


def _candidate_similarity(
    left: DiscoveredCandidate, right: DiscoveredCandidate
) -> float:
    left_parts = set(_cluster_parts(left.normalized_value))
    right_parts = set(_cluster_parts(right.normalized_value))
    if not left_parts or not right_parts:
        return 0.0
    if left.normalized_value == right.normalized_value:
        return 1.0
    overlap = left_parts & right_parts
    if not overlap:
        return 0.0
    containment = len(overlap) / min(len(left_parts), len(right_parts))
    jaccard = len(overlap) / len(left_parts | right_parts)
    return max(containment, jaccard)


def _cluster_parts(normalized: str) -> list[str]:
    parts = _normalized_parts(normalized)
    normalized_parts: list[str] = []
    for part in parts:
        if part.endswith("s") and len(part) > 4:
            part = part[:-1]
        normalized_parts.append(part)
    return normalized_parts


def _cluster_reasons(candidates: Sequence[DiscoveredCandidate]) -> list[str]:
    reasons: set[str] = set()
    if len(candidates) > 1:
        reasons.add("related_surface_cluster")
    if any(candidate.kind == "phrase" for candidate in candidates):
        reasons.add("phrase_surface_present")
    if any(
        candidate.score_breakdown is not None
        and candidate.score_breakdown.surface_class is not None
        for candidate in candidates
    ):
        reasons.add("code_surface_present")
    if any(
        candidate.score_breakdown is not None
        and candidate.score_breakdown.jargon_score >= 0.75
        for candidate in candidates
    ):
        reasons.add("domain_specific_language")
    return sorted(reasons)


def _score_candidate(
    accumulator: _CandidateAccumulator,
    *,
    config: CandidateDiscoveryConfig,
) -> tuple[float, CandidateScoreBreakdown]:
    frequency_score = float(accumulator.mention_count)
    document_frequency_score = float(accumulator.document_count) * 1.5
    support_score = frequency_score + document_frequency_score
    kind_boost = _kind_boost(accumulator.kind)
    display_value = accumulator.display_value
    normalized = _normalize_text(display_value)
    jargon_score, jargon_reasons = _jargon_score(
        display_value, normalized=normalized, config=config
    )
    surface_class = _surface_class(display_value)
    code_shape_score, code_reasons = _code_shape_score(display_value)
    background_penalty, background_reasons = _background_penalty(
        normalized, config=config
    )
    surface_risk_score, surface_risk_reasons = _surface_risk_score(
        display_value, normalized=normalized, config=config
    )
    tokenizer_signal, tokenizer_status, tokenizer_reasons = _tokenizer_signal(
        display_value, config=config
    )
    context_score, context_reasons = _context_score(accumulator.contexts)
    context_adjustment = support_score * config.context_weight * context_score
    tokenizer_boost = 0.0
    token_fragmentation_score: float | None = None
    oov_score: float | None = None
    if tokenizer_signal is not None:
        token_fragmentation_score = tokenizer_signal.fragmentation_score
        oov_score = tokenizer_signal.oov_score
        tokenizer_boost = max(
            tokenizer_signal.fragmentation_score, tokenizer_signal.oov_score
        )
    raw_score = support_score * kind_boost
    score = raw_score
    score += support_score * config.jargon_weight * jargon_score
    score += support_score * config.code_shape_weight * code_shape_score
    score += support_score * config.surface_risk_weight * surface_risk_score
    score += support_score * config.tokenizer_signal_weight * tokenizer_boost
    score += context_adjustment
    score -= support_score * config.background_penalty_weight * background_penalty
    breakdown = CandidateScoreBreakdown(
        frequency_score=round(frequency_score, 4),
        document_frequency_score=round(document_frequency_score, 4),
        kind_boost=round(kind_boost, 4),
        jargon_score=round(jargon_score, 4),
        code_shape_score=round(code_shape_score, 4),
        surface_risk_score=round(surface_risk_score, 4),
        token_fragmentation_score=(
            None
            if token_fragmentation_score is None
            else round(token_fragmentation_score, 4)
        ),
        oov_score=None if oov_score is None else round(oov_score, 4),
        tokenizer_signal_status=tokenizer_status,
        background_penalty=round(background_penalty, 4),
        context_score=round(context_score, 4),
        context_adjustment=round(context_adjustment, 4),
        context_counts=dict(sorted(accumulator.contexts.items())),
        surface_class=surface_class,
        reasons=sorted(
            set(
                [
                    *jargon_reasons,
                    *code_reasons,
                    *surface_risk_reasons,
                    *tokenizer_reasons,
                    *background_reasons,
                    *context_reasons,
                ]
            )
        ),
    )
    return round(max(score, 0.0), 4), breakdown


def _context_score(contexts: Mapping[str, int]) -> tuple[float, list[str]]:
    prose_values = {context.value for context in PROSE_CONTEXTS}
    prose_count = sum(count for name, count in contexts.items() if name in prose_values)
    code_count = sum(
        count for name, count in contexts.items() if name not in prose_values
    )
    if prose_count and code_count:
        return 0.5, ["mixed_prose_code_context"]
    if prose_count:
        return 0.2, ["prose_context"]
    if code_count:
        return 0.0, ["code_only_context"]
    return 0.0, []


def _kind_boost(kind: str) -> float:
    return {
        "ticket_id": 2.35,
        "all_caps": 2.1,
        "acronym": 2.0,
        "versioned_name": 1.95,
        "alphanumeric": 1.85,
        "kebab_case": 1.8,
        "snake_case": 1.8,
        "qualified_name": 1.75,
        "compound": 1.7,
        "camel_case": 1.6,
        "phrase": 1.35,
        "term": 1.0,
    }.get(kind, 1.0)


def _jargon_score(
    surface: str, *, normalized: str, config: CandidateDiscoveryConfig
) -> tuple[float, list[str]]:
    parts = _normalized_parts(normalized)
    if not parts:
        return 0.0, []
    background_terms = config.background_term_set | config.stop_word_set
    common_part_count = sum(1 for part in parts if part in background_terms)
    uncommon_ratio = 1.0 - (common_part_count / len(parts))
    score = 0.2 + (0.65 * uncommon_ratio)
    reasons: list[str] = []
    if uncommon_ratio >= 0.75:
        reasons.append("rare_against_background")
    elif uncommon_ratio > 0.0:
        reasons.append("mixed_background_and_domain_language")
    else:
        reasons.append("common_background_language")

    code_score, _ = _code_shape_score(surface)
    if code_score >= 0.5:
        score += 0.15
        reasons.append("identifier_like_surface")
    if _looks_like_short_alias(normalized):
        score += 0.1
        reasons.append("short_alias_like")
    return min(round(score, 4), 1.0), reasons


def _code_shape_score(surface: str) -> tuple[float, list[str]]:
    cleaned = surface.strip()
    normalized = _normalize_text(cleaned)
    score = 0.0
    reasons: list[str] = []
    if not cleaned:
        return 0.0, reasons

    surface_class = _surface_class(cleaned)
    if surface_class == "ticket_id":
        score += 0.65
        reasons.append("ticket_id_surface")
    elif surface_class == "versioned_name":
        score += 0.55
        reasons.append("versioned_name_surface")
    elif surface_class == "kebab_case":
        score += 0.45
        reasons.append("kebab_case_surface")
    elif surface_class == "snake_case":
        score += 0.45
        reasons.append("snake_case_surface")
    elif surface_class == "qualified_name":
        score += 0.45
        reasons.append("qualified_name_surface")
    elif surface_class == "all_caps":
        score += 0.4
        reasons.append("all_caps_surface")

    if any(ch.isalpha() for ch in cleaned) and any(ch.isdigit() for ch in cleaned):
        score += 0.35
        reasons.append("mixed_alpha_digit")
    if any(separator in cleaned for separator in ("_", ".", "/", ":", "-", "+")):
        score += 0.25
        reasons.append("compound_surface")
    if re.search(r"[a-z][A-Z]", cleaned) or re.search(r"[A-Z][a-z]+[A-Z]", cleaned):
        score += 0.3
        reasons.append("camel_case_surface")
    if normalized.endswith(("db", "svc", "api", "id")):
        score += 0.15
        reasons.append("domain_suffix")
    return min(round(score, 4), 1.0), reasons


def _surface_risk_score(
    surface: str, *, normalized: str, config: CandidateDiscoveryConfig
) -> tuple[float, list[str]]:
    """Return a lightweight tokenizer-risk proxy without pretending to be OOV.

    This signal is available even when no tokenizer provider is configured. It
    favors surfaces that are likely to fragment in embedding tokenizers because
    they look like internal identifiers, compact aliases, or code-shaped names.
    """

    cleaned = surface.strip()
    compact = normalized.replace(" ", "")
    if not cleaned or not compact:
        return 0.0, []

    score = 0.0
    reasons: list[str] = []
    background_terms = config.background_term_set | config.stop_word_set
    parts = _normalized_parts(normalized)

    if len(compact) <= 5 and any(ch.isalpha() for ch in compact):
        score += 0.22
        reasons.append("compact_surface_risk")
    if any(ch.isalpha() for ch in compact) and any(ch.isdigit() for ch in compact):
        score += 0.28
        reasons.append("alpha_digit_tokenizer_risk")
    if any(separator in cleaned for separator in ("_", ".", "/", ":", "-", "+")):
        score += 0.25
        reasons.append("separator_tokenizer_risk")
    surface_class = _surface_class(cleaned)
    if surface_class in {"ticket_id", "versioned_name"}:
        score += 0.18
        reasons.append("structured_identifier_risk")
    if cleaned.upper() == cleaned and any(ch.isalpha() for ch in cleaned):
        score += 0.18
        reasons.append("uppercase_tokenizer_risk")
    if parts and all(part not in background_terms for part in parts):
        score += 0.17
        reasons.append("background_oov_proxy")

    return min(round(score, 4), 1.0), reasons


def _tokenizer_signal(
    surface: str, *, config: CandidateDiscoveryConfig
) -> tuple[CandidateTokenizerSignal | None, str, list[str]]:
    provider = config.tokenizer_signal_provider
    if provider is None:
        return None, "unavailable", []
    try:
        raw_signal = provider.analyze(surface)
        signal = (
            raw_signal
            if isinstance(raw_signal, CandidateTokenizerSignal)
            else CandidateTokenizerSignal.model_validate(raw_signal)
        )
    except Exception:
        return None, "error", ["tokenizer_signal_error"]

    reasons = [*signal.reasons]
    if signal.fragmentation_score > 0:
        reasons.append("token_fragmentation_signal")
    if signal.oov_score > 0:
        reasons.append("oov_tokenizer_signal")
    if signal.unknown_token_count > 0:
        reasons.append("unknown_token_signal")
    return signal, "available", sorted(set(reasons))


def _background_penalty(
    normalized: str, *, config: CandidateDiscoveryConfig
) -> tuple[float, list[str]]:
    parts = _normalized_parts(normalized)
    if not parts:
        return 0.0, []
    background_terms = config.background_term_set | config.stop_word_set
    common_part_count = sum(1 for part in parts if part in background_terms)
    if common_part_count == len(parts):
        return 0.85, ["background_language_penalty"]
    if common_part_count:
        return round(0.35 * (common_part_count / len(parts)), 4), [
            "partial_background_language_penalty"
        ]
    return 0.0, []


def _candidate_kind(
    token: str,
    *,
    config: CandidateDiscoveryConfig,
) -> str | None:
    cleaned = token.strip()
    normalized = _normalize_text(cleaned)
    if not normalized or normalized in config.stop_word_set:
        return None

    if config.include_code_style_candidates:
        surface_class = _surface_class(cleaned)
        if surface_class is not None:
            return "acronym" if surface_class == "all_caps" else surface_class

    if any(separator in cleaned for separator in ("_", ".", "/", ":", "-", "+")):
        return "compound"
    if re.search(r"[A-Za-z]+[0-9]|[0-9]+[A-Za-z]", cleaned):
        return "alphanumeric"
    if re.search(r"[a-z][A-Z]", cleaned) or re.search(r"[A-Z][a-z]+[A-Z]", cleaned):
        return "camel_case"
    if cleaned.isalpha() and len(cleaned) >= config.min_word_length:
        return "term"
    return None


def _surface_class(surface: str) -> str | None:
    cleaned = surface.strip()
    if not cleaned or " " in cleaned:
        return None
    if _TICKET_ID_RE.fullmatch(cleaned):
        return "ticket_id"
    if _VERSIONED_NAME_RE.fullmatch(cleaned):
        return "versioned_name"
    if _SNAKE_CASE_RE.fullmatch(cleaned):
        return "snake_case"
    if _KEBAB_CASE_RE.fullmatch(cleaned):
        return "kebab_case"
    if _QUALIFIED_NAME_RE.fullmatch(cleaned):
        return "qualified_name"
    if _ALL_CAPS_RE.fullmatch(cleaned):
        return "all_caps"
    if re.search(r"[a-z][A-Z]", cleaned) or re.search(r"[A-Z][a-z]+[A-Z]", cleaned):
        return "camel_case"
    if re.search(r"[A-Za-z]+[0-9]|[0-9]+[A-Za-z]", cleaned):
        return "alphanumeric"
    return None


def _prefer_kind(left: str, right: str) -> str:
    rank = {
        "ticket_id": 10,
        "all_caps": 9,
        "acronym": 8,
        "versioned_name": 7,
        "alphanumeric": 6,
        "kebab_case": 5,
        "snake_case": 5,
        "qualified_name": 5,
        "compound": 4,
        "camel_case": 3,
        "phrase": 1,
        "term": 0,
    }
    return left if rank.get(left, 0) >= rank.get(right, 0) else right


def _is_stop_candidate(normalized: str, *, config: CandidateDiscoveryConfig) -> bool:
    if normalized in config.stop_word_set:
        return True
    parts = normalized.split()
    return bool(parts) and all(part in config.stop_word_set for part in parts)


def _looks_like_short_alias(normalized: str) -> bool:
    compact = normalized.replace(" ", "")
    return 2 <= len(compact) <= 5 and compact.isalpha()


def _normalized_parts(normalized: str) -> list[str]:
    return [part for part in normalized.split() if part]


def _normalize_text(value: str) -> str:
    return " ".join(
        part for part in _SEPARATOR_RE.split(str(value).strip().casefold()) if part
    )


def _snippet(line: str, *, max_length: int = 180) -> str:
    cleaned = " ".join(line.strip().split())
    if len(cleaned) <= max_length:
        return cleaned
    return cleaned[: max_length - 1].rstrip() + "…"
