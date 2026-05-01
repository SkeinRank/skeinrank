from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterator, Sequence

from skeinrank import extract_attributes


@dataclass(frozen=True)
class ElasticsearchEnrichmentConfig:
    """Configuration for Elasticsearch document enrichment.

    SkeinRank reads existing documents, extracts normalized technical
    attributes locally, and can either preview or write a partial update into
    ``target_field``. The caller must explicitly choose dry-run or write mode
    in the CLI.
    """

    index: str
    text_fields: tuple[str, ...]
    target_field: str = "skeinrank"
    profile: str = "default_it"
    limit: int = 20
    batch_size: int = 50
    include_passport: bool = False
    include_evidence: bool = False

    def __post_init__(self) -> None:
        if not self.index:
            raise ValueError("index must not be empty")
        if not self.text_fields:
            raise ValueError("at least one text field must be provided")
        if not self.target_field:
            raise ValueError("target_field must not be empty")
        if self.limit < 1:
            raise ValueError("limit must be >= 1")
        if self.batch_size < 1:
            raise ValueError("batch_size must be >= 1")


@dataclass(frozen=True)
class EnrichmentPreview:
    """Preview/update descriptor for one Elasticsearch hit."""

    doc_id: str
    index: str
    text_fields: tuple[str, ...]
    target_field: str
    text: str
    payload: dict[str, Any]

    def as_update_doc(self) -> dict[str, Any]:
        """Return the partial document to send to Elasticsearch update API."""
        return {self.target_field: self.payload}

    def as_record(self) -> dict[str, Any]:
        return {
            "_id": self.doc_id,
            "_index": self.index,
            "text_fields": list(self.text_fields),
            "target_field": self.target_field,
            "text_preview": self.text[:300],
            "doc": self.as_update_doc(),
        }

    def as_bulk_operations(self) -> list[dict[str, Any]]:
        """Return NDJSON-like bulk operations as Python dictionaries.

        The Elasticsearch Python client accepts this shape through the
        ``operations`` parameter in modern versions. ``_call_bulk`` also falls
        back to the older ``body`` parameter for compatibility.
        """
        return [
            {"update": {"_index": self.index, "_id": self.doc_id}},
            {"doc": self.as_update_doc()},
        ]


def _flatten_value(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            out.extend(_flatten_value(item))
        return out
    if isinstance(value, tuple):
        out = []
        for item in value:
            out.extend(_flatten_value(item))
        return out
    if isinstance(value, dict):
        # Do not guess how to render arbitrary nested objects. Users should pass
        # explicit dotted fields such as comments.text when they need them.
        return []
    text = str(value).strip()
    return [text] if text else []


def _get_by_dotted_path(source: dict[str, Any], field: str) -> list[str]:
    """Read a simple dotted field path from an Elasticsearch _source.

    This is deliberately small and predictable. It supports common fields such
    as ``title``, ``body``, and simple nested paths like ``metadata.summary``. It
    does not try to implement the full Elasticsearch nested query model.
    """
    current: Any = source
    for part in field.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list):
            next_values: list[Any] = []
            for item in current:
                if isinstance(item, dict) and part in item:
                    next_values.append(item[part])
            current = next_values
        else:
            return []
    return _flatten_value(current)


def compose_hit_text(hit: dict[str, Any], text_fields: Sequence[str]) -> str:
    source = hit.get("_source", {}) or {}
    parts: list[str] = []
    for field in text_fields:
        parts.extend(_get_by_dotted_path(source, field))
    return "\n".join(part for part in parts if part).strip()


def _slot_values_from_attributes(
    attributes: list[dict[str, Any]],
) -> dict[str, list[str]]:
    slots: dict[str, set[str]] = {}
    for item in attributes:
        slot = str(item.get("slot", "")).strip()
        value = str(item.get("value", "")).strip()
        if not slot or not value:
            continue
        slots.setdefault(slot, set()).add(value)
    return {slot: sorted(values) for slot, values in sorted(slots.items())}


def build_enrichment_payload(
    text: str,
    *,
    profile: str = "default_it",
    include_passport: bool = False,
    include_evidence: bool = False,
) -> dict[str, Any]:
    """Build the Elasticsearch enrichment payload for one text.

    The default payload is compact for production indexing: canonical values and
    slot-grouped values are enough for filtering, boosting, and downstream
    reranking. Pass ``include_evidence=True`` to include full attributes,
    evidences, and the full snapshot object for debugging.
    """
    pack = extract_attributes(text, profile=profile, debug=include_passport)
    attributes = [item.model_dump(mode="json") for item in pack.attributes]
    canonical_values = sorted({item["value"] for item in attributes})
    payload: dict[str, Any] = {
        "profile_id": pack.profile_id,
        "snapshot_version": pack.snapshot.version
        if pack.snapshot is not None
        else None,
        "alias_matcher_backend": pack.alias_matcher_backend,
        "canonical_values": canonical_values,
        "slots": _slot_values_from_attributes(attributes),
    }
    if include_evidence:
        payload["snapshot"] = (
            pack.snapshot.model_dump(mode="json") if pack.snapshot is not None else None
        )
        payload["attributes"] = attributes
    if include_passport and pack.passport is not None:
        passport = pack.passport.model_dump(mode="json")
        if not passport.get("stage_status"):
            passport.pop("stage_status", None)
        payload["passport"] = passport
    return payload


