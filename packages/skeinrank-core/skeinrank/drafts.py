"""Reviewable dictionary drafts for imports and assistant workflows.

A dictionary draft is a local, review-oriented artifact. It can be created from
an imported dictionary, suggested candidates, or future agent output. It does not
mutate governance state, snapshots, bindings, or runtime dictionaries.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from .sdk import Dictionary, DictionaryAlias, DictionaryTerm, load_dictionary

DRAFT_SCHEMA_VERSION = "skeinrank.dictionary_draft.v1"
_DRAFT_STATUSES = frozenset({"proposed", "accepted", "rejected"})


class EvidenceSnippet(BaseModel):
    """Evidence attached to a draft candidate."""

    source: str | None = None
    line: int | None = None
    text: str | None = None
    score: float | None = Field(default=None, ge=0.0, le=1.0)

    @field_validator("source", "text")
    @classmethod
    def _clean_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = " ".join(value.strip().split())
        return cleaned or None


class DraftFinding(BaseModel):
    """Review finding attached to a dictionary draft."""

    severity: Literal["fatal", "warn", "info"] = "info"
    code: str
    message: str
    source: str = "draft"
    line: int | None = None

    @field_validator("code", "message", "source")
    @classmethod
    def _non_empty_text(cls, value: str) -> str:
        cleaned = " ".join(value.strip().split())
        if not cleaned:
            raise ValueError("draft finding text must not be empty")
        return cleaned


class DraftCandidate(BaseModel):
    """One proposed canonical term plus aliases and review metadata."""

    canonical_value: str
    aliases: list[str] = Field(default_factory=list)
    slot: str = "TERM"
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    status: Literal["proposed", "accepted", "rejected"] = "proposed"
    source: str = "draft"
    evidence: list[EvidenceSnippet] = Field(default_factory=list)
    findings: list[DraftFinding] = Field(default_factory=list)

    @field_validator("canonical_value", "slot", "source")
    @classmethod
    def _non_empty_text(cls, value: str) -> str:
        cleaned = " ".join(value.strip().split())
        if not cleaned:
            raise ValueError("draft candidate text must not be empty")
        return cleaned

    @field_validator("aliases")
    @classmethod
    def _normalize_aliases(cls, values: list[str]) -> list[str]:
        seen: set[str] = set()
        aliases: list[str] = []
        for value in values:
            cleaned = " ".join(str(value).strip().split())
            if not cleaned:
                continue
            key = cleaned.casefold()
            if key in seen:
                continue
            seen.add(key)
            aliases.append(cleaned)
        return aliases

    @model_validator(mode="after")
    def _canonical_not_in_aliases(self) -> "DraftCandidate":
        canonical = self.canonical_value.casefold()
        self.aliases = [
            alias for alias in self.aliases if alias.casefold() != canonical
        ]
        return self

    def accept(self) -> "DraftCandidate":
        """Return a copy marked as accepted."""

        return self.model_copy(update={"status": "accepted"})

    def reject(self) -> "DraftCandidate":
        """Return a copy marked as rejected."""

        return self.model_copy(update={"status": "rejected"})


class DictionaryDraft(BaseModel):
    """A reviewable local dictionary draft.

    Drafts are safe to generate from imports, local document suggestions, or
    future agent workflows because they are not runtime dictionaries. Converting
    a draft to a runtime dictionary is an explicit call to :meth:`to_dictionary`.
    """

    schema_version: str = DRAFT_SCHEMA_VERSION
    profile_name: str
    profile_description: str | None = None
    source_path: str | None = None
    source_format: str | None = None
    candidates: list[DraftCandidate] = Field(default_factory=list)
    findings: list[DraftFinding] = Field(default_factory=list)

    @field_validator("profile_name")
    @classmethod
    def _non_empty_profile_name(cls, value: str) -> str:
        cleaned = " ".join(value.strip().split())
        if not cleaned:
            raise ValueError("draft profile_name must not be empty")
        return cleaned

    @classmethod
    def from_dictionary(
        cls,
        dictionary: Dictionary | str | Path | Mapping[str, Any],
        *,
        source_path: str | None = None,
        source_format: str | None = None,
        findings: Iterable[DraftFinding | Mapping[str, Any] | object] = (),
        status: Literal["proposed", "accepted", "rejected"] = "proposed",
        source: str = "dictionary",
    ) -> "DictionaryDraft":
        """Create a draft from an existing SkeinRank dictionary."""

        loaded = load_dictionary(dictionary)
        normalized_status = _normalize_status(status)
        candidates = [
            DraftCandidate(
                canonical_value=term.canonical_value,
                aliases=[alias.value for alias in term.aliases],
                slot=term.slot,
                confidence=_mean_alias_confidence(term.aliases),
                status=normalized_status,
                source=source,
            )
            for term in loaded.terms
        ]
        return cls(
            profile_name=loaded.profile_name,
            profile_description=loaded.profile_description,
            source_path=source_path,
            source_format=source_format,
            candidates=candidates,
            findings=[_coerce_finding(finding) for finding in findings],
        )

    @classmethod
    def from_file(cls, path: str | Path) -> "DictionaryDraft":
        """Load a draft JSON file."""

        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.model_validate(payload)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "DictionaryDraft":
        """Load a draft from a mapping payload."""

        return cls.model_validate(dict(payload))

    @property
    def candidate_count(self) -> int:
        return len(self.candidates)

    @property
    def accepted_count(self) -> int:
        return sum(1 for candidate in self.candidates if candidate.status == "accepted")

    @property
    def rejected_count(self) -> int:
        return sum(1 for candidate in self.candidates if candidate.status == "rejected")

    @property
    def proposed_count(self) -> int:
        return sum(1 for candidate in self.candidates if candidate.status == "proposed")

    def accept_all(self) -> "DictionaryDraft":
        """Return a copy with every non-rejected candidate marked as accepted."""

        return self.model_copy(
            update={
                "candidates": [
                    candidate if candidate.status == "rejected" else candidate.accept()
                    for candidate in self.candidates
                ]
            }
        )

    def reject(self, canonical_value: str) -> "DictionaryDraft":
        """Return a copy with one canonical candidate rejected."""

        target = canonical_value.casefold()
        return self.model_copy(
            update={
                "candidates": [
                    candidate.reject()
                    if candidate.canonical_value.casefold() == target
                    else candidate
                    for candidate in self.candidates
                ]
            }
        )

    def to_dictionary(
        self,
        *,
        include_proposed: bool = False,
    ) -> Dictionary:
        """Convert reviewed candidates to a runtime dictionary.

        By default only accepted candidates are exported. Pass
        ``include_proposed=True`` only for preview or local experiments.
        """

        allowed_statuses = {"accepted"}
        if include_proposed:
            allowed_statuses.add("proposed")
        selected = [
            candidate
            for candidate in self.candidates
            if candidate.status in allowed_statuses and candidate.aliases
        ]
        if not selected:
            raise ValueError(
                "Dictionary draft has no accepted candidates to export. "
                "Review candidates or pass include_proposed=True for preview use."
            )
        terms = [
            DictionaryTerm(
                canonical_value=candidate.canonical_value,
                slot=candidate.slot,
                aliases=[DictionaryAlias(value=alias) for alias in candidate.aliases],
            )
            for candidate in selected
        ]
        return Dictionary(
            profile_name=self.profile_name,
            profile_description=self.profile_description,
            terms=terms,
        )

    def save(self, path: str | Path) -> None:
        """Write the draft artifact as JSON."""

        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            self.model_dump_json(indent=2, exclude_none=True) + "\n",
            encoding="utf-8",
        )

    def review_markdown(self) -> str:
        """Render a human-readable review report."""

        lines = [
            "# Dictionary draft review",
            "",
            f"- Profile: `{self.profile_name}`",
            f"- Candidates: **{self.candidate_count}**",
            f"- Proposed: **{self.proposed_count}**",
            f"- Accepted: **{self.accepted_count}**",
            f"- Rejected: **{self.rejected_count}**",
        ]
        if self.source_path:
            lines.append(f"- Source: `{self.source_path}`")
        if self.source_format:
            lines.append(f"- Source format: `{self.source_format}`")
        lines.append("")

        if self.findings:
            lines.extend(
                [
                    "## Findings",
                    "",
                    "| Severity | Source | Code | Line | Message |",
                    "|---|---|---|---|---|",
                ]
            )
            for finding in self.findings:
                line = finding.line if finding.line is not None else "—"
                lines.append(
                    f"| {finding.severity} | {finding.source} | `{finding.code}` | "
                    f"{line} | {_escape_markdown_cell(finding.message)} |"
                )
            lines.append("")

        lines.extend(
            [
                "## Candidates",
                "",
                "| Status | Canonical | Slot | Aliases | Confidence |",
                "|---|---|---|---|---|",
            ]
        )
        for candidate in self.candidates:
            aliases = ", ".join(f"`{alias}`" for alias in candidate.aliases) or "—"
            lines.append(
                f"| {candidate.status} | `{candidate.canonical_value}` | "
                f"`{candidate.slot}` | {aliases} | {candidate.confidence:.2f} |"
            )
        return "\n".join(lines)


def _normalize_status(value: str) -> Literal["proposed", "accepted", "rejected"]:
    normalized = value.strip().lower()
    if normalized not in _DRAFT_STATUSES:
        raise ValueError("draft status must be proposed, accepted, or rejected")
    return normalized  # type: ignore[return-value]


def _mean_alias_confidence(aliases: list[DictionaryAlias]) -> float:
    if not aliases:
        return 1.0
    return sum(alias.confidence for alias in aliases) / len(aliases)


def _coerce_finding(value: DraftFinding | Mapping[str, Any] | object) -> DraftFinding:
    if isinstance(value, DraftFinding):
        return value
    if isinstance(value, Mapping):
        return DraftFinding.model_validate(dict(value))

    severity = getattr(value, "severity", "info")
    if hasattr(severity, "value"):
        severity = severity.value
    line = getattr(value, "line", None)
    return DraftFinding(
        severity=str(severity),
        code=str(getattr(value, "code", "unknown")),
        message=str(getattr(value, "message", "Review finding.")),
        source=str(getattr(value, "source", "draft")),
        line=line if isinstance(line, int) else None,
    )


def _escape_markdown_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")
