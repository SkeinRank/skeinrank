"""Compact evidence sampling for the OpenRouter alias scout example.

Patch 40I keeps evidence gathering deterministic and dependency-light. It samples
short windows around discovered candidate aliases from failed-query/search-log/doc
JSONL records so later LLM review never needs full documents.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:  # pragma: no cover - import style depends on how the example is executed.
    from .candidate_discovery import AliasCandidate
except ImportError:  # pragma: no cover
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from candidate_discovery import AliasCandidate

JsonDict = dict[str, Any]

DEFAULT_TEXT_FIELDS = (
    "query",
    "snippet",
    "message",
    "text",
    "content",
    "body",
    "title",
)
DEFAULT_NESTED_COLLECTION_FIELDS = (
    "evidence",
    "documents",
    "docs",
    "hits",
    "records",
    "windows",
)
DEFAULT_SOURCE_ID_FIELDS = ("id", "doc_id", "document_id", "query_id", "trace_id")


@dataclass(frozen=True)
class EvidenceSamplerConfig:
    """Tunable local-only evidence sampling settings."""

    max_records: int = 100
    max_docs: int = 5
    max_windows: int = 7
    window_chars: int = 120
    max_window_chars: int = 260
    max_total_chars: int = 1200
    text_fields: tuple[str, ...] = DEFAULT_TEXT_FIELDS
    nested_collection_fields: tuple[str, ...] = DEFAULT_NESTED_COLLECTION_FIELDS
    source_id_fields: tuple[str, ...] = DEFAULT_SOURCE_ID_FIELDS

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any] | None) -> "EvidenceSamplerConfig":
        """Create config from optional JSON config values."""

        if not raw:
            return cls()

        def _string_tuple(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
            value = raw.get(name)
            if value is None:
                return default
            if not isinstance(value, list) or not all(
                isinstance(item, str) for item in value
            ):
                raise ValueError(f"evidence_sampler.{name} must be a string list")
            normalized = tuple(item.strip() for item in value if item.strip())
            return normalized or default

        return cls(
            max_records=int(raw.get("max_records", cls.max_records)),
            max_docs=int(raw.get("max_docs", cls.max_docs)),
            max_windows=int(raw.get("max_windows", cls.max_windows)),
            window_chars=int(raw.get("window_chars", cls.window_chars)),
            max_window_chars=int(raw.get("max_window_chars", cls.max_window_chars)),
            max_total_chars=int(raw.get("max_total_chars", cls.max_total_chars)),
            text_fields=_string_tuple("text_fields", DEFAULT_TEXT_FIELDS),
            nested_collection_fields=_string_tuple(
                "nested_collection_fields", DEFAULT_NESTED_COLLECTION_FIELDS
            ),
            source_id_fields=_string_tuple(
                "source_id_fields", DEFAULT_SOURCE_ID_FIELDS
            ),
        )


@dataclass(frozen=True)
class EvidenceWindow:
    """A compact context window around one candidate surface form."""

    candidate_alias: str
    text: str
    source_id: str
    source_type: str
    field: str
    start_char: int
    end_char: int
    record_index: int
    metadata: JsonDict = field(default_factory=dict)

    def to_dict(self) -> JsonDict:
        """Return a stable JSON-serializable evidence window."""

        payload: JsonDict = {
            "candidate_alias": self.candidate_alias,
            "source_id": self.source_id,
            "source_type": self.source_type,
            "field": self.field,
            "text": self.text,
            "start_char": self.start_char,
            "end_char": self.end_char,
            "record_index": self.record_index,
        }
        if self.metadata:
            payload["metadata"] = dict(self.metadata)
        return payload


def load_jsonl_records(path: Path, *, limit: int | None = None) -> list[JsonDict]:
    """Load JSONL rows used as search-log/document evidence records."""

    rows: list[JsonDict] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), 1
    ):
        if not line.strip():
            continue
        import json

        value = json.loads(line)
        if isinstance(value, str):
            value = {"text": value}
        if not isinstance(value, dict):
            raise ValueError(f"Invalid evidence row at {path}:{line_number}")
        rows.append(value)
        if limit is not None and len(rows) >= limit:
            break
    return rows


def sample_evidence_windows(
    candidate_alias: str,
    records: Sequence[Mapping[str, Any]],
    *,
    config: EvidenceSamplerConfig | None = None,
) -> list[EvidenceWindow]:
    """Sample compact evidence windows around a candidate surface form.

    This function is deliberately local and deterministic. It scans already
    provided rows; it does not call Elasticsearch, OpenRouter, or SkeinRank.
    """

    cfg = config or EvidenceSamplerConfig()
    surface = candidate_alias.strip()
    if not surface:
        return []

    matcher = _compile_surface_matcher(surface)
    windows: list[EvidenceWindow] = []
    seen_docs: set[str] = set()
    total_chars = 0

    for record_index, record in enumerate(records[: cfg.max_records]):
        source_id = _record_source_id(record, record_index, cfg)
        if source_id in seen_docs and len(seen_docs) >= cfg.max_docs:
            continue
        if source_id not in seen_docs and len(seen_docs) >= cfg.max_docs:
            continue

        record_windows: list[EvidenceWindow] = []
        for field_name, text, metadata in _iter_text_values(record, cfg):
            match = matcher.search(text)
            if match is None:
                continue
            window_text, start_char, end_char = _make_context_window(
                text,
                match.start(),
                match.end(),
                window_chars=cfg.window_chars,
                max_window_chars=cfg.max_window_chars,
            )
            if total_chars + len(window_text) > cfg.max_total_chars:
                continue
            record_windows.append(
                EvidenceWindow(
                    candidate_alias=surface,
                    text=window_text,
                    source_id=source_id,
                    source_type=str(
                        record.get("source_type") or record.get("source") or "record"
                    ),
                    field=field_name,
                    start_char=start_char,
                    end_char=end_char,
                    record_index=record_index,
                    metadata=metadata,
                )
            )
            break

        if not record_windows:
            continue
        seen_docs.add(source_id)
        for window in record_windows:
            windows.append(window)
            total_chars += len(window.text)
            if len(windows) >= cfg.max_windows:
                return windows
    return windows


def build_evidence_sampling_report(
    candidates: Sequence[AliasCandidate],
    records: Sequence[Mapping[str, Any]],
    *,
    config: EvidenceSamplerConfig | None = None,
    binding_id: int | None = None,
    profile_name: str | None = None,
) -> JsonDict:
    """Return a compact JSON report for candidate evidence sampling."""

    cfg = config or EvidenceSamplerConfig()
    sampled: list[JsonDict] = []
    for candidate in candidates:
        windows = sample_evidence_windows(candidate.surface, records, config=cfg)
        sampled.append(
            {
                "candidate_alias": candidate.surface,
                "windows_found": len(windows),
                "total_chars": sum(len(window.text) for window in windows),
                "evidence_windows": [window.to_dict() for window in windows],
            }
        )

    return {
        "schema_version": "skeinrank.agent_evidence_sampling.v1",
        "runner": "openrouter_alias_scout",
        "llm_enabled": False,
        "binding_id": binding_id,
        "profile_name": profile_name,
        "candidate_count": len(candidates),
        "records_loaded": min(len(records), cfg.max_records),
        "config": {
            "max_records": cfg.max_records,
            "max_docs": cfg.max_docs,
            "max_windows": cfg.max_windows,
            "window_chars": cfg.window_chars,
            "max_window_chars": cfg.max_window_chars,
            "max_total_chars": cfg.max_total_chars,
        },
        "samples": sampled,
    }


def build_candidate_evidence_pack(
    candidate: AliasCandidate,
    windows: Sequence[EvidenceWindow],
    *,
    binding_id: int | None = None,
    profile_name: str | None = None,
    known_conflicts: Sequence[str] = (),
) -> JsonDict:
    """Build a compact LLM-ready pack with sampled evidence windows."""

    return {
        "candidate_alias": candidate.surface,
        "possible_canonical": None,
        "slot": None,
        "binding_id": binding_id,
        "profile_name": profile_name,
        "evidence": [window.text for window in windows],
        "evidence_windows": [window.to_dict() for window in windows],
        "stats": {
            "weighted_count": round(candidate.weighted_count, 4),
            "document_frequency": candidate.document_frequency,
            "discovery_score": round(candidate.score, 4),
            "discovery_reasons": list(candidate.reasons),
            "evidence_windows": len(windows),
            "evidence_total_chars": sum(len(window.text) for window in windows),
        },
        "known_conflicts": [item for item in known_conflicts if item],
    }


def _compile_surface_matcher(surface: str) -> re.Pattern[str]:
    escaped = re.escape(surface)
    return re.compile(rf"(?<![\w]){escaped}(?![\w])", re.IGNORECASE)


def _record_source_id(
    record: Mapping[str, Any], record_index: int, config: EvidenceSamplerConfig
) -> str:
    for field_name in config.source_id_fields:
        value = record.get(field_name)
        if value is not None and str(value).strip():
            return str(value).strip()
    return f"record-{record_index + 1}"


def _iter_text_values(
    record: Mapping[str, Any], config: EvidenceSamplerConfig
) -> list[tuple[str, str, JsonDict]]:
    values: list[tuple[str, str, JsonDict]] = []
    _collect_text_values(record, config=config, values=values, prefix="")
    return values


def _collect_text_values(
    value: Any,
    *,
    config: EvidenceSamplerConfig,
    values: list[tuple[str, str, JsonDict]],
    prefix: str,
) -> None:
    if isinstance(value, Mapping):
        for field_name in config.text_fields:
            raw_text = value.get(field_name)
            if isinstance(raw_text, str) and raw_text.strip():
                values.append(
                    (
                        f"{prefix}{field_name}" if prefix else field_name,
                        _compact_whitespace(raw_text),
                        _metadata_from_mapping(value),
                    )
                )
        for nested_name in config.nested_collection_fields:
            nested = value.get(nested_name)
            if isinstance(nested, list):
                for index, item in enumerate(nested):
                    _collect_text_values(
                        item,
                        config=config,
                        values=values,
                        prefix=f"{prefix}{nested_name}[{index}].",
                    )
            elif isinstance(nested, Mapping):
                _collect_text_values(
                    nested,
                    config=config,
                    values=values,
                    prefix=f"{prefix}{nested_name}.",
                )


def _metadata_from_mapping(value: Mapping[str, Any]) -> JsonDict:
    metadata: JsonDict = {}
    for metadata_field in ("title", "index", "rank", "score", "timestamp"):
        raw = value.get(metadata_field)
        if raw is not None and not isinstance(raw, (dict, list)):
            metadata[metadata_field] = raw
    return metadata


def _make_context_window(
    text: str,
    match_start: int,
    match_end: int,
    *,
    window_chars: int,
    max_window_chars: int,
) -> tuple[str, int, int]:
    start = max(match_start - window_chars, 0)
    end = min(match_end + window_chars, len(text))
    window = text[start:end].strip()
    if start > 0:
        window = "…" + window
    if end < len(text):
        window = window + "…"
    if len(window) > max_window_chars:
        window = window[: max_window_chars - 1].rstrip() + "…"
    return window, start, end


def _compact_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


__all__ = [
    "EvidenceSamplerConfig",
    "EvidenceWindow",
    "build_candidate_evidence_pack",
    "build_evidence_sampling_report",
    "load_jsonl_records",
    "sample_evidence_windows",
]
