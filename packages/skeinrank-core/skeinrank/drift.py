"""Terminology drift report schema.

The drift schema is a local reporting contract for future drift scanners. It is
intentionally data-only: creating a report never mutates governance state,
snapshots, bindings, runtime dictionaries, or production search configuration.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

DRIFT_REPORT_SCHEMA_VERSION = "skeinrank.terminology_drift_report.v1"


class DriftSeverity(str, Enum):
    """Severity assigned to a terminology drift finding."""

    INFO = "info"
    WARN = "warn"
    CRITICAL = "critical"


class DriftFindingType(str, Enum):
    """Supported terminology drift finding classes."""

    ALIAS_DRIFT = "alias_drift"
    STALE_TERM = "stale_term"
    BINDING_LAG = "binding_lag"
    AMBIGUITY_SIGNAL = "ambiguity_signal"


class DriftEvidence(BaseModel):
    """Evidence snippet supporting a drift finding."""

    source: str
    text: str
    line: int | None = Field(default=None, ge=1)
    score: float | None = Field(default=None, ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("source", "text")
    @classmethod
    def _non_empty_text(cls, value: str) -> str:
        cleaned = " ".join(str(value).strip().split())
        if not cleaned:
            raise ValueError("drift evidence source/text must not be empty")
        return cleaned


class DriftFinding(BaseModel):
    """One reviewable terminology drift finding.

    Findings are review signals, not production mutations. A future scanner may
    emit them for new unmatched aliases, stale terms, binding lag, or ambiguity
    signals. Reviewers decide whether findings become dictionary proposals.
    """

    finding_type: DriftFindingType
    severity: DriftSeverity = DriftSeverity.WARN
    title: str
    description: str | None = None
    value: str | None = None
    normalized_value: str | None = None
    canonical_value: str | None = None
    profile_name: str | None = None
    binding_id: str | None = None
    pinned_snapshot_version: str | None = None
    latest_snapshot_version: str | None = None
    metrics: dict[str, int | float | str | bool] = Field(default_factory=dict)
    evidence: list[DriftEvidence] = Field(default_factory=list)
    recommended_action: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "title",
        "description",
        "value",
        "normalized_value",
        "canonical_value",
        "profile_name",
        "binding_id",
        "pinned_snapshot_version",
        "latest_snapshot_version",
        "recommended_action",
        mode="before",
    )
    @classmethod
    def _clean_optional_text(cls, value: Any) -> Any:
        if value is None:
            return None
        cleaned = " ".join(str(value).strip().split())
        if not cleaned:
            return None
        return cleaned

    @model_validator(mode="after")
    def _derive_normalized_value(self) -> "DriftFinding":
        if self.value and not self.normalized_value:
            self.normalized_value = _normalize_value(self.value)
        return self


class DriftReportSummary(BaseModel):
    """Computed summary for a terminology drift report."""

    finding_count: int = Field(ge=0)
    critical_count: int = Field(ge=0)
    warn_count: int = Field(ge=0)
    info_count: int = Field(ge=0)
    alias_drift_count: int = Field(ge=0)
    stale_term_count: int = Field(ge=0)
    binding_lag_count: int = Field(ge=0)
    ambiguity_signal_count: int = Field(ge=0)
    unknown_alias_rate: float | None = Field(default=None, ge=0.0)


class TerminologyDriftReport(BaseModel):
    """Reviewable report describing terminology drift signals.

    This model is a schema contract for scanners and UIs. It does not perform a
    scan by itself and does not write proposals, snapshots, bindings, or runtime
    dictionaries.
    """

    model_config = ConfigDict(use_enum_values=True)

    schema_version: str = DRIFT_REPORT_SCHEMA_VERSION
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    profile_name: str | None = None
    binding_id: str | None = None
    dictionary_schema_version: str | None = None
    pinned_snapshot_version: str | None = None
    latest_snapshot_version: str | None = None
    document_count: int = Field(default=0, ge=0)
    source_count: int = Field(default=0, ge=0)
    metrics: dict[str, int | float | str | bool] = Field(default_factory=dict)
    findings: list[DriftFinding] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    @field_validator(
        "profile_name",
        "binding_id",
        "dictionary_schema_version",
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

    @field_validator("notes")
    @classmethod
    def _normalize_notes(cls, values: list[str]) -> list[str]:
        out: list[str] = []
        for value in values:
            cleaned = " ".join(str(value).strip().split())
            if cleaned:
                out.append(cleaned)
        return out

    @model_validator(mode="after")
    def _inherit_context(self) -> "TerminologyDriftReport":
        for finding in self.findings:
            if self.profile_name and not finding.profile_name:
                finding.profile_name = self.profile_name
            if self.binding_id and not finding.binding_id:
                finding.binding_id = self.binding_id
            if self.pinned_snapshot_version and not finding.pinned_snapshot_version:
                finding.pinned_snapshot_version = self.pinned_snapshot_version
            if self.latest_snapshot_version and not finding.latest_snapshot_version:
                finding.latest_snapshot_version = self.latest_snapshot_version
        return self

    @classmethod
    def from_file(cls, path: str | Path) -> "TerminologyDriftReport":
        """Load a drift report JSON document."""

        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Terminology drift report root must be an object")
        return cls.model_validate(payload)

    def save(self, path: str | Path, *, indent: int = 2) -> None:
        """Write the report as JSON."""

        Path(path).write_text(self.to_json(indent=indent), encoding="utf-8")

    def to_json(self, *, indent: int | None = 2) -> str:
        """Serialize the report to JSON."""

        return self.model_dump_json(indent=indent)

    def summary(self) -> DriftReportSummary:
        """Return computed summary counts for findings and key metrics."""

        severities = Counter(_enum_value(finding.severity) for finding in self.findings)
        finding_types = Counter(
            _enum_value(finding.finding_type) for finding in self.findings
        )
        unknown_alias_rate = self.metrics.get("unknown_alias_rate")
        if isinstance(unknown_alias_rate, bool) or not isinstance(
            unknown_alias_rate, (int, float)
        ):
            unknown_alias_rate = None
        return DriftReportSummary(
            finding_count=len(self.findings),
            critical_count=severities[DriftSeverity.CRITICAL.value],
            warn_count=severities[DriftSeverity.WARN.value],
            info_count=severities[DriftSeverity.INFO.value],
            alias_drift_count=finding_types[DriftFindingType.ALIAS_DRIFT.value],
            stale_term_count=finding_types[DriftFindingType.STALE_TERM.value],
            binding_lag_count=finding_types[DriftFindingType.BINDING_LAG.value],
            ambiguity_signal_count=finding_types[
                DriftFindingType.AMBIGUITY_SIGNAL.value
            ],
            unknown_alias_rate=float(unknown_alias_rate)
            if unknown_alias_rate is not None
            else None,
        )

    def findings_by_type(
        self, finding_type: DriftFindingType | str
    ) -> list[DriftFinding]:
        """Return findings matching a drift finding type."""

        value = _enum_value(finding_type)
        return [
            finding
            for finding in self.findings
            if _enum_value(finding.finding_type) == value
        ]

    def findings_by_severity(self, severity: DriftSeverity | str) -> list[DriftFinding]:
        """Return findings matching a severity."""

        value = _enum_value(severity)
        return [
            finding
            for finding in self.findings
            if _enum_value(finding.severity) == value
        ]

    def to_markdown(self) -> str:
        """Render a concise human-readable review report."""

        summary = self.summary()
        title_scope = self.binding_id or self.profile_name or "local dictionary"
        lines = [
            "# Terminology drift report",
            "",
            f"- Scope: `{title_scope}`",
            f"- Findings: **{summary.finding_count}**",
            f"- Critical: **{summary.critical_count}**",
            f"- Warnings: **{summary.warn_count}**",
        ]
        if summary.unknown_alias_rate is not None:
            lines.append(f"- Unknown alias rate: **{summary.unknown_alias_rate:.2%}**")
        if self.pinned_snapshot_version or self.latest_snapshot_version:
            lines.append(
                "- Snapshots: "
                f"`{self.pinned_snapshot_version or 'unknown'}` → "
                f"`{self.latest_snapshot_version or 'unknown'}`"
            )
        if self.notes:
            lines.extend(["", "## Notes", ""])
            lines.extend(f"- {note}" for note in self.notes)
        lines.extend(["", "| Severity | Type | Value | Title |", "|---|---|---|---|"])
        if not self.findings:
            lines.append("| info | none | — | No drift findings recorded. |")
            return "\n".join(lines)
        for finding in self.findings:
            value = finding.value or finding.canonical_value or "—"
            lines.append(
                "| "
                f"{_enum_value(finding.severity)} | "
                f"{_enum_value(finding.finding_type)} | "
                f"`{value}` | "
                f"{finding.title} |"
            )
        return "\n".join(lines)


def _normalize_value(value: str) -> str:
    return " ".join(value.strip().casefold().split())


def _enum_value(value: Any) -> str:
    if isinstance(value, Enum):
        return str(value.value)
    return str(value)
