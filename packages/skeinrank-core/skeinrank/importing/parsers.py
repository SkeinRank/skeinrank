"""Parsers for existing dictionary and synonym-list formats."""

from __future__ import annotations

import csv
import json
from collections.abc import Mapping
from io import StringIO

from .models import ImportWarning, ParseResult, RawMapping

SUPPORTED_FORMATS = frozenset({"json", "csv", "es-synonyms"})
_CANONICAL_COLUMNS = ("canonical", "canonical_value", "term", "canonical term")
_ALIAS_COLUMNS = ("alias", "aliases", "synonym", "synonyms")
_SLOT_COLUMNS = ("slot", "type", "category")


def detect_format(
    path: str,
    content: str,
    *,
    override: str | None = None,
) -> str:
    """Detect an import format from a path/content pair."""

    if override:
        normalized = override.strip().lower()
        if normalized not in SUPPORTED_FORMATS:
            raise ValueError(
                "Unsupported dictionary import format. "
                f"Use one of: {', '.join(sorted(SUPPORTED_FORMATS))}"
            )
        return normalized

    lower = path.lower()
    stripped = content.lstrip()
    if lower.endswith(".json") or stripped.startswith("{"):
        return "json"
    if lower.endswith(".csv"):
        return "csv"
    if lower.endswith((".txt", ".synonyms")) or "=>" in content[:2000]:
        return "es-synonyms"
    raise ValueError(
        "Cannot detect dictionary import format. "
        "Pass --format json, --format csv, or --format es-synonyms."
    )


class JsonDictionaryParser:
    """Parse a simple JSON dictionary or a SkeinRank dictionary payload."""

    format_name = "json"

    def parse(self, raw_text: str) -> ParseResult:
        warnings: list[ImportWarning] = []
        try:
            loaded = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            return ParseResult(
                warnings=[
                    ImportWarning.fatal(
                        code="json.invalid",
                        message=f"Invalid JSON: {exc}",
                        source="parse",
                    )
                ]
            )

        if not isinstance(loaded, Mapping):
            return ParseResult(
                warnings=[
                    ImportWarning.fatal(
                        code="json.root_not_object",
                        message="JSON import root must be an object.",
                        source="parse",
                    )
                ]
            )

        if isinstance(loaded.get("terms"), list):
            return _parse_terms_payload(loaded)

        mappings: list[RawMapping] = []
        for canonical, value in loaded.items():
            if str(canonical).strip() in {"schema_version", "profile_name"}:
                warnings.append(
                    ImportWarning.info(
                        code="json.metadata_skipped",
                        message=f"Skipped metadata key '{canonical}'.",
                        source="parse",
                    )
                )
                continue

            aliases, slot = _aliases_and_slot_from_json_value(value)
            if not aliases:
                warnings.append(
                    ImportWarning.warn(
                        code="json.no_aliases",
                        message=f"Canonical '{canonical}' has no aliases; skipped.",
                        source="parse",
                    )
                )
                continue

            for alias in aliases:
                mappings.append(
                    RawMapping(
                        canonical=str(canonical),
                        alias=alias,
                        slot=slot,
                        raw=f"{canonical}: {alias}",
                    )
                )

        return ParseResult(mappings=mappings, warnings=warnings)


class CsvDictionaryParser:
    """Parse a CSV file with canonical/alias columns and optional slot."""

    format_name = "csv"

    def parse(self, raw_text: str) -> ParseResult:
        warnings: list[ImportWarning] = []
        reader = csv.DictReader(StringIO(raw_text))
        if not reader.fieldnames:
            return ParseResult(
                warnings=[
                    ImportWarning.fatal(
                        code="csv.missing_header",
                        message="CSV import requires a header row.",
                        source="parse",
                    )
                ]
            )

        columns = {_normalize_header(name): name for name in reader.fieldnames}
        canonical_column = _first_existing(columns, _CANONICAL_COLUMNS)
        alias_column = _first_existing(columns, _ALIAS_COLUMNS)
        slot_column = _first_existing(columns, _SLOT_COLUMNS)

        missing = []
        if canonical_column is None:
            missing.append("canonical")
        if alias_column is None:
            missing.append("alias")
        if missing:
            return ParseResult(
                warnings=[
                    ImportWarning.fatal(
                        code="csv.missing_columns",
                        message=(
                            "CSV import requires canonical and alias columns. "
                            f"Missing: {', '.join(missing)}."
                        ),
                        source="parse",
                    )
                ]
            )

        mappings: list[RawMapping] = []
        for row_number, row in enumerate(reader, start=2):
            canonical = _clean(row.get(canonical_column))
            alias_cell = _clean(row.get(alias_column))
            slot = _clean(row.get(slot_column)) if slot_column else None

            if not canonical or not alias_cell:
                warnings.append(
                    ImportWarning.warn(
                        code="csv.incomplete_row",
                        message="Skipped row with empty canonical or alias value.",
                        line=row_number,
                        source="parse",
                    )
                )
                continue

            for alias in _split_alias_cell(alias_cell):
                mappings.append(
                    RawMapping(
                        canonical=canonical,
                        alias=alias,
                        slot=slot,
                        source_line=row_number,
                        raw=",".join(str(value or "") for value in row.values()),
                    )
                )

        return ParseResult(mappings=mappings, warnings=warnings)