def iter_hits(
    client: Any,
    *,
    index: str,
    text_fields: Sequence[str],
    limit: int,
    batch_size: int,
) -> Iterator[dict[str, Any]]:
    remaining = limit
    offset = 0
    source_fields = sorted(set(text_fields))
    while remaining > 0:
        size = min(batch_size, remaining)
        body = {
            "query": {"match_all": {}},
            "from": offset,
            "size": size,
            "sort": ["_doc"],
            "_source": source_fields,
        }
        response = client.search(index=index, body=body)
        hits = list((response or {}).get("hits", {}).get("hits", []) or [])
        if not hits:
            break
        for hit in hits:
            yield hit
            remaining -= 1
            if remaining <= 0:
                break
        if len(hits) < size:
            break
        offset += len(hits)


def iter_enrichment_previews(
    client: Any,
    config: ElasticsearchEnrichmentConfig,
) -> tuple[list[EnrichmentPreview], list[dict[str, Any]]]:
    previews: list[EnrichmentPreview] = []
    skipped: list[dict[str, Any]] = []

    for hit in iter_hits(
        client,
        index=config.index,
        text_fields=config.text_fields,
        limit=config.limit,
        batch_size=config.batch_size,
    ):
        doc_id = str(hit.get("_id", ""))
        text = compose_hit_text(hit, config.text_fields)
        if not text:
            skipped.append({"_id": doc_id, "reason": "missing_text_fields"})
            continue
        payload = build_enrichment_payload(
            text,
            profile=config.profile,
            include_passport=config.include_passport,
            include_evidence=config.include_evidence,
        )
        previews.append(
            EnrichmentPreview(
                doc_id=doc_id,
                index=str(hit.get("_index") or config.index),
                text_fields=config.text_fields,
                target_field=config.target_field,
                text=text,
                payload=payload,
            )
        )
    return previews, skipped


def _summary(
    config: ElasticsearchEnrichmentConfig,
    *,
    dry_run: bool,
    processed: int,
    previewed: int,
    skipped: int,
) -> dict[str, Any]:
    return {
        "dry_run": dry_run,
        "index": config.index,
        "profile": config.profile,
        "text_fields": list(config.text_fields),
        "target_field": config.target_field,
        "limit": config.limit,
        "batch_size": config.batch_size,
        "processed": processed,
        "previewed": previewed,
        "skipped": skipped,
        "include_evidence": config.include_evidence,
        "include_passport": config.include_passport,
    }


def preview_enrichment(
    client: Any,
    config: ElasticsearchEnrichmentConfig,
) -> dict[str, Any]:
    previews, skipped = iter_enrichment_previews(client, config)
    records = [preview.as_record() for preview in previews]
    summary = _summary(
        config,
        dry_run=True,
        processed=len(previews) + len(skipped),
        previewed=len(records),
        skipped=len(skipped),
    )
    return {"summary": summary, "previews": records, "skipped": skipped}


def _bulk_error_items(response: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not response or not response.get("errors"):
        return []
    errors: list[dict[str, Any]] = []
    for item in response.get("items", []) or []:
        update = item.get("update") if isinstance(item, dict) else None
        if update and update.get("error"):
            errors.append(update)
    return errors


def _call_bulk(client: Any, operations: list[dict[str, Any]]) -> dict[str, Any]:
    """Call Elasticsearch bulk API across client versions and test fakes."""
    try:
        return client.bulk(operations=operations)
    except TypeError:
        return client.bulk(body=operations)


def write_enrichment(
    client: Any,
    config: ElasticsearchEnrichmentConfig,
) -> dict[str, Any]:
    """Enrich matching documents and write partial updates with bulk API."""
    previews, skipped = iter_enrichment_previews(client, config)
    updates: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    updated = 0
    batches = 0

    for start in range(0, len(previews), config.batch_size):
        batch = previews[start : start + config.batch_size]
        if not batch:
            continue
        operations: list[dict[str, Any]] = []
        for preview in batch:
            operations.extend(preview.as_bulk_operations())
        response = _call_bulk(client, operations)
        batches += 1
        batch_errors = _bulk_error_items(response)
        errors.extend(batch_errors)
        updated += max(0, len(batch) - len(batch_errors))
        for preview in batch:
            updates.append(
                {
                    "_id": preview.doc_id,
                    "_index": preview.index,
                    "target_field": preview.target_field,
                    "canonical_values": preview.payload.get("canonical_values", []),
                    "snapshot_version": preview.payload.get("snapshot_version"),
                }
            )

    summary = _summary(
        config,
        dry_run=False,
        processed=len(previews) + len(skipped),
        previewed=0,
        skipped=len(skipped),
    )
    summary.update(
        {
            "write_mode": "bulk_update",
            "enriched": len(previews),
            "updated": updated,
            "failed": len(errors),
            "bulk_batches": batches,
        }
    )
    return {
        "summary": summary,
        "updates": updates,
        "skipped": skipped,
        "errors": errors,
    }
