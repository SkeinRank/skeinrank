"""Candidate discovery and pruning for the OpenRouter alias scout example.

Discovery is deterministic and dependency-light. It mines compact alias
candidates from failed-query JSONL rows before any LLM call exists, so
OpenRouter review spends tokens only on small, explainable fact packs.
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

JsonDict = dict[str, Any]
_TOKEN_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9][A-Za-zА-Яа-яЁё0-9_.+#/-]*")

DEFAULT_STOP_WORDS = frozenset(
    {
        "a",
        "about",
        "after",
        "all",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "can",
        "during",
        "for",
        "from",
        "how",
        "in",
        "into",
        "is",
        "it",
        "of",
        "on",
        "or",
        "the",
        "to",
        "with",
        "without",
        "после",
        "для",
        "как",
        "при",
        "что",
    }
)

DEFAULT_NOISE_TOKENS = frozenset(
    {
        "error",
        "errors",
        "failed",
        "failure",
        "help",
        "incident",
        "issue",
        "problem",
        "dns",
        "exhausted",
        "failover",
        "pool",
        "pod",
        "query",
        "queue",
        "red",
        "restart",
        "rollout",
        "runbook",
        "search",
        "service",
        "shard",
        "status",
        "stuck",
        "timeout",
        "worker",
    }
)

DEFAULT_BACKGROUND_TERMS = frozenset(
    {
        "api",
        "application",
        "backend",
        "cache",
        "client",
        "cluster",
        "component",
        "config",
        "connection",
        "container",
        "dashboard",
        "data",
        "database",
        "deploy",
        "deployment",
        "endpoint",
        "event",
        "failure",
        "gateway",
        "health",
        "http",
        "index",
        "job",
        "latency",
        "message",
        "metric",
        "migration",
        "node",
        "pipeline",
        "pod",
        "process",
        "query",
        "queue",
        "release",
        "request",
        "response",
        "route",
        "runtime",
        "schema",
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
        "traffic",
        "version",
        "worker",
    }
)


DEFAULT_KNOWN_TERMS = frozenset(
    {
        "kubernetes",
        "postgres",
        "postgresql",
        "database",
        "production",
        "cluster",
    }
)


@dataclass(frozen=True)
class CandidateDiscoveryConfig:
    """Tunable local-only discovery settings for failed-query mining."""

    max_candidates: int = 25
    min_token_length: int = 2
    max_token_length: int = 32
    min_weighted_count: float = 1.0
    min_score: float = 1.0
    max_examples_per_candidate: int = 5
    stop_words: frozenset[str] = DEFAULT_STOP_WORDS
    noise_tokens: frozenset[str] = DEFAULT_NOISE_TOKENS
    known_terms: frozenset[str] = DEFAULT_KNOWN_TERMS
    background_terms: frozenset[str] = DEFAULT_BACKGROUND_TERMS
    jargon_weight: float = 2.0
    surface_risk_weight: float = 0.75
    background_penalty_weight: float = 1.0

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any] | None) -> "CandidateDiscoveryConfig":
        """Create config from optional JSON config values.

        Missing values intentionally keep conservative defaults so older
        config files keep working.
        """

        if not raw:
            return cls()

        def _string_set(name: str, default: frozenset[str]) -> frozenset[str]:
            value = raw.get(name)
            if value is None:
                return default
            if not isinstance(value, list) or not all(
                isinstance(item, str) for item in value
            ):
                raise ValueError(f"candidate_discovery.{name} must be a string list")
            return frozenset(_normalize_token(item) for item in value if item.strip())

        return cls(
            max_candidates=int(raw.get("max_candidates", cls.max_candidates)),
            min_token_length=int(raw.get("min_token_length", cls.min_token_length)),
            max_token_length=int(raw.get("max_token_length", cls.max_token_length)),
            min_weighted_count=float(
                raw.get("min_weighted_count", cls.min_weighted_count)
            ),
            min_score=float(raw.get("min_score", cls.min_score)),
            max_examples_per_candidate=int(
                raw.get("max_examples_per_candidate", cls.max_examples_per_candidate)
            ),
            stop_words=_string_set("stop_words", DEFAULT_STOP_WORDS),
            noise_tokens=_string_set("noise_tokens", DEFAULT_NOISE_TOKENS),
            known_terms=_string_set("known_terms", DEFAULT_KNOWN_TERMS),
            background_terms=_string_set("background_terms", DEFAULT_BACKGROUND_TERMS),
            jargon_weight=float(raw.get("jargon_weight", cls.jargon_weight)),
            surface_risk_weight=float(
                raw.get("surface_risk_weight", cls.surface_risk_weight)
            ),
            background_penalty_weight=float(
                raw.get("background_penalty_weight", cls.background_penalty_weight)
            ),
        )


@dataclass(frozen=True)
class AliasCandidate:
    """A deterministic candidate mined from failed-query rows."""

    surface: str
    weighted_count: float
    document_frequency: int
    score: float
    reasons: tuple[str, ...]
    score_breakdown: Mapping[str, float | list[str]] = field(default_factory=dict)
    example_queries: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> JsonDict:
        """Return a stable JSON-serializable candidate payload."""

        return {
            "surface": self.surface,
            "weighted_count": round(self.weighted_count, 4),
            "document_frequency": self.document_frequency,
            "score": round(self.score, 4),
            "reasons": list(self.reasons),
            "score_breakdown": _round_score_breakdown(self.score_breakdown),
            "example_queries": list(self.example_queries),
        }


def tokenize_query(query: str) -> list[str]:
    """Tokenize a failed query into normalized candidate surfaces."""

    return [_normalize_token(match.group(0)) for match in _TOKEN_RE.finditer(query)]


def discover_alias_candidates(
    failed_queries: Sequence[Mapping[str, Any]],
    *,
    config: CandidateDiscoveryConfig | None = None,
) -> list[AliasCandidate]:
    """Mine alias-like candidates from failed-query rows.

    This is intentionally not a semantic mapper: it finds cheap candidate
    surfaces such as `pg`, `k8s`, or `kube` and leaves canonical selection for a
    later LLM/evidence stage.
    """

    cfg = config or CandidateDiscoveryConfig()
    weighted_counts: Counter[str] = Counter()
    document_frequency: Counter[str] = Counter()
    examples: dict[str, list[str]] = defaultdict(list)

    for row in failed_queries:
        query = str(row.get("query", "")).strip()
        if not query:
            continue
        row_weight = _row_weight(row)
        unique_tokens = set(tokenize_query(query))
        for token in unique_tokens:
            reasons = candidate_reasons(token, cfg)
            if not reasons:
                continue
            weighted_counts[token] += row_weight
            document_frequency[token] += 1
            if len(examples[token]) < cfg.max_examples_per_candidate:
                examples[token].append(query)

    total_docs = max(len([row for row in failed_queries if row.get("query")]), 1)
    candidates: list[AliasCandidate] = []
    for token, weighted_count in weighted_counts.items():
        if weighted_count < cfg.min_weighted_count:
            continue
        df = document_frequency[token]
        score, score_breakdown = _candidate_score(
            token=token,
            weighted_count=weighted_count,
            document_frequency=df,
            total_docs=total_docs,
            config=cfg,
        )
        if score < cfg.min_score:
            continue
        candidates.append(
            AliasCandidate(
                surface=token,
                weighted_count=float(weighted_count),
                document_frequency=int(df),
                score=score,
                reasons=tuple(candidate_reasons(token, cfg)),
                score_breakdown=score_breakdown,
                example_queries=tuple(examples[token]),
            )
        )

    return sorted(
        candidates,
        key=lambda item: (-item.score, -item.weighted_count, item.surface),
    )[: cfg.max_candidates]


def candidate_reasons(
    token: str, config: CandidateDiscoveryConfig | None = None
) -> list[str]:
    """Return reasons that make a token worth reviewing, or an empty list."""

    cfg = config or CandidateDiscoveryConfig()
    normalized = _normalize_token(token)
    if not normalized:
        return []
    if len(normalized) < cfg.min_token_length:
        return []
    if len(normalized) > cfg.max_token_length:
        return []
    if normalized in cfg.stop_words or normalized in cfg.noise_tokens:
        return []
    if normalized in cfg.known_terms:
        return []
    if _looks_private_or_identifier(normalized):
        return []

    reasons: list[str] = []
    if _has_digit_and_alpha(normalized):
        reasons.append("mixed_alpha_digit")
    if 2 <= len(normalized) <= 5 and normalized.isalpha():
        reasons.append("short_alias_like")
    if "_" in normalized or "/" in normalized or "-" in normalized:
        reasons.append("compound_surface")
    if normalized.endswith("db") or normalized.endswith("svc"):
        reasons.append("domain_suffix")

    return reasons


def build_candidate_discovery_report(
    failed_queries: Sequence[Mapping[str, Any]],
    *,
    config: CandidateDiscoveryConfig | None = None,
    binding_id: int | None = None,
    profile_name: str | None = None,
) -> JsonDict:
    """Return a JSON report suitable for CLI preview and later agent runs."""

    cfg = config or CandidateDiscoveryConfig()
    candidates = discover_alias_candidates(failed_queries, config=cfg)
    query_count = len([row for row in failed_queries if row.get("query")])
    return {
        "schema_version": "skeinrank.agent_candidate_discovery.v1",
        "runner": "openrouter_alias_scout",
        "llm_enabled": False,
        "binding_id": binding_id,
        "profile_name": profile_name,
        "queries_loaded": query_count,
        "candidates_found": len(candidates),
        "config": {
            "max_candidates": cfg.max_candidates,
            "min_token_length": cfg.min_token_length,
            "min_weighted_count": cfg.min_weighted_count,
            "min_score": cfg.min_score,
            "max_examples_per_candidate": cfg.max_examples_per_candidate,
            "background_terms": sorted(cfg.background_terms),
            "jargon_weight": cfg.jargon_weight,
            "surface_risk_weight": cfg.surface_risk_weight,
            "background_penalty_weight": cfg.background_penalty_weight,
        },
        "candidates": [candidate.to_dict() for candidate in candidates],
    }


def build_candidate_fact_pack(
    candidate: AliasCandidate,
    *,
    binding_id: int | None = None,
    profile_name: str | None = None,
    known_conflicts: Sequence[str] = (),
) -> JsonDict:
    """Build the compact pre-LLM fact pack for one discovered candidate."""

    return {
        "candidate_alias": candidate.surface,
        "possible_canonical": None,
        "slot": None,
        "binding_id": binding_id,
        "profile_name": profile_name,
        "evidence": [f"failed query: {query}" for query in candidate.example_queries],
        "stats": {
            "weighted_count": round(candidate.weighted_count, 4),
            "document_frequency": candidate.document_frequency,
            "discovery_score": round(candidate.score, 4),
            "discovery_reasons": list(candidate.reasons),
            "score_breakdown": _round_score_breakdown(candidate.score_breakdown),
        },
        "known_conflicts": [item for item in known_conflicts if item],
    }


def _candidate_score(
    *,
    token: str,
    weighted_count: float,
    document_frequency: int,
    total_docs: int,
    config: CandidateDiscoveryConfig,
) -> tuple[float, JsonDict]:
    idf = math.log((1 + total_docs) / (1 + document_frequency)) + 1.0
    frequency_score = weighted_count * idf
    jargon_score, jargon_reasons = _jargon_score(token, config)
    background_penalty = _background_penalty(token, config)
    surface_risk_score, surface_risk_reasons = _surface_risk_score(token, config)
    score = frequency_score
    score += config.jargon_weight * jargon_score
    score += config.surface_risk_weight * surface_risk_score
    score -= config.background_penalty_weight * background_penalty
    if _has_digit_and_alpha(token):
        score += 1.5
    if 2 <= len(token) <= 4:
        score += 1.0
    if "_" in token or "/" in token or "-" in token:
        score += 0.5
    breakdown: JsonDict = {
        "frequency_score": frequency_score,
        "jargon_score": jargon_score,
        "surface_risk_score": surface_risk_score,
        "token_fragmentation_score": None,
        "oov_score": None,
        "tokenizer_signal_status": "unavailable",
        "background_penalty": background_penalty,
        "reasons": sorted(set([*jargon_reasons, *surface_risk_reasons])),
    }
    return float(max(score, 0.0)), breakdown


def _jargon_score(
    token: str, config: CandidateDiscoveryConfig
) -> tuple[float, list[str]]:
    normalized = _normalize_token(token)
    if not normalized:
        return 0.0, []
    background_terms = config.background_terms | config.stop_words | config.noise_tokens
    parts = [part for part in re.split(r"[_.+#/-]+", normalized) if part]
    if not parts:
        return 0.0, []
    common_count = sum(1 for part in parts if part in background_terms)
    uncommon_ratio = 1.0 - (common_count / len(parts))
    score = 0.2 + (0.65 * uncommon_ratio)
    reasons: list[str] = []
    if uncommon_ratio >= 0.75:
        reasons.append("rare_against_background")
    elif uncommon_ratio > 0.0:
        reasons.append("mixed_background_and_domain_language")
    else:
        reasons.append("common_background_language")
    if _has_digit_and_alpha(normalized) or any(
        separator in normalized for separator in ("_", "/", "-", ".", "+")
    ):
        score += 0.15
        reasons.append("identifier_like_surface")
    if 2 <= len(normalized) <= 5 and normalized.isalpha():
        score += 0.1
        reasons.append("short_alias_like")
    return min(score, 1.0), reasons


def _surface_risk_score(
    token: str, config: CandidateDiscoveryConfig
) -> tuple[float, list[str]]:
    """Return a lightweight tokenizer-risk proxy for the standalone example.

    The example intentionally does not import embedding tokenizers. This score
    highlights compact aliases and code-shaped surfaces that are likely to be
    fragile in retrieval, while leaving true OOV fields empty until a tokenizer
    provider is connected in production code.
    """

    normalized = _normalize_token(token)
    if not normalized:
        return 0.0, []

    score = 0.0
    reasons: list[str] = []
    background_terms = config.background_terms | config.stop_words | config.noise_tokens
    parts = [part for part in re.split(r"[_.+#/-]+", normalized) if part]

    if 2 <= len(normalized.replace("-", "")) <= 5 and any(
        ch.isalpha() for ch in normalized
    ):
        score += 0.22
        reasons.append("compact_surface_risk")
    if _has_digit_and_alpha(normalized):
        score += 0.28
        reasons.append("alpha_digit_tokenizer_risk")
    if any(separator in normalized for separator in ("_", "/", "-", ".", "+")):
        score += 0.25
        reasons.append("separator_tokenizer_risk")
    if parts and all(part not in background_terms for part in parts):
        score += 0.17
        reasons.append("background_oov_proxy")

    return min(score, 1.0), reasons


def _background_penalty(token: str, config: CandidateDiscoveryConfig) -> float:
    normalized = _normalize_token(token)
    parts = [part for part in re.split(r"[_.+#/-]+", normalized) if part]
    if not parts:
        return 0.0
    background_terms = config.background_terms | config.stop_words | config.noise_tokens
    common_count = sum(1 for part in parts if part in background_terms)
    if common_count == len(parts):
        return 0.85
    if common_count:
        return 0.35 * (common_count / len(parts))
    return 0.0


def _round_score_breakdown(value: Mapping[str, Any]) -> JsonDict:
    rounded: JsonDict = {}
    for key, item in value.items():
        if isinstance(item, float):
            rounded[key] = round(item, 4)
        elif isinstance(item, list):
            rounded[key] = [entry for entry in item]
        else:
            rounded[key] = item
    return rounded


def _normalize_token(value: str) -> str:
    return value.strip().strip(".,:;!?()[]{}'\"").lower()


def _row_weight(row: Mapping[str, Any]) -> float:
    count = row.get("count", 1)
    try:
        value = float(count)
    except (TypeError, ValueError):
        value = 1.0
    return max(value, 1.0)


def _has_digit_and_alpha(token: str) -> bool:
    return any(ch.isdigit() for ch in token) and any(ch.isalpha() for ch in token)


def _looks_private_or_identifier(token: str) -> bool:
    if "@" in token or token.startswith("http"):
        return True
    if len(token) >= 16 and re.fullmatch(r"[a-f0-9-]+", token):
        return True
    if re.fullmatch(r"\d+", token):
        return True
    return False


__all__ = [
    "AliasCandidate",
    "CandidateDiscoveryConfig",
    "build_candidate_discovery_report",
    "build_candidate_fact_pack",
    "candidate_reasons",
    "discover_alias_candidates",
    "tokenize_query",
]
