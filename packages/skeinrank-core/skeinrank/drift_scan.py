"""Local dictionary-vs-corpus terminology drift scans.

The scanner compares a SkeinRank dictionary with local documents and emits a
reviewable :class:`TerminologyDriftReport`. It is intentionally deterministic
and local: it does not call model providers, mutate governance state, publish
snapshots, update bindings, or touch production runtime configuration.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator

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


class DriftScanConfig(BaseModel):
    """Configuration for a local dictionary-vs-corpus drift scan."""

    profile_name: str | None = None
    binding_id: str | None = None
    pinned_snapshot_version: str | None = None
    latest_snapshot_version: str | None = None
    critical_min_mentions: int = Field(default=10, ge=1)
    include_stale_terms: bool = True
    stale_term_max_mentions: int = Field(default=0, ge=0)
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


def scan_dictionary_drift(
    *,
    dictionary: str | Path | Mapping[str, Any] | Dictionary,
    docs: Sequence[str | Path],
    config: DriftScanConfig | Mapping[str, Any] | None = None,
) -> TerminologyDriftReport:
    """Scan local documents for terminology not covered by a dictionary.

    The current MVP emits ``alias_drift`` findings for significant unmatched
    candidates and ``stale_term`` findings for dictionary terms with little or
    no evidence in the scanned corpus. It computes ``unknown_alias_rate`` from
    local evidence. It is a report-only workflow and never writes proposals,
    snapshots, bindings, or runtime dictionaries.
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
    findings = [*alias_findings, *stale_findings]
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
