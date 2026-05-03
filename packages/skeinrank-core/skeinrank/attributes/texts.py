from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from .pipeline import extract_attributes
from .profiles import AttributeProfileInput
from .types import AttributePack

TextRecordInput = str | Mapping[str, Any]
EnrichedTextRecord = dict[str, Any]


def _compact_pack_payload(
    pack: AttributePack,
    *,
    include_attributes: bool = False,
    include_passport: bool = False,
) -> dict[str, Any]:
    attributes = [item.model_dump(mode="json") for item in pack.attributes]
    canonical_values = sorted({item["value"] for item in attributes})
    slots: dict[str, list[str]] = {}
    for item in attributes:
        slot = str(item["slot"])
        value = str(item["value"])
        slots.setdefault(slot, [])
        if value not in slots[slot]:
            slots[slot].append(value)

    payload: dict[str, Any] = {
        "profile_id": pack.profile_id,
        "snapshot_version": pack.snapshot.version
        if pack.snapshot is not None
        else None,
        "alias_matcher_backend": pack.alias_matcher_backend,
        "canonical_values": canonical_values,
        "slots": {slot: sorted(values) for slot, values in sorted(slots.items())},
    }
    if include_attributes:
        payload["attributes"] = attributes
    if include_passport:
        passport = (
            pack.passport.model_dump(mode="json") if pack.passport is not None else None
        )
        if passport is not None and not passport.get("stage_status"):
            passport.pop("stage_status", None)
        payload["passport"] = passport
    return payload


def _record_text(
    record: TextRecordInput,
    *,
    index: int,
    id_field: str,
    text_field: str,
) -> tuple[str, str]:
    if isinstance(record, str):
        return str(index), record
    if text_field not in record:
        raise ValueError(f"Record at index {index} is missing text field: {text_field}")
    text = str(record.get(text_field, "") or "")
    doc_id = str(record.get(id_field, index))
    return doc_id, text


def enrich_texts(
    records: Iterable[TextRecordInput],
    *,
    profile: AttributeProfileInput = "default_it",
    id_field: str = "id",
    text_field: str = "text",
    include_text: bool = True,
    include_attributes: bool = False,
    include_passport: bool = False,
    enable_fuzzy: bool = False,
    fuzzy_threshold: float = 0.9,
    fuzzy_min_length: int = 4,
) -> list[EnrichedTextRecord]:
    """Enrich a small in-memory text corpus with canonical attributes.

    ``records`` can be an iterable of strings or dictionaries. Dictionaries are
    expected to contain ``text_field`` and may contain ``id_field``. The function
    returns compact, search-friendly dictionaries by default and can include full
    attributes/passport data when requested.
    """
    enriched: list[EnrichedTextRecord] = []
    debug = include_passport
    for index, record in enumerate(records):
        doc_id, text = _record_text(
            record,
            index=index,
            id_field=id_field,
            text_field=text_field,
        )
        pack = extract_attributes(
            text,
            profile=profile,
            debug=debug,
            enable_fuzzy=enable_fuzzy,
            fuzzy_threshold=fuzzy_threshold,
            fuzzy_min_length=fuzzy_min_length,
        )
        payload = _compact_pack_payload(
            pack,
            include_attributes=include_attributes,
            include_passport=include_passport,
        )
        row: EnrichedTextRecord = {"id": doc_id}
        if include_text:
            row["text"] = text
        row.update(payload)
        enriched.append(row)
    return enriched
