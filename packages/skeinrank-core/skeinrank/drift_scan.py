"""Local dictionary-vs-corpus terminology drift scans.

The scanner compares a SkeinRank dictionary with local documents and emits a
reviewable :class:`TerminologyDriftReport`. It is intentionally deterministic
and local: it does not call model providers, mutate governance state, publish
snapshots, update bindings, or touch production runtime configuration.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .candidates import (
    CandidateDiscoveryConfig,
    CandidateDiscoveryDocument,
    CandidateEvidence,
    DiscoveredCandidate,
    discover_candidates,
)
from .documents import extract_document_text
from .drift import (
    DriftEvidence,
    DriftFinding,
    DriftFindingType,
    DriftSeverity,
    TerminologyDriftReport,
)
from .sdk import Dictionary, extract_terms, load_dictionary
from .suggestions import expand_document_paths


class BindingLagMetadata(BaseModel):
    """Optional binding snapshot metadata used by local drift scans.

    This is a file/input adapter for report metadata only. Loading binding lag
    metadata does not call the Governance API and does not update bindings,
    snapshots, runtime dictionaries, or production search configuration.
    """

    model_config = ConfigDict(populate_by_name=True)

    profile_name: str | None = None
    binding_id: str | None = None
    pinned_snapshot_version: str | None = None
    latest_snapshot_version: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "profile_name",
        "binding_id",
        "pinned_snapshot_version",
        "latest_snapshot_version",
        mode="before",
    )
    @classmethod
    def _clean_optional_text(cls, value: Any) -> Any:
        if value is None:
            return None
        cleaned = " ".join(str(value).strip().split())
        return cleaned or None

    @classmethod
    def from_file(cls, path: str | Path) -> "BindingLagMetadata":
        """Load binding metadata from a JSON file."""

        return load_binding_metadata(path)


def load_binding_metadata(path: str | Path) -> BindingLagMetadata:
    """Load optional binding lag metadata from a local JSON file.

    Accepted keys include ``binding_id``, ``profile_name``,
    ``pinned_snapshot_version``/``pinned_snapshot`` and
    ``latest_snapshot_version``/``latest_snapshot``. Unknown keys are preserved in
    ``details`` for report context.
    """

    raw_path = Path(path)
    payload = json.loads(raw_path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("Binding metadata root must be an object")
    normalized = _normalize_binding_metadata_payload(payload)
    return BindingLagMetadata.model_validate(normalized)


def _normalize_binding_metadata_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    known_keys = {
        "profile_name",
        "profile",
        "binding_id",
        "binding",
        "pinned_snapshot_version",
        "pinned_snapshot",
        "pinned_snapshot_id",
        "pinned_version",
        "latest_snapshot_version",
        "latest_snapshot",
        "latest_approved_snapshot_version",
        "latest_snapshot_id",
        "latest_version",
    }
    return {
        "profile_name": payload.get("profile_name") or payload.get("profile"),
        "binding_id": payload.get("binding_id") or payload.get("binding"),
        "pinned_snapshot_version": (
            payload.get("pinned_snapshot_version")
            or payload.get("pinned_snapshot")
            or payload.get("pinned_snapshot_id")
            or payload.get("pinned_version")
        ),
        "latest_snapshot_version": (
            payload.get("latest_snapshot_version")
            or payload.get("latest_snapshot")
            or payload.get("latest_approved_snapshot_version")
            or payload.get("latest_snapshot_id")
            or payload.get("latest_version")
        ),
        "details": {
            key: value for key, value in payload.items() if key not in known_keys
        },
    }


class DriftScanConfig(BaseModel):
    """Configuration for a local dictionary-vs-corpus drift scan."""

    profile_name: str | None = None
    binding_id: str | None = None
    pinned_snapshot_version: str | None = None
    latest_snapshot_version: str | None = None
    critical_min_mentions: int = Field(default=10, ge=1)
    include_stale_terms: bool = True
    stale_term_max_mentions: int = Field(default=0, ge=0)
    include_binding_lag: bool = True
    critical_binding_lag_snapshots: int = Field(default=5, ge=1)
    include_ambiguity_signals: bool = True
    ambiguity_min_mentions: int = Field(default=2, ge=1)
    ambiguity_min_document_count: int = Field(default=1, ge=1)
    ambiguity_min_context_terms: int = Field(default=2, ge=1)
    ambiguity_context_window: int = Field(default=6, ge=2, le=16)
    discovery: CandidateDiscoveryConfig = Field(
        default_factory=CandidateDiscoveryConfig
    )

    @field_validator(
        "profile_name",
        "binding_id",
        "pinned_snapshot_version",
        "latest_snapshot_version",
        mode="before",
    )
    @classmethod
    def _clean_optional_text(cls, value: Any) -> Any:
        if value is None:
            return None
        cleaned = " ".join(str(value).strip().split())
        return cleaned or None


def merge_binding_metadata(
    config: DriftScanConfig | Mapping[str, Any] | None,
    metadata: BindingLagMetadata | Mapping[str, Any] | str | Path | None,
) -> DriftScanConfig:
    """Return scan config with binding metadata applied.

    Explicit values already present in ``config`` win over metadata. This keeps
    CLI flags and caller-provided config deterministic while still allowing a
    small metadata file to fill report context.
    """

    merged = _coerce_config(config).model_copy(deep=True)
    if metadata is None:
        return merged
    if isinstance(metadata, BindingLagMetadata):
        loaded = metadata
    elif isinstance(metadata, (str, Path)):
        loaded = load_binding_metadata(metadata)
    else:
        loaded = BindingLagMetadata.model_validate(
            _normalize_binding_metadata_payload(metadata)
        )

    if loaded.profile_name and not merged.profile_name:
        merged.profile_name = loaded.profile_name
    if loaded.binding_id and not merged.binding_id:
        merged.binding_id = loaded.binding_id
    if loaded.pinned_snapshot_version and not merged.pinned_snapshot_version:
        merged.pinned_snapshot_version = loaded.pinned_snapshot_version
    if loaded.latest_snapshot_version and not merged.latest_snapshot_version:
        merged.latest_snapshot_version = loaded.latest_snapshot_version
    return merged


def scan_dictionary_drift(
    *,
    dictionary: str | Path | Mapping[str, Any] | Dictionary,
    docs: Sequence[str | Path],
    config: DriftScanConfig | Mapping[str, Any] | None = None,
) -> TerminologyDriftReport:
    """Scan local documents for terminology not covered by a dictionary.

    The scanner emits ``alias_drift`` findings for significant unmatched
    candidates, ``stale_term`` findings for dictionary terms with little or no
    evidence in the scanned corpus, optional ``binding_lag`` findings, and
    conservative ``ambiguity_signal`` findings for short aliases that appear in
    unfamiliar contexts. It computes ``unknown_alias_rate`` from local evidence.
    It is a report-only workflow and never writes proposals, snapshots,
    bindings, or runtime dictionaries.
    """

    normalized_config = _coerce_config(config)
    loaded_dictionary = load_dictionary(dictionary)
    document_paths = expand_document_paths(docs)
    documents = [
        CandidateDiscoveryDocument(
            source=str(path),
            text=extract_document_text(path).text,
        )
        for path in document_paths
    ]
    return scan_dictionary_drift_from_documents(
        dictionary=loaded_dictionary,
        documents=documents,
        config=normalized_config,
    )


def scan_dictionary_drift_from_documents(
    *,
    dictionary: str | Path | Mapping[str, Any] | Dictionary,
    documents: Sequence[str | Mapping[str, Any] | CandidateDiscoveryDocument],
    config: DriftScanConfig | Mapping[str, Any] | None = None,
) -> TerminologyDriftReport:
    """Scan in-memory documents and return a terminology drift report."""

    normalized_config = _coerce_config(config)
    loaded_dictionary = load_dictionary(dictionary)
    normalized_documents = _coerce_documents(documents)
    candidate_report = discover_candidates(
        normalized_documents,
        dictionary=loaded_dictionary,
        config=normalized_config.discovery,
    )
    match_stats = _dictionary_match_stats(normalized_documents, loaded_dictionary)
    unknown_mentions = candidate_report.total_mentions
    denominator = match_stats.total_match_count + unknown_mentions
    unknown_alias_rate = (unknown_mentions / denominator) if denominator else 0.0
    top_score = max(
        (candidate.score for candidate in candidate_report.candidates), default=1.0
    )
    alias_findings = [
        _alias_drift_finding(
            candidate,
            config=normalized_config,
            top_score=top_score,
        )
        for candidate in candidate_report.candidates
    ]
    stale_findings = (
        _stale_term_findings(
            loaded_dictionary,
            match_stats=match_stats,
            config=normalized_config,
        )
        if normalized_config.include_stale_terms
        else []
    )
    binding_lag_findings = (
        _binding_lag_findings(normalized_config)
        if normalized_config.include_binding_lag
        else []
    )
    ambiguity_findings = (
        _ambiguity_signal_findings(
            loaded_dictionary,
            normalized_documents,
            config=normalized_config,
        )
        if normalized_config.include_ambiguity_signals
        else []
    )
    findings = [
        *alias_findings,
        *stale_findings,
        *binding_lag_findings,
        *ambiguity_findings,
    ]
    runtime_term_count = _runtime_term_count(loaded_dictionary)
    covered_term_count = sum(
        1
        for count in match_stats.term_mentions.values()
        if count > normalized_config.stale_term_max_mentions
    )
    profile_name = normalized_config.profile_name or loaded_dictionary.profile_name
    notes = [
        "Local drift scan only; no governance, snapshot, binding, or runtime state was changed."
    ]
    if not findings:
        notes.append("No significant unmatched terminology candidates were detected.")
    return TerminologyDriftReport(
        profile_name=profile_name,
        binding_id=normalized_config.binding_id,
        dictionary_schema_version=loaded_dictionary.schema_version,
        pinned_snapshot_version=normalized_config.pinned_snapshot_version,
        latest_snapshot_version=normalized_config.latest_snapshot_version,
        document_count=len(normalized_documents),
        source_count=len({document.source for document in normalized_documents}),
        metrics={
            "unknown_alias_rate": round(unknown_alias_rate, 6),
            "unknown_candidate_count": candidate_report.candidate_count,
            "unknown_candidate_mentions": unknown_mentions,
            "known_dictionary_match_count": match_stats.total_match_count,
            "known_term_count": candidate_report.known_term_count,
            "dictionary_term_count": runtime_term_count,
            "covered_dictionary_term_count": covered_term_count,
            "stale_term_count": len(stale_findings),
            "stale_term_max_mentions": normalized_config.stale_term_max_mentions,
            "binding_lag_count": len(binding_lag_findings),
            "binding_snapshot_lag": _binding_snapshot_lag_value(normalized_config),
            "ambiguity_signal_count": len(ambiguity_findings),
        },
        findings=findings,
        notes=notes,
    )


def _alias_drift_finding(
    candidate: DiscoveredCandidate,
    *,
    config: DriftScanConfig,
    top_score: float,
) -> DriftFinding:
    confidence = _relative_score(candidate.score, top_score=top_score)
    severity = (
        DriftSeverity.CRITICAL
        if candidate.mention_count >= config.critical_min_mentions
        else DriftSeverity.WARN
    )
    return DriftFinding(
        finding_type=DriftFindingType.ALIAS_DRIFT,
        severity=severity,
        title=f"Unmatched terminology candidate: {candidate.value}",
        description=(
            "This term or phrase appears in the scanned corpus but is not covered "
            "by the current dictionary canonical values or aliases."
        ),
        value=candidate.value,
        normalized_value=candidate.normalized_value,
        metrics={
            "mention_count": candidate.mention_count,
            "document_count": candidate.document_count,
            "candidate_score": candidate.score,
            "confidence": confidence,
        },
        evidence=[
            _drift_evidence(item, score=confidence) for item in candidate.evidence
        ],
        recommended_action=(
            "Review this candidate before creating a dictionary proposal or draft alias."
        ),
        details={"candidate_kind": candidate.kind},
    )


def _drift_evidence(item: CandidateEvidence, *, score: float) -> DriftEvidence:
    return DriftEvidence(
        source=item.source,
        line=item.line,
        text=item.text,
        score=score,
    )


@dataclass(frozen=True)
class _DictionaryMatchStats:
    total_match_count: int
    term_mentions: Counter[str]
    term_documents: Counter[str]


def _dictionary_match_stats(
    documents: Sequence[CandidateDiscoveryDocument],
    dictionary: Dictionary,
) -> _DictionaryMatchStats:
    term_mentions: Counter[str] = Counter()
    term_documents: Counter[str] = Counter()
    total_match_count = 0
    for document in documents:
        result = extract_terms(document.text, dictionary=dictionary)
        total_match_count += result.match_count
        seen_in_document: set[str] = set()
        for match in result.matches:
            normalized = _normalize_value(match.canonical_value)
            term_mentions[normalized] += 1
            seen_in_document.add(normalized)
        for normalized in seen_in_document:
            term_documents[normalized] += 1
    return _DictionaryMatchStats(
        total_match_count=total_match_count,
        term_mentions=term_mentions,
        term_documents=term_documents,
    )


def _stale_term_findings(
    dictionary: Dictionary,
    *,
    match_stats: _DictionaryMatchStats,
    config: DriftScanConfig,
) -> list[DriftFinding]:
    findings: list[DriftFinding] = []
    for term in dictionary.terms:
        if term.status not in {"active", "deprecated"}:
            continue
        normalized = _normalize_value(term.canonical_value)
        mention_count = int(match_stats.term_mentions[normalized])
        if mention_count > config.stale_term_max_mentions:
            continue
        document_count = int(match_stats.term_documents[normalized])
        severity = (
            DriftSeverity.INFO if term.status == "deprecated" else DriftSeverity.WARN
        )
        findings.append(
            DriftFinding(
                finding_type=DriftFindingType.STALE_TERM,
                severity=severity,
                title=f"Dictionary term has little or no corpus evidence: {term.canonical_value}",
                description=(
                    "This canonical term is present in the dictionary but was not "
                    "observed above the configured evidence threshold in the scanned corpus."
                ),
                value=term.canonical_value,
                canonical_value=term.canonical_value,
                normalized_value=normalized,
                metrics={
                    "mention_count": mention_count,
                    "document_count": document_count,
                    "alias_count": len(term.aliases),
                    "stale_term_max_mentions": config.stale_term_max_mentions,
                },
                recommended_action=(
                    "Review whether this term should stay active, be deprecated, "
                    "or remain for compatibility with older content."
                ),
                details={
                    "slot": term.slot,
                    "status": term.status,
                    "aliases": [alias.value for alias in term.aliases],
                },
            )
        )
    return findings


def _binding_lag_findings(config: DriftScanConfig) -> list[DriftFinding]:
    pinned = config.pinned_snapshot_version
    latest = config.latest_snapshot_version
    if not pinned or not latest or pinned == latest:
        return []

    lag = _snapshot_version_lag(pinned, latest)
    severity = (
        DriftSeverity.CRITICAL
        if lag is not None and lag >= config.critical_binding_lag_snapshots
        else DriftSeverity.WARN
    )
    lag_label = (
        f"{lag} snapshot(s)" if lag is not None else "different snapshot versions"
    )
    return [
        DriftFinding(
            finding_type=DriftFindingType.BINDING_LAG,
            severity=severity,
            title="Binding pinned snapshot is behind the latest approved snapshot",
            description=(
                "The drift report metadata shows that this binding is pinned to an "
                "older snapshot than the latest approved snapshot. Review rollout "
                "readiness before changing the binding."
            ),
            value=config.binding_id or "binding",
            binding_id=config.binding_id,
            pinned_snapshot_version=pinned,
            latest_snapshot_version=latest,
            metrics={
                "binding_snapshot_lag": lag if lag is not None else 1,
                "binding_snapshot_lag_parseable": lag is not None,
                "critical_binding_lag_snapshots": config.critical_binding_lag_snapshots,
            },
            recommended_action=(
                f"Review whether this binding should move from `{pinned}` to "
                f"`{latest}` after validation. Current lag: {lag_label}."
            ),
            details={
                "pinned_snapshot_version": pinned,
                "latest_snapshot_version": latest,
            },
        )
    ]


def _binding_snapshot_lag_value(config: DriftScanConfig) -> int:
    pinned = config.pinned_snapshot_version
    latest = config.latest_snapshot_version
    if not pinned or not latest:
        return 0
    if pinned == latest:
        return 0
    lag = _snapshot_version_lag(pinned, latest)
    return lag if lag is not None else 1


def _snapshot_version_lag(pinned: str, latest: str) -> int | None:
    pinned_number = _snapshot_ordinal(pinned)
    latest_number = _snapshot_ordinal(latest)
    if pinned_number is None or latest_number is None:
        return None
    return max(0, latest_number - pinned_number)


def _snapshot_ordinal(value: str) -> int | None:
    matches = re.findall(r"\d+", str(value))
    if not matches:
        return None
    return int(matches[-1])


@dataclass
class _AliasContextStats:
    alias: str
    canonical_value: str
    slot: str
    aliases: list[str]
    governed_context_terms: set[str]
    context_terms: Counter[str]
    sources: set[str]
    evidence: list[DriftEvidence]
    mention_count: int = 0

    @property
    def document_count(self) -> int:
        return len(self.sources)


def _ambiguity_signal_findings(
    dictionary: Dictionary,
    documents: Sequence[CandidateDiscoveryDocument],
    *,
    config: DriftScanConfig,
) -> list[DriftFinding]:
    """Return review signals for aliases appearing in unfamiliar contexts.

    This detector is intentionally conservative. It does not infer a new
    canonical meaning for an alias. It only flags short/high-risk aliases when
    the surrounding corpus context contains enough terms that are not part of
    the governed dictionary context for the current canonical term.
    """

    contexts = _collect_alias_contexts(
        dictionary,
        documents,
        context_window=config.ambiguity_context_window,
    )
    findings: list[DriftFinding] = []
    for stats in contexts.values():
        if stats.mention_count < config.ambiguity_min_mentions:
            continue
        if stats.document_count < config.ambiguity_min_document_count:
            continue
        novel_terms = [
            term
            for term, _count in stats.context_terms.most_common()
            if term not in stats.governed_context_terms
            and term not in _alias_context_stop_terms(stats)
        ]
        if len(novel_terms) < config.ambiguity_min_context_terms:
            continue
        severity = (
            DriftSeverity.CRITICAL
            if stats.mention_count >= config.critical_min_mentions
            else DriftSeverity.WARN
        )
        top_terms = novel_terms[:8]
        findings.append(
            DriftFinding(
                finding_type=DriftFindingType.AMBIGUITY_SIGNAL,
                severity=severity,
                title=f"Alias appears in unfamiliar contexts: {stats.alias}",
                description=(
                    "This alias is already governed by the dictionary, but the "
                    "scanned corpus uses it near context terms that are not part "
                    "of the current governed dictionary context. This is a review "
                    "signal only; the scanner did not infer a new meaning."
                ),
                value=stats.alias,
                canonical_value=stats.canonical_value,
                normalized_value=_normalize_value(stats.alias),
                metrics={
                    "mention_count": stats.mention_count,
                    "document_count": stats.document_count,
                    "novel_context_term_count": len(novel_terms),
                    "ambiguity_min_context_terms": config.ambiguity_min_context_terms,
                    "ambiguity_context_window": config.ambiguity_context_window,
                },
                evidence=stats.evidence,
                recommended_action=(
                    "Review the evidence before adding context triggers, binding "
                    "rules, or a separate dictionary proposal for this alias."
                ),
                details={
                    "slot": stats.slot,
                    "aliases": stats.aliases,
                    "governed_context_terms": sorted(stats.governed_context_terms)[:20],
                    "novel_context_terms": top_terms,
                },
            )
        )
    findings.sort(
        key=lambda finding: (
            -int(finding.metrics.get("mention_count", 0)),
            str(finding.value or ""),
        )
    )
    return findings


def _collect_alias_contexts(
    dictionary: Dictionary,
    documents: Sequence[CandidateDiscoveryDocument],
    *,
    context_window: int,
) -> dict[tuple[str, str], _AliasContextStats]:
    alias_terms = _alias_terms(dictionary)
    contexts: dict[tuple[str, str], _AliasContextStats] = {}
    for document in documents:
        result = extract_terms(document.text, dictionary=dictionary)
        token_spans = _token_spans(document.text)
        for match in result.matches:
            normalized_alias = _normalize_value(match.alias)
            term = alias_terms.get(
                (normalized_alias, _normalize_value(match.canonical_value))
            )
            if term is None:
                continue
            if not _is_high_risk_alias(
                match.alias, canonical_value=match.canonical_value
            ):
                continue
            key = (normalized_alias, _normalize_value(term.canonical_value))
            stats = contexts.get(key)
            if stats is None:
                governed_terms = _governed_context_terms(term)
                stats = _AliasContextStats(
                    alias=match.alias,
                    canonical_value=term.canonical_value,
                    slot=term.slot,
                    aliases=[alias.value for alias in term.aliases],
                    governed_context_terms=governed_terms,
                    context_terms=Counter(),
                    sources=set(),
                    evidence=[],
                )
                contexts[key] = stats
            stats.mention_count += 1
            stats.sources.add(document.source)
            context_terms = _match_context_terms(
                document.text,
                token_spans,
                match.start,
                match.end,
                window=context_window,
            )
            for term_value in context_terms:
                if term_value:
                    stats.context_terms[term_value] += 1
            if len(stats.evidence) < 3:
                stats.evidence.append(
                    DriftEvidence(
                        source=document.source,
                        line=_line_number(document.text, match.start),
                        text=match.fragment,
                        score=0.66,
                        metadata={
                            "alias": match.alias,
                            "matched_text": match.matched_text,
                            "canonical_value": match.canonical_value,
                        },
                    )
                )
    return contexts


def _alias_terms(dictionary: Dictionary) -> dict[tuple[str, str], Any]:
    out: dict[tuple[str, str], Any] = {}
    for term in dictionary.terms:
        if term.status not in {"active", "deprecated"}:
            continue
        canonical = _normalize_value(term.canonical_value)
        out[(canonical, canonical)] = term
        for alias in term.aliases:
            if alias.status not in {"active", "deprecated"}:
                continue
            out[(_normalize_value(alias.value), canonical)] = term
    return out


def _governed_context_terms(term: Any) -> set[str]:
    values: list[str] = [
        term.canonical_value,
        term.slot,
        term.description or "",
        *term.tags,
        *(alias.value for alias in term.aliases),
    ]
    terms: set[str] = set()
    for value in values:
        terms.update(_context_tokenize(str(value)))
    terms.discard("")
    return terms


def _alias_context_stop_terms(stats: _AliasContextStats) -> set[str]:
    blocked = set(stats.governed_context_terms)
    blocked.update(_context_tokenize(stats.alias))
    blocked.update(_context_tokenize(stats.canonical_value))
    for alias in stats.aliases:
        blocked.update(_context_tokenize(alias))
    return blocked


def _is_high_risk_alias(alias: str, *, canonical_value: str) -> bool:
    normalized_alias = _normalize_value(alias)
    normalized_canonical = _normalize_value(canonical_value)
    if not normalized_alias or normalized_alias == normalized_canonical:
        return False
    return len(normalized_alias.replace(" ", "")) <= 4 or " " not in normalized_alias


def _match_context_terms(
    text: str,
    token_spans: Sequence[tuple[str, int, int]],
    start: int,
    end: int,
    *,
    window: int,
) -> list[str]:
    token_index = None
    for index, (_token, token_start, token_end) in enumerate(token_spans):
        if token_start <= start < token_end or start <= token_start < end:
            token_index = index
            break
    if token_index is None:
        return []
    left = max(0, token_index - window)
    right = min(len(token_spans), token_index + window + 1)
    return [
        token
        for token, token_start, token_end in token_spans[left:right]
        if not (token_start <= start < token_end or start <= token_start < end)
    ]


_TOKEN_SPAN_RE = re.compile(r"[A-Za-z][A-Za-z0-9]*(?:[._:/-][A-Za-z0-9]+)*")


def _token_spans(text: str) -> list[tuple[str, int, int]]:
    return [
        (normalized, match.start(), match.end())
        for match in _TOKEN_SPAN_RE.finditer(text)
        if (normalized := _normalize_context_token(match.group(0)))
    ]


def _context_tokenize(value: str) -> set[str]:
    return {
        token
        for token in (
            _normalize_context_token(part) for part in re.split(r"[\s._:/,-]+", value)
        )
        if token
    }


def _normalize_context_token(value: str) -> str:
    normalized = _normalize_value(value)
    if not normalized:
        return ""
    if normalized in _BASIC_CONTEXT_STOP_WORDS:
        return ""
    if len(normalized) <= 1:
        return ""
    return normalized


def _line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, max(0, offset)) + 1


_BASIC_CONTEXT_STOP_WORDS = {
    "a",
    "after",
    "and",
    "are",
    "as",
    "at",
    "before",
    "by",
    "for",
    "from",
    "in",
    "into",
    "is",
    "it",
    "near",
    "of",
    "on",
    "or",
    "the",
    "this",
    "to",
    "with",
}


def _runtime_term_count(dictionary: Dictionary) -> int:
    return sum(
        1 for term in dictionary.terms if term.status in {"active", "deprecated"}
    )


def _normalize_value(value: str) -> str:
    return " ".join(str(value).strip().casefold().split())


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
                    "drift scan document mappings must include text/content/body"
                )
            source = document.get("source") or document.get("path") or f"text-{index}"
            out.append(CandidateDiscoveryDocument(source=str(source), text=text))
            continue
        raise TypeError(
            "documents must be strings, mappings, or CandidateDiscoveryDocument"
        )
    if not out:
        raise ValueError("At least one document is required for drift scanning")
    return out


def _coerce_config(
    config: DriftScanConfig | Mapping[str, Any] | None,
) -> DriftScanConfig:
    if config is None:
        return DriftScanConfig()
    if isinstance(config, DriftScanConfig):
        return config
    payload = dict(config)
    discovery_payload = payload.get("discovery")
    if isinstance(discovery_payload, Mapping):
        payload["discovery"] = CandidateDiscoveryConfig.model_validate(
            dict(discovery_payload)
        )
    return DriftScanConfig.model_validate(payload)


def _relative_score(score: float, *, top_score: float) -> float:
    if top_score <= 0:
        return 0.5
    normalized = max(0.0, min(1.0, score / top_score))
    return round(0.35 + normalized * 0.55, 3)