class EsSynonymsParser:
    """Parse Elasticsearch/OpenSearch synonym-list lines."""

    format_name = "es-synonyms"

    def parse(self, raw_text: str) -> ParseResult:
        warnings: list[ImportWarning] = []
        mappings: list[RawMapping] = []

        for line_number, raw_line in enumerate(raw_text.splitlines(), start=1):
            line = _strip_es_comment(raw_line).strip()
            if not line:
                continue

            if "=>" in line:
                left, right = line.split("=>", 1)
                aliases = _split_es_terms(left)
                canonicals = _split_es_terms(right)
                if not aliases or not canonicals:
                    warnings.append(
                        ImportWarning.warn(
                            code="es.empty_mapping",
                            message="Skipped synonym rule with empty side.",
                            line=line_number,
                            source="parse",
                        )
                    )
                    continue
                canonical = canonicals[0]
                if len(canonicals) > 1:
                    warnings.append(
                        ImportWarning.warn(
                            code="es.multiple_canonicals",
                            message=(
                                "Explicit synonym rule has multiple right-hand "
                                f"terms; using '{canonical}' as canonical."
                            ),
                            line=line_number,
                            source="parse",
                        )
                    )
                for alias in aliases:
                    mappings.append(
                        RawMapping(
                            canonical=canonical,
                            alias=alias,
                            source_line=line_number,
                            raw=raw_line,
                        )
                    )
                continue

            terms = _split_es_terms(line)
            if len(terms) < 2:
                warnings.append(
                    ImportWarning.info(
                        code="es.single_term_skipped",
                        message="Skipped synonym line with fewer than two terms.",
                        line=line_number,
                        source="parse",
                    )
                )
                continue
            canonical = terms[0]
            warnings.append(
                ImportWarning.info(
                    code="es.canonical_guessed",
                    message=(
                        "Equivalent synonym set has no canonical side; "
                        f"using '{canonical}' as canonical. Review recommended."
                    ),
                    line=line_number,
                    source="parse",
                )
            )
            for alias in terms[1:]:
                mappings.append(
                    RawMapping(
                        canonical=canonical,
                        alias=alias,
                        source_line=line_number,
                        raw=raw_line,
                    )
                )

        return ParseResult(mappings=mappings, warnings=warnings)


def _parse_terms_payload(payload: Mapping[str, object]) -> ParseResult:
    warnings: list[ImportWarning] = []
    mappings: list[RawMapping] = []
    terms = payload.get("terms")
    if not isinstance(terms, list):
        return ParseResult(
            warnings=[
                ImportWarning.fatal(
                    code="json.terms_not_list",
                    message="JSON 'terms' value must be a list.",
                    source="parse",
                )
            ]
        )

    for index, term in enumerate(terms, start=1):
        if not isinstance(term, Mapping):
            warnings.append(
                ImportWarning.warn(
                    code="json.term_not_object",
                    message=f"Skipped term #{index}; expected an object.",
                    source="parse",
                )
            )
            continue
        canonical = _clean(
            term.get("canonical_value") or term.get("canonical") or term.get("term")
        )
        slot = _clean(term.get("slot"))
        aliases_raw = term.get("aliases")
        aliases = _aliases_from_json_value(aliases_raw)
        if not canonical:
            warnings.append(
                ImportWarning.warn(
                    code="json.missing_canonical",
                    message=f"Skipped term #{index}; canonical value is empty.",
                    source="parse",
                )
            )
            continue
        if not aliases:
            warnings.append(
                ImportWarning.warn(
                    code="json.no_aliases",
                    message=f"Canonical '{canonical}' has no aliases; skipped.",
                    source="parse",
                )
            )
            continue
        for alias in aliases:
            mappings.append(
                RawMapping(
                    canonical=canonical,
                    alias=alias,
                    slot=slot,
                    raw=f"{canonical}: {alias}",
                )
            )
    return ParseResult(mappings=mappings, warnings=warnings)


def _aliases_and_slot_from_json_value(value: object) -> tuple[list[str], str | None]:
    if isinstance(value, Mapping):
        slot = _clean(value.get("slot"))
        aliases = _aliases_from_json_value(value.get("aliases"))
        return aliases, slot
    return _aliases_from_json_value(value), None


def _aliases_from_json_value(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [_cleaned for _cleaned in [_clean(value)] if _cleaned]
    if isinstance(value, list):
        aliases: list[str] = []
        for item in value:
            if isinstance(item, str):
                alias = _clean(item)
            elif isinstance(item, Mapping):
                alias = _clean(item.get("value") or item.get("alias"))
            else:
                alias = ""
            if alias:
                aliases.append(alias)
        return aliases
    return []


def _split_alias_cell(value: str) -> list[str]:
    if "|" in value:
        parts = value.split("|")
    elif ";" in value:
        parts = value.split(";")
    else:
        parts = [value]
    return [cleaned for part in parts if (cleaned := _clean(part))]


def _split_es_terms(value: str) -> list[str]:
    return [cleaned for part in value.split(",") if (cleaned := _clean(part))]


def _strip_es_comment(line: str) -> str:
    return line.split("#", 1)[0]


def _first_existing(
    columns: Mapping[str, str],
    candidates: tuple[str, ...],
) -> str | None:
    for candidate in candidates:
        actual = columns.get(_normalize_header(candidate))
        if actual:
            return actual
    return None


def _normalize_header(value: str) -> str:
    return " ".join(value.strip().lower().replace("_", " ").split())


def _clean(value: object) -> str:
    if value is None:
        return ""
    return " ".join(str(value).strip().split())
