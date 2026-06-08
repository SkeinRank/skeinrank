"""Human-readable and machine-readable import reports."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .models import ImportWarning, Severity


@dataclass
class ImportReport:
    """Summary of an existing dictionary import."""

    source_path: str
    detected_format: str
    canonical_count: int
    alias_count: int
    warnings: list[ImportWarning] = field(default_factory=list)

    @property
    def fatals(self) -> list[ImportWarning]:
        return [
            warning for warning in self.warnings if warning.severity is Severity.FATAL
        ]

    @property
    def is_ok(self) -> bool:
        return not self.fatals

    @property
    def warning_count(self) -> int:
        return sum(1 for warning in self.warnings if warning.severity is Severity.WARN)

    @property
    def info_count(self) -> int:
        return sum(1 for warning in self.warnings if warning.severity is Severity.INFO)

    @property
    def fatal_count(self) -> int:
        return len(self.fatals)

    def counts(self) -> dict[str, int]:
        return {
            "fatal": self.fatal_count,
            "warn": self.warning_count,
            "info": self.info_count,
        }

    def source_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for warning in self.warnings:
            counts[warning.source] = counts.get(warning.source, 0) + 1
        return dict(sorted(counts.items()))

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_path": self.source_path,
            "detected_format": self.detected_format,
            "canonical_count": self.canonical_count,
            "alias_count": self.alias_count,
            "counts": self.counts(),
            "source_counts": self.source_counts(),
            "ok": self.is_ok,
            "warnings": [warning.to_dict() for warning in self.sorted_warnings()],
        }

    def sorted_warnings(self) -> list[ImportWarning]:
        severity_rank = {Severity.FATAL: 0, Severity.WARN: 1, Severity.INFO: 2}
        return sorted(
            self.warnings,
            key=lambda warning: (
                severity_rank[warning.severity],
                warning.source,
                warning.code,
                warning.line or 0,
            ),
        )

    def to_markdown(self) -> str:
        counts = self.counts()
        lines = [
            "# Dictionary import report",
            "",
            f"- Source: `{self.source_path}`",
            f"- Format: `{self.detected_format}`",
            f"- Canonical terms: **{self.canonical_count}**",
            f"- Aliases: **{self.alias_count}**",
            (
                "- Findings: "
                f"{counts['fatal']} fatal, {counts['warn']} warn, "
                f"{counts['info']} info"
            ),
            "",
        ]

        if not self.warnings:
            lines.append("No issues found.")
            return "\n".join(lines)

        lines.append("| Severity | Source | Code | Line | Message |")
        lines.append("|---|---|---|---|---|")
        for warning in self.sorted_warnings():
            line = warning.line if warning.line is not None else "—"
            lines.append(
                "| "
                f"{warning.severity.value} | {warning.source} | `{warning.code}` | "
                f"{line} | {_escape_table_cell(warning.message)} |"
            )
        return "\n".join(lines)


def _escape_table_cell(value: str) -> str:
    return value.replace("|", "\\|")
