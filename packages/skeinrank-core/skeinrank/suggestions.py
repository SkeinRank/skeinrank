"""Deterministic dictionary draft suggestions from local documents.

This module builds on the shared candidate discovery engine. It is intentionally
local and dependency-free: it scans documents, finds significant unmatched
terminology candidates, and returns a reviewable :class:`DictionaryDraft`.

The workflow is proposal-first. Suggested drafts do not mutate governance state,
snapshots, bindings, or runtime dictionaries. A human can review the draft and
explicitly convert accepted candidates into a runtime dictionary later.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator

from .candidates import (
    CandidateDiscoveryConfig,
    CandidateDiscoveryDocument,
    CandidateDiscoveryReport,
    DiscoveredCandidate,
    discover_candidates,
    discover_candidates_from_documents,
)
from .drafts import DictionaryDraft, DraftCandidate, DraftFinding, EvidenceSnippet
from .sdk import Dictionary

_DOCUMENT_SUFFIXES = frozenset(
    {
        ".txt",
        ".md",
        ".rst",
        ".log",
        ".csv",
        ".tsv",
        ".json",
        ".jsonl",
        ".yaml",
        ".yml",
        ".html",
        ".htm",
        ".docx",
        ".pdf",
    }
)


class DictionarySuggestionConfig(BaseModel):
    """Configuration for building a reviewable draft from discovered candidates."""

    profile_name: str = "suggested_terms"
    profile_description: str | None = (
        "Deterministic dictionary draft suggested from local documents."
    )
    default_slot: str = "TERM"
    source_label: str = "document_suggestion"
    discovery: CandidateDiscoveryConfig = Field(
        default_factory=CandidateDiscoveryConfig
    )

    @field_validator("profile_name", "default_slot", "source_label")
    @classmethod
    def _non_empty_text(cls, value: str) -> str:
        cleaned = " ".join(str(value).strip().split())
        if not cleaned:
            raise ValueError("suggestion config text fields must not be empty")
        return cleaned


class DictionarySuggestionResult(BaseModel):
    """Suggested draft plus the candidate discovery report behind it."""

    draft: DictionaryDraft
    discovery_report: CandidateDiscoveryReport

    def save(self, path: str | Path) -> None:
        """Write the suggested draft JSON to ``path``."""

        self.draft.save(path)

    def review_markdown(self) -> str:
        """Render the draft review markdown."""

        return self.draft.review_markdown()


def suggest_dictionary(
    documents: Sequence[str | Mapping[str, Any] | CandidateDiscoveryDocument],
    *,
    dictionary: str | Path | Mapping[str, Any] | Dictionary | None = None,
    config: DictionarySuggestionConfig | Mapping[str, Any] | None = None,
) -> DictionarySuggestionResult:
    """Suggest a reviewable dictionary draft from in-memory documents.

    The returned draft keeps every candidate in ``proposed`` status. Runtime
    dictionaries are created only after explicit review, for example with
    ``result.draft.accept_all().to_dictionary()`` in local preview code.
    """

    normalized_config = _coerce_suggestion_config(config)
    report = discover_candidates(
        documents,
        dictionary=dictionary,
        config=normalized_config.discovery,
    )
    draft = _draft_from_report(report, config=normalized_config)
    return DictionarySuggestionResult(draft=draft, discovery_report=report)


def suggest_dictionary_from_documents(
    paths: Sequence[str | Path],
    *,
    dictionary: str | Path | Mapping[str, Any] | Dictionary | None = None,
    config: DictionarySuggestionConfig | Mapping[str, Any] | None = None,
) -> DictionarySuggestionResult:
    """Suggest a reviewable dictionary draft from local files or directories."""

    normalized_config = _coerce_suggestion_config(config)
    document_paths = expand_document_paths(paths)
    report = discover_candidates_from_documents(
        document_paths,
        dictionary=dictionary,
        config=normalized_config.discovery,
    )
    draft = _draft_from_report(
        report,
        config=normalized_config,
        source_path=", ".join(str(path) for path in document_paths),
    )
    return DictionarySuggestionResult(draft=draft, discovery_report=report)


def expand_document_paths(paths: Sequence[str | Path]) -> list[Path]:
    """Expand files and directories into supported local document paths."""

    if not paths:
        raise ValueError("At least one document path is required")

    expanded: list[Path] = []
    for raw_path in paths:
        path = Path(raw_path)
        if not path.exists():
            raise FileNotFoundError(f"Document path does not exist: {path}")
        if path.is_file():
            expanded.append(path)
            continue
        if path.is_dir():
            expanded.extend(
                child
                for child in sorted(path.rglob("*"))
                if child.is_file() and _is_supported_document_path(child)
            )
            continue
        raise ValueError(f"Document path is not a file or directory: {path}")

    if not expanded:
        raise ValueError("No supported documents found in the provided paths")
    return expanded


def _coerce_suggestion_config(
    config: DictionarySuggestionConfig | Mapping[str, Any] | None,
) -> DictionarySuggestionConfig:
    if config is None:
        return DictionarySuggestionConfig()
    if isinstance(config, DictionarySuggestionConfig):
        return config
    payload = dict(config)
    discovery_payload = payload.get("discovery")
    if isinstance(discovery_payload, Mapping):
        payload["discovery"] = CandidateDiscoveryConfig.model_validate(
            dict(discovery_payload)
        )
    return DictionarySuggestionConfig.model_validate(payload)


def _draft_from_report(
    report: CandidateDiscoveryReport,
    *,
    config: DictionarySuggestionConfig,
    source_path: str | None = None,
) -> DictionaryDraft:
    top_score = max((candidate.score for candidate in report.candidates), default=1.0)
    findings = [
        DraftFinding(
            severity="info",
            code="suggestion.generated",
            message=(
                "Review suggested candidates before converting the draft into a "
                "runtime dictionary. No production state was changed."
            ),
            source=config.source_label,
        )
    ]
    if not report.candidates:
        findings.append(
            DraftFinding(
                severity="warn",
                code="suggestion.empty",
                message="No significant unmatched terminology candidates were found.",
                source=config.source_label,
            )
        )
    candidates = [
        _candidate_from_discovered(
            candidate,
            config=config,
            top_score=top_score,
        )
        for candidate in report.candidates
    ]
    return DictionaryDraft(
        profile_name=config.profile_name,
        profile_description=config.profile_description,
        source_path=source_path,
        source_format="documents",
        candidates=candidates,
        findings=findings,
    )


def _candidate_from_discovered(
    candidate: DiscoveredCandidate,
    *,
    config: DictionarySuggestionConfig,
    top_score: float,
) -> DraftCandidate:
    canonical_value = _canonical_value(candidate)
    aliases = _aliases_for_candidate(candidate, canonical_value=canonical_value)
    evidence_score = _relative_score(candidate.score, top_score=top_score)
    evidence = [
        EvidenceSnippet(
            source=item.source,
            line=item.line,
            text=item.text,
            score=evidence_score,
        )
        for item in candidate.evidence
    ]
    findings = [
        DraftFinding(
            severity="info",
            code="suggestion.candidate_stats",
            message=(
                f"Detected as {candidate.kind}; {candidate.mention_count} mention(s) "
                f"across {candidate.document_count} document(s)."
            ),
            source=config.source_label,
        )
    ]
    return DraftCandidate(
        canonical_value=canonical_value,
        aliases=aliases,
        slot=config.default_slot,
        confidence=evidence_score,
        status="proposed",
        source=config.source_label,
        evidence=evidence,
        findings=findings,
    )


def _canonical_value(candidate: DiscoveredCandidate) -> str:
    if candidate.kind in {"acronym", "alphanumeric", "camel_case"}:
        return candidate.value.strip()
    return candidate.normalized_value.strip() or candidate.value.strip()


def _aliases_for_candidate(
    candidate: DiscoveredCandidate,
    *,
    canonical_value: str,
) -> list[str]:
    aliases: list[str] = []
    surface = candidate.value.strip()
    if surface and surface.casefold() != canonical_value.casefold():
        aliases.append(surface)
    if (
        candidate.normalized_value
        and candidate.normalized_value.casefold() != canonical_value.casefold()
        and candidate.normalized_value.casefold() != surface.casefold()
    ):
        aliases.append(candidate.normalized_value)
    return aliases


def _relative_score(score: float, *, top_score: float) -> float:
    if top_score <= 0:
        return 0.5
    normalized = max(0.0, min(1.0, score / top_score))
    return round(0.35 + normalized * 0.55, 3)


def _is_supported_document_path(path: Path) -> bool:
    return path.suffix.lower() in _DOCUMENT_SUFFIXES
