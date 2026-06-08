"""Public dictionary import runner."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from skeinrank.drafts import DictionaryDraft
from skeinrank.sdk import Dictionary

from .builder import build_dictionary
from .parsers import (
    CsvDictionaryParser,
    EsSynonymsParser,
    JsonDictionaryParser,
    detect_format,
)
from .report import ImportReport
from .validator_bridge import validate_imported_dictionary

_PARSERS = {
    "json": JsonDictionaryParser(),
    "csv": CsvDictionaryParser(),
    "es-synonyms": EsSynonymsParser(),
}


@dataclass
class ImportResult:
    """Dictionary import output and report."""

    dictionary: Dictionary | None
    report: ImportReport

    def to_draft(self) -> DictionaryDraft:
        """Return a reviewable dictionary draft from the import candidate."""

        if self.dictionary is None:
            raise ValueError(
                "Cannot create draft: dictionary import produced fatal findings."
            )
        return DictionaryDraft.from_dictionary(
            self.dictionary,
            source_path=self.report.source_path,
            source_format=self.report.detected_format,
            findings=self.report.warnings,
            source="import",
        )

    def save(self, path: str | Path) -> None:
        """Write the imported dictionary JSON to ``path``."""

        if self.dictionary is None:
            raise ValueError("Cannot save: dictionary import produced fatal findings.")
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        payload = self.dictionary.model_dump(mode="json", exclude_none=True)
        destination.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def import_dictionary(
    path: str | Path,
    *,
    fmt: str | None = None,
    name: str = "imported",
    run_validator: bool = True,
    strict_validator: bool = False,
) -> ImportResult:
    """Convert an existing term list into a local SkeinRank dictionary candidate.

    Supported input formats are simple JSON dictionaries, CSV files with
    canonical/alias columns, and Elasticsearch/OpenSearch synonym-list text files.
    The function returns a dictionary candidate and a report. It never mutates
    governance state or runtime bindings. Validator findings are advisory by
    default and can be made fatal with ``strict_validator=True``.
    """

    source = Path(path)
    content = source.read_text(encoding="utf-8")
    detected = detect_format(str(source), content, override=fmt)
    parser = _PARSERS[detected]
    parsed = parser.parse(content)
    dictionary, build_warnings = build_dictionary(parsed.mappings, name=name)

    warnings = [*parsed.warnings, *build_warnings]
    if dictionary is not None and run_validator:
        warnings.extend(
            validate_imported_dictionary(
                dictionary,
                strict=strict_validator,
            )
        )

    canonical_count = len(dictionary.terms) if dictionary else 0
    alias_count = (
        sum(len(term.aliases) for term in dictionary.terms) if dictionary else 0
    )
    report = ImportReport(
        source_path=str(source),
        detected_format=detected,
        canonical_count=canonical_count,
        alias_count=alias_count,
        warnings=warnings,
    )
    if not report.is_ok:
        dictionary = None
    return ImportResult(dictionary=dictionary, report=report)
