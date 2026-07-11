"""Convert terminology drift reports into reviewable dictionary drafts.

This module keeps drift handling proposal-first. It turns local drift report
findings into a :class:`DictionaryDraft` artifact that reviewers can inspect,
edit, accept, reject, or import into the governance workflow later. It never
creates governance proposals directly and never mutates snapshots, bindings,
runtime dictionaries, or production search configuration.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, field_validator

from .drafts import DictionaryDraft, DraftCandidate, DraftFinding, EvidenceSnippet
from .drift import (
    DriftEvidence,
    DriftFinding,
    DriftFindingType,
    DriftSeverity,
    TerminologyDriftReport,
)


class DriftDraftConfig(BaseModel):
    """Configuration for converting a drift report to a dictionary draft."""

    profile_name: str | None = None
    profile_description: str | None = (
        "Reviewable dictionary draft created from a terminology drift report."
    )
    default_slot: str = "TERM"
    source_label: str = "drift_report"
    include_alias_drift: bool = True
    include_report_findings: bool = True

    @field_validator(
        "profile_name",
        "profile_description",
        "default_slot",
        "source_label",
        mode="before",
    )
    @classmethod
    def _clean_optional_text(cls, value: Any) -> Any:
        if value is None:
            return None
        cleaned = " ".join(str(value).strip().split())
        return cleaned or None


class DriftDraftConversionSummary(BaseModel):
    """Structured explanation of how drift findings became draft candidates."""

    status: Literal[
        "completed",
        "no_convertible_findings",
        "alias_conversion_disabled",
    ]
    source_finding_count: int
    alias_drift_finding_count: int
    candidate_source_finding_count: int
    candidate_count: int
    preserved_finding_count: int
    skipped_finding_count: int
    skipped_findings_by_type: dict[str, int]
    message: str

    def to_markdown(self) -> str:
        """Render the conversion summary for a review report."""

        skipped = (
            ", ".join(
                f"`{finding_type}`={count}"
                for finding_type, count in sorted(self.skipped_findings_by_type.items())
            )
            or "none"
        )
        return "\n".join(
            [
                "## Conversion summary",
                "",
                f"- Status: `{self.status}`",
                f"- Source findings: **{self.source_finding_count}**",
                f"- Alias-drift findings: **{self.alias_drift_finding_count}**",
                f"- Candidate source findings: **{self.candidate_source_finding_count}**",
                f"- Draft candidates: **{self.candidate_count}**",
                f"- Preserved review findings: **{self.preserved_finding_count}**",
                f"- Findings not converted to candidates: {skipped}",
                "",
                self.message,
            ]
        )


class DriftDraftResult(BaseModel):
    """Dictionary draft, source report, and a conversion summary."""

    draft: DictionaryDraft
    report: TerminologyDriftReport
    summary: DriftDraftConversionSummary

    def save(self, path: str | Path) -> None:
        """Write the draft artifact as JSON."""

        self.draft.save(path)

    def save_summary(self, path: str | Path) -> None:
        """Write the structured conversion summary as JSON."""

        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            self.summary.model_dump_json(indent=2) + "\n",
            encoding="utf-8",
        )

    def review_markdown(self) -> str:
        """Render the draft review with an explicit conversion summary."""

        draft_markdown = self.draft.review_markdown()
        marker = "\n## Findings"
        if marker not in draft_markdown:
            marker = "\n## Candidates"
        before, after = draft_markdown.split(marker, 1)
        return "\n\n".join(
            [
                before.rstrip(),
                self.summary.to_markdown(),
                f"{marker.lstrip()}" + after,
            ]
        )


def drift_report_to_dictionary_draft(
    report: str | Path | Mapping[str, Any] | TerminologyDriftReport,
    *,
    config: DriftDraftConfig | Mapping[str, Any] | None = None,
) -> DriftDraftResult:
    """Convert a terminology drift report into a reviewable dictionary draft.

    Only ``alias_drift`` findings become draft candidates. Other drift findings
    are preserved as draft-level review findings so reviewers still see stale
    terms, binding lag, and ambiguity signals. The conversion writes no runtime
    dictionary and performs no governance mutation.
    """

    loaded_report = _coerce_report(report)
    normalized_config = _coerce_config(config)
    profile_name = (
        normalized_config.profile_name
        or loaded_report.profile_name
        or "drift_candidates"
    )
    alias_drift_findings = loaded_report.findings_by_type(DriftFindingType.ALIAS_DRIFT)
    candidate_source_findings = (
        alias_drift_findings if normalized_config.include_alias_drift else []
    )
    candidates = [
        _candidate_from_alias_drift_finding(
            finding,
            config=normalized_config,
        )
        for finding in candidate_source_findings
    ]
    summary = _build_conversion_summary(
        report=loaded_report,
        candidate_count=len(candidates),
        include_alias_drift=normalized_config.include_alias_drift,
        include_report_findings=normalized_config.include_report_findings,
    )
    findings: list[DraftFinding] = []
    if normalized_config.include_report_findings:
        findings = [
            _draft_finding_from_drift_finding(finding)
            for finding in loaded_report.findings
        ]
    findings.insert(
        0,
        DraftFinding(
            severity="info",
            code="drift.draft_generated",
            message=(
                "Created a reviewable dictionary draft from a terminology drift report. "
                "No governance, snapshot, binding, or runtime state was changed."
            ),
            source=normalized_config.source_label,
        ),
    )
    findings.insert(
        1,
        DraftFinding(
            severity="info",
            code="drift.conversion_summary",
            message=summary.message,
            source=normalized_config.source_label,
        ),
    )
    if not candidates:
        findings.append(
            DraftFinding(
                severity="info",
                code="drift.no_alias_candidates",
                message=summary.message,
                source=normalized_config.source_label,
            )
        )
    draft = DictionaryDraft(
        profile_name=profile_name,
        profile_description=normalized_config.profile_description,
        source_path=_source_path_for_report(report),
        source_format="terminology_drift_report",
        candidates=candidates,
        findings=findings,
    )
    return DriftDraftResult(
        draft=draft,
        report=loaded_report,
        summary=summary,
    )


def _build_conversion_summary(
    *,
    report: TerminologyDriftReport,
    candidate_count: int,
    include_alias_drift: bool,
    include_report_findings: bool,
) -> DriftDraftConversionSummary:
    finding_counts: dict[str, int] = {}
    for finding in report.findings:
        finding_type = _finding_type_value(finding.finding_type)
        finding_counts[finding_type] = finding_counts.get(finding_type, 0) + 1

    alias_count = finding_counts.get(DriftFindingType.ALIAS_DRIFT.value, 0)
    candidate_source_count = alias_count if include_alias_drift else 0
    skipped_counts = dict(finding_counts)
    if include_alias_drift:
        skipped_counts.pop(DriftFindingType.ALIAS_DRIFT.value, None)
    skipped_count = sum(skipped_counts.values())

    if not include_alias_drift and alias_count:
        status: Literal[
            "completed",
            "no_convertible_findings",
            "alias_conversion_disabled",
        ] = "alias_conversion_disabled"
        message = (
            "No dictionary candidates were created because alias-drift conversion "
            f"is disabled. The report contains {alias_count} alias_drift finding(s)."
        )
    elif alias_count == 0:
        status = "no_convertible_findings"
        non_alias_count = len(report.findings)
        detail = _format_finding_counts(skipped_counts)
        message = (
            "No dictionary candidates were created because the report contains no "
            f"alias_drift findings. {non_alias_count} non-convertible finding(s) "
            f"remain available for review{detail}."
        )
    else:
        status = "completed"
        detail = _format_finding_counts(skipped_counts)
        message = (
            f"Created {candidate_count} dictionary candidate(s) from {alias_count} "
            f"alias_drift finding(s). {skipped_count} other finding(s) were not "
            f"converted to candidates{detail}."
        )

    return DriftDraftConversionSummary(
        status=status,
        source_finding_count=len(report.findings),
        alias_drift_finding_count=alias_count,
        candidate_source_finding_count=candidate_source_count,
        candidate_count=candidate_count,
        preserved_finding_count=(
            len(report.findings) if include_report_findings else 0
        ),
        skipped_finding_count=skipped_count,
        skipped_findings_by_type=skipped_counts,
        message=message,
    )


def _format_finding_counts(counts: Mapping[str, int]) -> str:
    if not counts:
        return ""
    rendered = ", ".join(
        f"{finding_type}={count}" for finding_type, count in sorted(counts.items())
    )
    return f" ({rendered})"


def _coerce_report(
    report: str | Path | Mapping[str, Any] | TerminologyDriftReport,
) -> TerminologyDriftReport:
    if isinstance(report, TerminologyDriftReport):
        return report
    if isinstance(report, (str, Path)):
        return TerminologyDriftReport.from_file(report)
    return TerminologyDriftReport.model_validate(dict(report))


def _coerce_config(
    config: DriftDraftConfig | Mapping[str, Any] | None,
) -> DriftDraftConfig:
    if config is None:
        return DriftDraftConfig()
    if isinstance(config, DriftDraftConfig):
        return config
    return DriftDraftConfig.model_validate(dict(config))


def _source_path_for_report(
    report: str | Path | Mapping[str, Any] | TerminologyDriftReport,
) -> str | None:
    if isinstance(report, (str, Path)):
        return str(report)
    return None


def _candidate_from_alias_drift_finding(
    finding: DriftFinding,
    *,
    config: DriftDraftConfig,
) -> DraftCandidate:
    value = finding.value or finding.normalized_value or finding.title
    canonical_value = _canonical_value_for_finding(finding, fallback=value)
    aliases = _aliases_for_finding(finding, canonical_value=canonical_value)
    confidence = _confidence_for_finding(finding)
    return DraftCandidate(
        canonical_value=canonical_value,
        aliases=aliases,
        slot=str(finding.details.get("slot") or config.default_slot),
        confidence=confidence,
        status="proposed",
        source=config.source_label,
        evidence=[_evidence_snippet(item) for item in finding.evidence],
        findings=[
            DraftFinding(
                severity=_draft_severity(finding.severity),
                code="drift.alias_drift",
                message=finding.title,
                source=config.source_label,
            )
        ],
    )


def _canonical_value_for_finding(finding: DriftFinding, *, fallback: str) -> str:
    if finding.canonical_value:
        return finding.canonical_value
    split_surface = _split_camel_or_acronym_surface(str(finding.value or ""))
    if split_surface:
        return split_surface
    normalized = finding.normalized_value or _normalize_candidate_value(fallback)
    return normalized or fallback


def _aliases_for_finding(finding: DriftFinding, *, canonical_value: str) -> list[str]:
    aliases: list[str] = []
    for value in (finding.value, finding.normalized_value):
        if not value:
            continue
        cleaned = " ".join(str(value).strip().split())
        if not cleaned or cleaned.casefold() == canonical_value.casefold():
            continue
        if cleaned.casefold() in {alias.casefold() for alias in aliases}:
            continue
        aliases.append(cleaned)
    return aliases


def _draft_finding_from_drift_finding(finding: DriftFinding) -> DraftFinding:
    return DraftFinding(
        severity=_draft_severity(finding.severity),
        code=f"drift.{_finding_type_value(finding.finding_type)}",
        message=finding.title,
        source="drift_report",
    )


def _evidence_snippet(item: DriftEvidence) -> EvidenceSnippet:
    return EvidenceSnippet(
        source=item.source,
        line=item.line,
        text=item.text,
        score=item.score,
    )


def _confidence_for_finding(finding: DriftFinding) -> float:
    raw = finding.metrics.get("confidence") or finding.metrics.get("candidate_score")
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return 0.75
    return round(max(0.0, min(1.0, float(raw))), 3)


def _draft_severity(value: DriftSeverity | str) -> str:
    severity = value.value if isinstance(value, DriftSeverity) else str(value)
    if severity == DriftSeverity.CRITICAL.value:
        return "warn"
    if severity == DriftSeverity.WARN.value:
        return "warn"
    return "info"


def _finding_type_value(value: DriftFindingType | str) -> str:
    return value.value if isinstance(value, DriftFindingType) else str(value)


def _normalize_candidate_value(value: str) -> str:
    return " ".join(str(value).strip().casefold().split())


def _split_camel_or_acronym_surface(value: str) -> str | None:
    surface = " ".join(value.strip().split())
    if not surface or surface.casefold() == surface:
        return None
    spaced = surface.replace("_", " ").replace("-", " ")
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", spaced)
    spaced = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", " ", spaced)
    normalized = " ".join(part for part in spaced.casefold().split() if part)
    if normalized and normalized != surface.casefold():
        return normalized
    return None
