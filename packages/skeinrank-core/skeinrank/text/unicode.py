"""Unicode normalization helpers for deterministic terminology matching.

The runtime matcher keeps the original input untouched while scanning normalized
views that handle common compatibility forms, invisible separators, and bidi
controls. Match offsets are mapped back to the original text so callers can use
them for highlighting and safe replacement.
"""

from __future__ import annotations

import unicodedata
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class UnicodeFindingKind(str, Enum):
    """Kinds of Unicode normalization findings reported by the runtime matcher."""

    BIDI_CONTROL = "bidi_control"
    COMPATIBILITY = "compatibility"
    NON_ASCII_SPACE = "non_ascii_space"
    ZERO_WIDTH = "zero_width"


_BIDI_CONTROLS = frozenset(
    {
        "\u061c",  # Arabic letter mark
        "\u200e",  # left-to-right mark
        "\u200f",  # right-to-left mark
        "\u202a",  # left-to-right embedding
        "\u202b",  # right-to-left embedding
        "\u202c",  # pop directional formatting
        "\u202d",  # left-to-right override
        "\u202e",  # right-to-left override
        "\u2066",  # left-to-right isolate
        "\u2067",  # right-to-left isolate
        "\u2068",  # first strong isolate
        "\u2069",  # pop directional isolate
    }
)

_ZERO_WIDTH_SEPARATORS = frozenset(
    {
        "\u200b",  # zero width space
        "\u200c",  # zero width non-joiner
        "\u200d",  # zero width joiner
        "\u2060",  # word joiner
        "\ufeff",  # zero width no-break space / BOM
    }
)

_DASH_EQUIVALENTS = frozenset(
    {
        "\u2011",  # non-breaking hyphen
        "\u2013",  # en dash
        "\u2014",  # em dash
        "\u2212",  # minus sign
    }
)


class UnicodeTextFinding(BaseModel):
    """One notable Unicode transformation found in runtime text."""

    model_config = ConfigDict(frozen=True)

    kind: UnicodeFindingKind
    start: int = Field(ge=0)
    end: int = Field(ge=0)
    text: str
    replacement: str
    name: str
    risk: Literal["low", "high"]


class UnicodeNormalizationResult(BaseModel):
    """Normalized matching views plus offset maps back to the original input."""

    model_config = ConfigDict(frozen=True)

    original_text: str
    normalized_text: str
    index_map: tuple[int, ...]
    compact_text: str
    compact_index_map: tuple[int, ...]
    findings: tuple[UnicodeTextFinding, ...] = ()

    @property
    def changed(self) -> bool:
        """Return whether the primary normalized view differs from the input."""

        return self.normalized_text != self.original_text

    @property
    def has_bidi_control(self) -> bool:
        """Return whether bidi-control characters were removed before matching."""

        return any(
            finding.kind == UnicodeFindingKind.BIDI_CONTROL for finding in self.findings
        )

    @property
    def has_findings(self) -> bool:
        """Return whether any notable Unicode normalization was recorded."""

        return bool(self.findings)

    def original_span(
        self,
        start: int,
        end: int,
        *,
        compact: bool = False,
    ) -> tuple[int, int]:
        """Map a normalized span back to the original input coordinates."""

        if start < 0 or end < start:
            raise ValueError("invalid normalized span")
        index_map = self.compact_index_map if compact else self.index_map
        if start == end:
            if start == 0:
                return (0, 0)
            if start > len(index_map):
                raise ValueError("normalized span is outside the input text")
            original_index = index_map[start - 1] + 1 if index_map else 0
            return (original_index, original_index)
        if start >= len(index_map) or end > len(index_map):
            raise ValueError("normalized span is outside the input text")
        return (index_map[start], index_map[end - 1] + 1)


def normalize_text_for_matching(text: str) -> UnicodeNormalizationResult:
    """Normalize text for deterministic runtime matching.

    The primary view turns Unicode spaces and zero-width separators into plain
    spaces. A compact alternate view removes zero-width separators so an
    obfuscated compact alias such as ``k\u200b8s`` can still match ``k8s``. Both
    views use NFKC compatibility normalization, normalize common dash variants,
    and remove bidi-control characters while preserving original offsets.
    """

    if not isinstance(text, str):
        raise TypeError("text must be a string")

    primary_chars: list[str] = []
    primary_map: list[int] = []
    compact_chars: list[str] = []
    compact_map: list[int] = []
    findings: list[UnicodeTextFinding] = []

    for index, char in enumerate(text):
        if char in _BIDI_CONTROLS:
            findings.append(_finding(UnicodeFindingKind.BIDI_CONTROL, index, char, ""))
            continue

        if char in _ZERO_WIDTH_SEPARATORS:
            findings.append(_finding(UnicodeFindingKind.ZERO_WIDTH, index, char, " "))
            primary_chars.append(" ")
            primary_map.append(index)
            continue

        if char.isspace() and char != " ":
            findings.append(
                _finding(UnicodeFindingKind.NON_ASCII_SPACE, index, char, " ")
            )
            primary_chars.append(" ")
            primary_map.append(index)
            compact_chars.append(" ")
            compact_map.append(index)
            continue

        normalized = unicodedata.normalize("NFKC", char)
        normalized = "".join(
            "-" if normalized_char in _DASH_EQUIVALENTS else normalized_char
            for normalized_char in normalized
        )
        if normalized != char:
            findings.append(
                _finding(UnicodeFindingKind.COMPATIBILITY, index, char, normalized)
            )
        for normalized_char in normalized:
            primary_chars.append(normalized_char)
            primary_map.append(index)
            compact_chars.append(normalized_char)
            compact_map.append(index)

    normalized_text, index_map = _collapse_spaces(primary_chars, primary_map)
    compact_text, compact_index_map = _collapse_spaces(compact_chars, compact_map)

    return UnicodeNormalizationResult(
        original_text=text,
        normalized_text=normalized_text,
        index_map=index_map,
        compact_text=compact_text,
        compact_index_map=compact_index_map,
        findings=tuple(findings),
    )


def _collapse_spaces(
    chars: list[str],
    index_map: list[int],
) -> tuple[str, tuple[int, ...]]:
    collapsed_chars: list[str] = []
    collapsed_map: list[int] = []
    previous_was_space = False
    for char, source_index in zip(chars, index_map):
        if char.isspace():
            if previous_was_space:
                continue
            collapsed_chars.append(" ")
            collapsed_map.append(source_index)
            previous_was_space = True
            continue
        collapsed_chars.append(char)
        collapsed_map.append(source_index)
        previous_was_space = False
    return "".join(collapsed_chars), tuple(collapsed_map)


def _finding(
    kind: UnicodeFindingKind,
    index: int,
    text: str,
    replacement: str,
) -> UnicodeTextFinding:
    return UnicodeTextFinding(
        kind=kind,
        start=index,
        end=index + 1,
        text=text,
        replacement=replacement,
        name=unicodedata.name(text, "UNKNOWN") if text else "UNKNOWN",
        risk="high" if kind == UnicodeFindingKind.BIDI_CONTROL else "low",
    )


__all__ = [
    "UnicodeFindingKind",
    "UnicodeNormalizationResult",
    "UnicodeTextFinding",
    "normalize_text_for_matching",
]
