"""Models used by dictionary import helpers.

The import path is intentionally candidate-oriented: it converts existing
synonym lists into a local SkeinRank dictionary file plus a reviewable report.
It does not connect to the governance API or mutate runtime state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Severity(str, Enum):
    """Import finding severity."""

    FATAL = "fatal"
    WARN = "warn"
    INFO = "info"


@dataclass(frozen=True)
class RawMapping:
    """One raw alias-to-canonical fact extracted from an input file."""

    canonical: str
    alias: str
    slot: str | None = None
    source_line: int | None = None
    raw: str | None = None


@dataclass(frozen=True)
class ImportWarning:
    """Parse/build finding attached to a dictionary import."""

    severity: Severity
    code: str
    message: str
    line: int | None = None
    source: str = "import"

    @classmethod
    def fatal(
        cls,
        *,
        code: str,
        message: str,
        line: int | None = None,
        source: str = "import",
    ) -> "ImportWarning":
        return cls(Severity.FATAL, code, message, line, source)

    @classmethod
    def warn(
        cls,
        *,
        code: str,
        message: str,
        line: int | None = None,
        source: str = "import",
    ) -> "ImportWarning":
        return cls(Severity.WARN, code, message, line, source)

    @classmethod
    def info(
        cls,
        *,
        code: str,
        message: str,
        line: int | None = None,
        source: str = "import",
    ) -> "ImportWarning":
        return cls(Severity.INFO, code, message, line, source)

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity.value,
            "code": self.code,
            "message": self.message,
            "line": self.line,
            "source": self.source,
        }


@dataclass
class ParseResult:
    """Parser output before dictionary construction."""

    mappings: list[RawMapping] = field(default_factory=list)
    warnings: list[ImportWarning] = field(default_factory=list)
