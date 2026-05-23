"""Before/after evaluation helpers for runtime snapshot artifacts.

The evaluator is intentionally dependency-light and offline-friendly. It compares
portable runtime snapshot artifacts and can optionally run a small query set
through both alias maps to show which canonicalization plans changed.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .runtime_snapshots import (
    LoadedRuntimeSnapshotArtifact,
    RuntimeAliasEntry,
    RuntimeSnapshotArtifactCache,
)

SNAPSHOT_EVALUATION_SCHEMA_VERSION = "skeinrank.snapshot_evaluation.v1"


@dataclass(frozen=True)
class EvaluationQuery:
    """One query used for before/after runtime snapshot evaluation."""

    query: str
    query_id: str | None = None


def evaluate_runtime_snapshot_artifacts(
    *,
    before_path: str | Path,
    after_path: str | Path,
    queries_path: str | Path | None = None,
) -> dict[str, Any]:
    """Evaluate two runtime snapshot artifacts and return a JSON report."""

    cache = RuntimeSnapshotArtifactCache(max_entries=2)
    before = cache.get(before_path)
    after = cache.get(after_path)
    queries = load_evaluation_queries(queries_path) if queries_path else []
    return evaluate_loaded_runtime_snapshot_artifacts(
        before=before,
        after=after,
        queries=queries,
    )


def evaluate_loaded_runtime_snapshot_artifacts(
    *,
    before: LoadedRuntimeSnapshotArtifact,
    after: LoadedRuntimeSnapshotArtifact,
    queries: list[EvaluationQuery] | None = None,
) -> dict[str, Any]:
    """Evaluate two already-loaded runtime snapshot artifacts."""

    query_items = list(queries or [])
    alias_diff = _alias_diff(before.alias_entries, after.alias_entries)
    tag_diff = _tag_diff(before.alias_entries, after.alias_entries)
    query_report = _query_diff(before.alias_entries, after.alias_entries, query_items)
    return {
        "schema_version": SNAPSHOT_EVALUATION_SCHEMA_VERSION,
        "before": _artifact_side_summary(before),
        "after": _artifact_side_summary(after),
        "aliases": alias_diff,
        "tags": tag_diff,
        "queries": query_report,
        "risk_summary": _risk_summary(alias_diff, query_report),
    }


def load_evaluation_queries(path: str | Path) -> list[EvaluationQuery]:
    """Load evaluation queries from JSON or JSONL.

    Supported formats:
    - JSON list of strings;
    - JSON list of objects with ``query`` and optional ``id``/``query_id``;
    - JSONL with one string or object per line.
    """

    query_path = Path(path).expanduser().resolve()
    raw = query_path.read_text(encoding="utf-8")
    if query_path.suffix.lower() == ".jsonl":
        return _load_jsonl_queries(raw)
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid evaluation query JSON: {exc}") from exc
    return _decode_query_items(decoded)


def _load_jsonl_queries(raw: str) -> list[EvaluationQuery]:
    items: list[Any] = []
    for line_number, line in enumerate(raw.splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            items.append(json.loads(stripped))
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Invalid evaluation query JSONL at line {line_number}: {exc}"
            ) from exc
    return _decode_query_items(items)


def _decode_query_items(decoded: Any) -> list[EvaluationQuery]:
    if not isinstance(decoded, list):
        raise ValueError("Evaluation queries must be a JSON list or JSONL stream")
    queries: list[EvaluationQuery] = []
    for index, item in enumerate(decoded):
        if isinstance(item, str):
            query = item.strip()
            query_id = None
        elif isinstance(item, dict):
            query = str(item.get("query") or "").strip()
            query_id_value = item.get("query_id", item.get("id"))
            query_id = str(query_id_value) if query_id_value is not None else None
        else:
            raise ValueError(
                "Evaluation query items must be strings or objects with a query field"
            )
        if not query:
            raise ValueError(f"Evaluation query at index {index} is empty")
        queries.append(EvaluationQuery(query=query, query_id=query_id))
    return queries


def _artifact_side_summary(loaded: LoadedRuntimeSnapshotArtifact) -> dict[str, Any]:
    tags = sorted({tag for entry in loaded.alias_entries for tag in entry.tags})
    slots = sorted({entry.slot for entry in loaded.alias_entries})
    canonicals = sorted({entry.normalized_canonical for entry in loaded.alias_entries})
    return {
        "path": str(loaded.path) if loaded.path is not None else None,
        "schema_version": loaded.artifact.get("schema_version"),
        "snapshot_version": loaded.snapshot_version,
        "checksum": loaded.checksum,
        "binding_id": loaded.binding.get("id"),
        "binding_name": loaded.binding.get("name"),
        "profile_name": loaded.profile.get("name"),
        "alias_entries_total": len(loaded.alias_entries),
        "canonical_values_total": len(canonicals),
        "slots": slots,
        "tags": tags,
        "tags_total": len(tags),
    }


def _alias_diff(
    before_entries: tuple[RuntimeAliasEntry, ...],
    after_entries: tuple[RuntimeAliasEntry, ...],
) -> dict[str, Any]:
    before = _entry_map(before_entries)
    after = _entry_map(after_entries)
    before_keys = set(before)
    after_keys = set(after)
    added_keys = sorted(after_keys - before_keys)
    removed_keys = sorted(before_keys - after_keys)
    changed_keys = sorted(
        key
        for key in before_keys & after_keys
        if _entry_fingerprint(before[key]) != _entry_fingerprint(after[key])
    )
    unchanged_keys = sorted((before_keys & after_keys) - set(changed_keys))
    return {
        "before_total": len(before),
        "after_total": len(after),
        "added_total": len(added_keys),
        "removed_total": len(removed_keys),
        "changed_total": len(changed_keys),
        "unchanged_total": len(unchanged_keys),
        "added": [_entry_payload(after[key]) for key in added_keys],
        "removed": [_entry_payload(before[key]) for key in removed_keys],
        "changed": [
            {
                "normalized_alias": key,
                "before": _entry_payload(before[key]),
                "after": _entry_payload(after[key]),
            }
            for key in changed_keys
        ],
    }


def _tag_diff(
    before_entries: tuple[RuntimeAliasEntry, ...],
    after_entries: tuple[RuntimeAliasEntry, ...],
) -> dict[str, Any]:
    before_tags = {tag for entry in before_entries for tag in entry.tags}
    after_tags = {tag for entry in after_entries for tag in entry.tags}
    return {
        "before_total": len(before_tags),
        "after_total": len(after_tags),
        "added_total": len(after_tags - before_tags),
        "removed_total": len(before_tags - after_tags),
        "added": sorted(after_tags - before_tags),
        "removed": sorted(before_tags - after_tags),
        "unchanged": sorted(before_tags & after_tags),
    }


def _query_diff(
    before_entries: tuple[RuntimeAliasEntry, ...],
    after_entries: tuple[RuntimeAliasEntry, ...],
    queries: list[EvaluationQuery],
) -> dict[str, Any]:
    changes: list[dict[str, Any]] = []
    unchanged = 0
    for query in queries:
        before_plan = _canonicalize_query(query.query, before_entries)
        after_plan = _canonicalize_query(query.query, after_entries)
        changed = before_plan != after_plan
        if changed:
            item: dict[str, Any] = {
                "query": query.query,
                "before": before_plan,
                "after": after_plan,
            }
            if query.query_id is not None:
                item["query_id"] = query.query_id
            changes.append(item)
        else:
            unchanged += 1
    return {
        "total": len(queries),
        "changed_total": len(changes),
        "unchanged_total": unchanged,
        "changed": changes,
    }


def _canonicalize_query(
    query: str,
    entries: tuple[RuntimeAliasEntry, ...],
) -> dict[str, Any]:
    matches: list[dict[str, Any]] = []
    canonical_query = query
    for entry in sorted(
        entries, key=lambda item: (-len(item.alias_value), item.alias_value)
    ):
        pattern = re.compile(
            rf"(?<![\w]){re.escape(entry.alias_value)}(?![\w])",
            flags=re.IGNORECASE,
        )
        found = list(pattern.finditer(canonical_query))
        if not found:
            continue
        canonical_query = pattern.sub(entry.canonical_value, canonical_query)
        matches.append(
            {
                "alias_value": entry.alias_value,
                "normalized_alias": entry.normalized_alias,
                "canonical_value": entry.canonical_value,
                "normalized_canonical": entry.normalized_canonical,
                "slot": entry.slot,
                "tags": list(entry.tags),
                "matches_total": len(found),
            }
        )
    return {
        "canonical_query": canonical_query,
        "changed": canonical_query != query,
        "matched_aliases": sorted({item["normalized_alias"] for item in matches}),
        "canonical_values": sorted({item["canonical_value"] for item in matches}),
        "slots": sorted({item["slot"] for item in matches}),
        "tags": sorted({tag for item in matches for tag in item["tags"]}),
        "matches": matches,
    }


def _risk_summary(
    alias_diff: dict[str, Any], query_report: dict[str, Any]
) -> dict[str, Any]:
    notes: list[str] = []
    if alias_diff["removed_total"]:
        notes.append(
            "Aliases were removed; check recall regressions for affected queries."
        )
    if alias_diff["changed_total"]:
        notes.append("Aliases changed canonical target, slot, tags, or confidence.")
    if query_report["changed_total"]:
        notes.append("Some sample queries produce different canonicalization plans.")
    if not notes:
        notes.append("No alias or query-plan changes were detected.")
    return {
        "has_alias_changes": bool(
            alias_diff["added_total"]
            or alias_diff["removed_total"]
            or alias_diff["changed_total"]
        ),
        "has_query_changes": bool(query_report["changed_total"]),
        "notes": notes,
    }


def _entry_map(entries: tuple[RuntimeAliasEntry, ...]) -> dict[str, RuntimeAliasEntry]:
    return {entry.normalized_alias: entry for entry in entries}


def _entry_fingerprint(entry: RuntimeAliasEntry) -> tuple[Any, ...]:
    return (
        entry.normalized_canonical,
        entry.canonical_value,
        entry.slot,
        round(float(entry.confidence), 8),
        tuple(entry.tags),
    )


def _entry_payload(entry: RuntimeAliasEntry) -> dict[str, Any]:
    return {
        "alias_value": entry.alias_value,
        "normalized_alias": entry.normalized_alias,
        "canonical_value": entry.canonical_value,
        "normalized_canonical": entry.normalized_canonical,
        "slot": entry.slot,
        "confidence": entry.confidence,
        "tags": list(entry.tags),
    }
