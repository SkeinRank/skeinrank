"""Import existing dictionaries and synonym lists into SkeinRank format."""

from skeinrank.drafts import (
    DictionaryDraft,
    DraftCandidate,
    DraftFinding,
    EvidenceSnippet,
)

from .models import ImportWarning, ParseResult, RawMapping, Severity
from .parsers import (
    CsvDictionaryParser,
    EsSynonymsParser,
    JsonDictionaryParser,
    detect_format,
)
from .report import ImportReport
from .runner import ImportResult, import_dictionary
from .validator_bridge import validate_imported_dictionary

__all__ = [
    "CsvDictionaryParser",
    "DictionaryDraft",
    "DraftCandidate",
    "DraftFinding",
    "EvidenceSnippet",
    "EsSynonymsParser",
    "ImportReport",
    "ImportResult",
    "ImportWarning",
    "JsonDictionaryParser",
    "ParseResult",
    "RawMapping",
    "Severity",
    "detect_format",
    "import_dictionary",
    "validate_imported_dictionary",
]
