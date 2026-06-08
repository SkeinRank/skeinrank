"""Local dictionary-vs-corpus terminology drift scans.

The scanner compares a SkeinRank dictionary with local documents and emits a
reviewable :class:`TerminologyDriftReport`. It is intentionally deterministic
and local: it does not call model providers, mutate governance state, publish
snapshots, update bindings, or touch production runtime configuration.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
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
    candidates and computes ``unknown_alias_rate`` from local evidence. It is a
    report-only workflow and never writes proposals, snapshots, bindings, or
    runtime dictionaries.
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
    known_match_count = _known_match_count(normalized_documents, loaded_dictionary)
    unknown_mentions = candidate_report.total_mentions
    denominator = known_match_count + unknown_mentions
    unknown_alias_rate = (unknown_mentions / denominator) if denominator else 0.0
    top_score = max(
        (candidate.score for candidate in candidate_report.candidates), default=1.0
    )
    findings = [
        _alias_drift_finding(
            candidate,
            config=normalized_config,
            top_score=top_score,
        )
        for candidate in candidate_report.candidates
    ]
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
            "known_dictionary_match_count": known_match_count,
            "known_term_count": candidate_report.known_term_count,
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


def _known_match_count(
    documents: Sequence[CandidateDiscoveryDocument],
    dictionary: Dictionary,
) -> int:
    count = 0
    for document in documents:
        result = extract_terms(document.text, dictionary=dictionary)
        count += result.match_count
    return count


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
