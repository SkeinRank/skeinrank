"""Local agent run and document-visit tracking for the alias scout.

Patch 41F adds a dependency-light tracking contract that mirrors the state we
will eventually persist in PostgreSQL. The tracker records run metadata,
document fingerprints, processing context, and skip/revisit decisions in a JSONL
ledger. It does not call SkeinRank, OpenRouter, or Elasticsearch and it never
mutates dictionaries, snapshots, or runtime state.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

JsonDict = dict[str, Any]

DEFAULT_CONTENT_FIELDS = (
    "query",
    "title",
    "text",
    "message",
    "content",
    "body",
    "snippet",
)
DEFAULT_SOURCE_ID_FIELDS = (
    "id",
    "source_id",
    "doc_id",
    "document_id",
    "trace_id",
)


@dataclass(frozen=True)
class AgentRunTrackingConfig:
    """Local JSONL tracking settings for the reference alias scout."""

    enabled: bool = True
    ledger_path: Path = Path(".cache/openrouter_alias_scout_run_ledger.jsonl")
    agent_name: str = "openrouter-alias-scout"
    agent_version: str = "41F"
    prompt_version: str = "canonical-hints-v1"
    skip_unchanged_documents: bool = True
    content_fields: tuple[str, ...] = DEFAULT_CONTENT_FIELDS
    source_id_fields: tuple[str, ...] = DEFAULT_SOURCE_ID_FIELDS
    max_recent_ledger_entries: int = 10000
    include_record_previews: bool = False
    preview_chars: int = 160

    @classmethod
    def from_mapping(
        cls, raw: Mapping[str, Any] | None, *, base_dir: Path | None = None
    ) -> "AgentRunTrackingConfig":
        """Create config from optional JSON config values."""

        if not raw:
            return cls()
        ledger_path = Path(str(raw.get("ledger_path", cls.ledger_path)))
        if base_dir is not None and not ledger_path.is_absolute():
            ledger_path = base_dir / ledger_path
        return cls(
            enabled=bool(raw.get("enabled", cls.enabled)),
            ledger_path=ledger_path,
            agent_name=str(raw.get("agent_name", cls.agent_name)),
            agent_version=str(raw.get("agent_version", cls.agent_version)),
            prompt_version=str(raw.get("prompt_version", cls.prompt_version)),
            skip_unchanged_documents=bool(
                raw.get(
                    "skip_unchanged_documents",
                    cls.skip_unchanged_documents,
                )
            ),
            content_fields=_as_tuple(raw.get("content_fields"), cls.content_fields),
            source_id_fields=_as_tuple(
                raw.get("source_id_fields"), cls.source_id_fields
            ),
            max_recent_ledger_entries=int(
                raw.get("max_recent_ledger_entries", cls.max_recent_ledger_entries)
            ),
            include_record_previews=bool(
                raw.get("include_record_previews", cls.include_record_previews)
            ),
            preview_chars=int(raw.get("preview_chars", cls.preview_chars)),
        )

    def with_overrides(
        self,
        *,
        ledger_path: Path | None = None,
        append_ledger: bool | None = None,
    ) -> "AgentRunTrackingConfig":
        """Return a copy with CLI overrides applied.

        ``append_ledger`` is accepted for API symmetry with CLI code. It does
        not change the config itself because appending is a command action, not
        a durable setting.
        """

        _ = append_ledger
        return AgentRunTrackingConfig(
            enabled=self.enabled,
            ledger_path=ledger_path or self.ledger_path,
            agent_name=self.agent_name,
            agent_version=self.agent_version,
            prompt_version=self.prompt_version,
            skip_unchanged_documents=self.skip_unchanged_documents,
            content_fields=self.content_fields,
            source_id_fields=self.source_id_fields,
            max_recent_ledger_entries=self.max_recent_ledger_entries,
            include_record_previews=self.include_record_previews,
            preview_chars=self.preview_chars,
        )

    def to_plan(self) -> JsonDict:
        """Return a network-free tracking plan."""

        return {
            "schema_version": "skeinrank.agent_run_tracking_plan.v1",
            "runner": "openrouter_alias_scout",
            "tracking_enabled": self.enabled,
            "ledger_path": str(self.ledger_path),
            "agent_name": self.agent_name,
            "agent_version": self.agent_version,
            "prompt_version": self.prompt_version,
            "skip_unchanged_documents": self.skip_unchanged_documents,
            "content_fields": list(self.content_fields),
            "source_id_fields": list(self.source_id_fields),
            "openrouter_calls": False,
            "skeinrank_api_calls": False,
            "elasticsearch_calls": False,
            "safety": {
                "runtime_mutation_enabled": False,
                "snapshot_publish_enabled": False,
                "direct_dictionary_write_enabled": False,
            },
        }


def build_agent_run_tracking_report(
    records: Sequence[Mapping[str, Any]],
    *,
    config: AgentRunTrackingConfig | None = None,
    run_id: str | None = None,
    binding_id: int | None = None,
    profile_name: str | None = None,
    openrouter_model: str = "openai/gpt-4o-mini",
    source_name: str = "local_evidence_records",
    append_ledger: bool = False,
) -> JsonDict:
    """Build a run/document tracking report for local evidence records."""

    cfg = config or AgentRunTrackingConfig()
    resolved_run_id = run_id or build_agent_run_id(
        records,
        config=cfg,
        binding_id=binding_id,
        profile_name=profile_name,
        openrouter_model=openrouter_model,
        source_name=source_name,
    )
    ledger_entries = load_agent_tracking_ledger(
        cfg.ledger_path, limit=cfg.max_recent_ledger_entries
    )
    latest_visits = _latest_document_visits(ledger_entries)
    context_hash = compute_processing_context_hash(
        config=cfg,
        binding_id=binding_id,
        profile_name=profile_name,
        openrouter_model=openrouter_model,
    )
    now = _utc_now_iso()
    document_visits = [
        _build_document_visit(
            record,
            record_index=index,
            config=cfg,
            latest_visits=latest_visits,
            run_id=resolved_run_id,
            observed_at=now,
            binding_id=binding_id,
            profile_name=profile_name,
            openrouter_model=openrouter_model,
            source_name=source_name,
            processing_context_hash=context_hash,
        )
        for index, record in enumerate(records)
    ]
    summary = _summarize_visits(document_visits)
    report = {
        "schema_version": "skeinrank.agent_run_tracking_report.v1",
        "runner": "openrouter_alias_scout",
        "run_id": resolved_run_id,
        "observed_at": now,
        "tracking_enabled": cfg.enabled,
        "ledger_path": str(cfg.ledger_path),
        "ledger_appended": False,
        "source_name": source_name,
        "binding_id": binding_id,
        "profile_name": profile_name,
        "openrouter_model": openrouter_model,
        "agent_name": cfg.agent_name,
        "agent_version": cfg.agent_version,
        "prompt_version": cfg.prompt_version,
        "processing_context_hash": context_hash,
        "summary": summary,
        "document_visits": document_visits,
        "openrouter_calls": False,
        "skeinrank_api_calls": False,
        "elasticsearch_calls": False,
        "runtime_mutation_enabled": False,
        "snapshot_publish_enabled": False,
        "safety": {
            "agent_may_mutate_runtime": False,
            "blocked_actions": [
                "direct_dictionary_write",
                "snapshot_publish",
                "direct_git_push",
                "runtime_mutation",
            ],
            "tracking_is_local_jsonl": True,
        },
    }
    if append_ledger:
        appended = append_agent_run_tracking_ledger(report, config=cfg)
        report["ledger_appended"] = True
        report["ledger_entries_written"] = appended
    return report


def append_agent_run_tracking_ledger(
    report: Mapping[str, Any], *, config: AgentRunTrackingConfig | None = None
) -> int:
    """Append document-visit tracking entries to the local JSONL ledger."""

    cfg = config or AgentRunTrackingConfig()
    if not cfg.enabled:
        return 0
    cfg.ledger_path.parent.mkdir(parents=True, exist_ok=True)
    entries = [_run_summary_entry(report)]
    entries.extend(
        _document_visit_ledger_entry(report, visit)
        for visit in report.get("document_visits", [])
        if isinstance(visit, Mapping)
    )
    with cfg.ledger_path.open("a", encoding="utf-8") as fh:
        for entry in entries:
            fh.write(json.dumps(entry, sort_keys=True) + "\n")
    return len(entries)


def load_agent_tracking_ledger(
    path: Path, *, limit: int | None = None
) -> list[JsonDict]:
    """Load recent JSONL tracking entries from a local ledger."""

    if not path.exists():
        return []
    rows: list[JsonDict] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), 1
    ):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"Invalid tracking ledger row at {path}:{line_number}")
        rows.append(value)
    if limit is not None and limit > 0:
        rows = rows[-limit:]
    return rows


def build_agent_run_id(
    records: Sequence[Mapping[str, Any]],
    *,
    config: AgentRunTrackingConfig | None = None,
    binding_id: int | None = None,
    profile_name: str | None = None,
    openrouter_model: str = "openai/gpt-4o-mini",
    source_name: str = "local_evidence_records",
) -> str:
    """Build a deterministic run id for the same input batch and context."""

    cfg = config or AgentRunTrackingConfig()
    payload = {
        "source_name": source_name,
        "binding_id": binding_id,
        "profile_name": profile_name,
        "agent_name": cfg.agent_name,
        "agent_version": cfg.agent_version,
        "prompt_version": cfg.prompt_version,
        "openrouter_model": openrouter_model,
        "record_hashes": [
            compute_record_content_hash(record, content_fields=cfg.content_fields)
            for record in records
        ],
    }
    digest = sha256(_stable_json(payload).encode("utf-8")).hexdigest()[:16]
    return f"openrouter-alias-scout-run:{digest}"


def compute_record_content_hash(
    record: Mapping[str, Any], *, content_fields: Sequence[str] = DEFAULT_CONTENT_FIELDS
) -> str:
    """Hash only the content-bearing fields used by the evidence sampler."""

    content: JsonDict = {}
    for field_name in content_fields:
        value = record.get(field_name)
        if value is not None and not isinstance(value, (dict, list)):
            normalized = str(value).strip()
            if normalized:
                content[field_name] = normalized
    if not content:
        content = {"record": _json_safe_mapping(record)}
    return sha256(_stable_json(content).encode("utf-8")).hexdigest()


def compute_processing_context_hash(
    *,
    config: AgentRunTrackingConfig,
    binding_id: int | None,
    profile_name: str | None,
    openrouter_model: str,
) -> str:
    """Hash the agent/model/prompt context that affects LLM review decisions."""

    payload = {
        "agent_name": config.agent_name,
        "agent_version": config.agent_version,
        "prompt_version": config.prompt_version,
        "binding_id": binding_id,
        "profile_name": profile_name,
        "openrouter_model": openrouter_model,
    }
    return sha256(_stable_json(payload).encode("utf-8")).hexdigest()[:24]


def _build_document_visit(
    record: Mapping[str, Any],
    *,
    record_index: int,
    config: AgentRunTrackingConfig,
    latest_visits: Mapping[tuple[str, str, str | None, int | None], Mapping[str, Any]],
    run_id: str,
    observed_at: str,
    binding_id: int | None,
    profile_name: str | None,
    openrouter_model: str,
    source_name: str,
    processing_context_hash: str,
) -> JsonDict:
    source_id = _resolve_source_id(record, config.source_id_fields, record_index)
    source_type = str(record.get("source_type") or "record")
    content_hash = compute_record_content_hash(
        record, content_fields=config.content_fields
    )
    key = (source_id, source_type, profile_name, binding_id)
    previous = latest_visits.get(key)
    visit_status = _classify_visit(previous, content_hash, processing_context_hash)
    should_scan = not (
        config.skip_unchanged_documents and visit_status == "unchanged_seen"
    )
    visit: JsonDict = {
        "run_id": run_id,
        "observed_at": observed_at,
        "source_name": source_name,
        "source_id": source_id,
        "source_type": source_type,
        "record_index": record_index,
        "content_hash": content_hash,
        "processing_context_hash": processing_context_hash,
        "visit_status": visit_status,
        "should_scan": should_scan,
        "binding_id": binding_id,
        "profile_name": profile_name,
        "agent_name": config.agent_name,
        "agent_version": config.agent_version,
        "prompt_version": config.prompt_version,
        "openrouter_model": openrouter_model,
        "fields_present": [
            field_name
            for field_name in config.content_fields
            if record.get(field_name) is not None
        ],
    }
    if previous:
        visit["previous_content_hash"] = previous.get("content_hash")
        visit["previous_processing_context_hash"] = previous.get(
            "processing_context_hash"
        )
        visit["previous_observed_at"] = previous.get("observed_at")
        visit["previous_run_id"] = previous.get("run_id")
    if config.include_record_previews:
        visit["preview"] = _build_record_preview(record, config)
    return visit


def _classify_visit(
    previous: Mapping[str, Any] | None,
    content_hash: str,
    processing_context_hash: str,
) -> str:
    if previous is None:
        return "new_document"
    if previous.get("content_hash") != content_hash:
        return "content_changed"
    if previous.get("processing_context_hash") != processing_context_hash:
        return "context_changed"
    return "unchanged_seen"


def _latest_document_visits(
    ledger_entries: Sequence[Mapping[str, Any]],
) -> dict[tuple[str, str, str | None, int | None], Mapping[str, Any]]:
    visits: dict[tuple[str, str, str | None, int | None], Mapping[str, Any]] = {}
    for entry in ledger_entries:
        if entry.get("entry_type") != "document_visit":
            continue
        source_id = str(entry.get("source_id") or "")
        source_type = str(entry.get("source_type") or "record")
        if not source_id:
            continue
        binding_raw = entry.get("binding_id")
        binding_id = int(binding_raw) if binding_raw is not None else None
        profile_name = entry.get("profile_name")
        key = (
            source_id,
            source_type,
            str(profile_name) if profile_name is not None else None,
            binding_id,
        )
        visits[key] = entry
    return visits


def _summarize_visits(visits: Sequence[Mapping[str, Any]]) -> JsonDict:
    counts = {
        "new_document": 0,
        "unchanged_seen": 0,
        "content_changed": 0,
        "context_changed": 0,
    }
    should_scan = 0
    skipped = 0
    for visit in visits:
        status = str(visit.get("visit_status"))
        if status in counts:
            counts[status] += 1
        if visit.get("should_scan"):
            should_scan += 1
        else:
            skipped += 1
    return {
        "records_loaded": len(visits),
        "unique_documents": len(
            {(visit.get("source_id"), visit.get("source_type")) for visit in visits}
        ),
        "should_scan": should_scan,
        "skipped_unchanged": skipped,
        "visit_statuses": counts,
    }


def _run_summary_entry(report: Mapping[str, Any]) -> JsonDict:
    return {
        "entry_type": "agent_run",
        "schema_version": "skeinrank.agent_run_tracking_ledger.v1",
        "run_id": report.get("run_id"),
        "observed_at": report.get("observed_at"),
        "runner": report.get("runner"),
        "source_name": report.get("source_name"),
        "binding_id": report.get("binding_id"),
        "profile_name": report.get("profile_name"),
        "openrouter_model": report.get("openrouter_model"),
        "agent_name": report.get("agent_name"),
        "agent_version": report.get("agent_version"),
        "prompt_version": report.get("prompt_version"),
        "processing_context_hash": report.get("processing_context_hash"),
        "summary": report.get("summary"),
    }


def _document_visit_ledger_entry(
    report: Mapping[str, Any], visit: Mapping[str, Any]
) -> JsonDict:
    entry = dict(visit)
    entry["entry_type"] = "document_visit"
    entry["schema_version"] = "skeinrank.agent_document_visit.v1"
    entry["runner"] = report.get("runner")
    return entry


def _resolve_source_id(
    record: Mapping[str, Any], source_id_fields: Sequence[str], record_index: int
) -> str:
    for field_name in source_id_fields:
        value = record.get(field_name)
        if value is not None and str(value).strip():
            return str(value).strip()
    digest = sha256(
        _stable_json(_json_safe_mapping(record)).encode("utf-8")
    ).hexdigest()
    return f"record-{record_index + 1}-{digest[:12]}"


def _build_record_preview(
    record: Mapping[str, Any], config: AgentRunTrackingConfig
) -> str:
    parts: list[str] = []
    for field_name in config.content_fields:
        value = record.get(field_name)
        if value is not None and not isinstance(value, (dict, list)):
            text = str(value).strip()
            if text:
                parts.append(text)
    preview = " | ".join(parts)
    if len(preview) > config.preview_chars:
        return preview[: max(config.preview_chars - 1, 0)].rstrip() + "…"
    return preview


def _as_tuple(value: Any, default: Sequence[str]) -> tuple[str, ...]:
    if value is None:
        return tuple(default)
    if isinstance(value, str):
        return (value,)
    if isinstance(value, Sequence):
        return tuple(str(item) for item in value if str(item).strip())
    return tuple(default)


def _json_safe_mapping(value: Mapping[str, Any]) -> JsonDict:
    safe: JsonDict = {}
    for key, item in value.items():
        if isinstance(item, (str, int, float, bool)) or item is None:
            safe[str(key)] = item
        elif isinstance(item, Sequence) and not isinstance(
            item, (str, bytes, bytearray)
        ):
            safe[str(key)] = [str(child) for child in item]
        elif isinstance(item, Mapping):
            safe[str(key)] = _json_safe_mapping(item)
        else:
            safe[str(key)] = str(item)
    return safe


def _stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _utc_now_iso() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat()
