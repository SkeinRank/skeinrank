from __future__ import annotations

import json
from importlib import resources
from typing import Any

from .alias_map import AliasMap
from .model_adapters import AttributeModelAdapters, ModelCandidate
from .normalize import normalize_text, normalize_value
from .passport import build_passport
from .rules import RuleSet, should_filter
from .types import (
    AttributeEvidence,
    AttributePack,
    AttributeProfile,
    AttributeSlot,
    AttributeSnapshot,
    AttributeStageStatus,
    AttributeTrace,
    ExtractedAttribute,
)

_DEFAULT_PROFILE = "default_it"
_STAGE_ORDER = ("gliner", "e5", "keybert")


def list_attribute_profiles() -> list[str]:
    root = resources.files("skeinrank.attributes.config")
    return sorted(path.stem for path in root.iterdir() if path.name.endswith(".json"))


def _load_profile_payload(profile: str) -> dict[str, Any]:
    try:
        text = (
            resources.files("skeinrank.attributes.config")
            .joinpath(f"{profile}.json")
            .read_text(encoding="utf-8")
        )
    except FileNotFoundError as exc:
        raise ValueError(f"Unknown attribute profile: {profile}") from exc
    return json.loads(text)


def _snapshot_from_payload(payload: dict[str, Any]) -> AttributeSnapshot:
    snapshot_payload = payload.get("snapshot") or {}
    profile_id = str(payload["profile_id"])
    version = str(snapshot_payload.get("version") or f"{profile_id}@local")
    return AttributeSnapshot(
        version=version,
        source=str(snapshot_payload.get("source", "file")),
        created_at=snapshot_payload.get("created_at"),
        description=snapshot_payload.get("description"),
    )


def _alias_matcher_backend_from_payload(payload: dict[str, Any]) -> str:
    cfg = payload.get("alias_matcher") or {}
    return str(cfg.get("backend", "simple"))


def get_attribute_profile(profile: str = _DEFAULT_PROFILE) -> AttributeProfile:
    payload = _load_profile_payload(profile)
    return AttributeProfile(
        profile_id=str(payload["profile_id"]),
        description=str(payload.get("description", "")),
        total_limit=int(payload.get("total_limit", 10)),
        slot_limits={
            AttributeSlot(k): int(v) for k, v in payload.get("slot_limits", {}).items()
        },
        snapshot=_snapshot_from_payload(payload),
        alias_matcher_backend=_alias_matcher_backend_from_payload(payload),
    )


def _stage_enabled(payload: dict[str, Any], stage: str, explicit: bool | None) -> bool:
    if explicit is not None:
        return explicit
    model_stages = payload.get("model_stages", {})
    stage_cfg = model_stages.get(stage, {})
    return bool(stage_cfg.get("enabled", False))


def _build_model_candidates(
    *, adapter_output: list[ModelCandidate], alias_map: AliasMap
) -> list[tuple[AttributeTrace, AttributeEvidence]]:
    candidates: list[tuple[AttributeTrace, AttributeEvidence]] = []
    for item in adapter_output:
        canonical_value, canonicalized_from, alias_confidence = (
            alias_map.canonicalize_value(item.value, slot=item.slot)
        )
        confidence = (
            item.confidence
            if alias_confidence is None
            else max(item.confidence, alias_confidence)
        )
        trace = AttributeTrace(
            slot=item.slot,
            value=normalize_value(canonical_value),
            source=item.source,
            matched_text=item.matched_text,
            canonicalized_from=canonicalized_from,
            confidence=confidence,
        )
        evidence = AttributeEvidence(
            source=item.source,
            matched_text=item.matched_text,
        )
        candidates.append((trace, evidence))
    return candidates


def extract_attributes(
    text: str,
    *,
    profile: str = _DEFAULT_PROFILE,
    debug: bool = False,
    adapters: AttributeModelAdapters | None = None,
    use_gliner: bool | None = None,
    use_e5: bool | None = None,
    use_keybert: bool | None = None,
) -> AttributePack:
    payload = _load_profile_payload(profile)
    profile_obj = get_attribute_profile(profile)

    normalized_text = normalize_text(text)
    alias_map = AliasMap.from_profile(
        payload.get("aliases", []),
        matcher_backend=profile_obj.alias_matcher_backend,
    )
    rule_set = RuleSet.from_profile(payload.get("regex_rules", []))
    global_stopwords = {normalize_text(x) for x in payload.get("global_stopwords", [])}
    slot_stopwords = {
        slot: {normalize_text(item) for item in items}
        for slot, items in payload.get("slot_stopwords", {}).items()
    }

    proposed: list[AttributeTrace] = []
    accepted: list[AttributeTrace] = []
    filtered_out: list[AttributeTrace] = []
    warnings: list[str] = []
    final_attributes: list[ExtractedAttribute] = []
    seen: set[tuple[AttributeSlot, str]] = set()
    per_slot_counts: dict[AttributeSlot, int] = {}
    stage_status: list[AttributeStageStatus] = []

    candidates: list[tuple[AttributeTrace, AttributeEvidence]] = []

    for match in alias_map.find(normalized_text):
        trace = AttributeTrace(
            slot=match.slot,
            value=match.canonical,
            source="alias",
            matched_text=match.matched_text,
            canonicalized_from=match.alias,
            confidence=match.confidence,
        )
        evidence = AttributeEvidence(
            source="alias",
            matched_text=match.matched_text,
            start=match.start,
            end=match.end,
        )
        proposed.append(trace)
        candidates.append((trace, evidence))

    for match in rule_set.find(normalized_text):
        trace = AttributeTrace(
            slot=match.slot,
            value=match.canonical,
            source="regex",
            matched_text=match.matched_text,
            rule_id=match.rule_id,
            confidence=match.confidence,
        )
        evidence = AttributeEvidence(
            source="regex",
            matched_text=match.matched_text,
            start=match.start,
            end=match.end,
            rule_id=match.rule_id,
        )
        proposed.append(trace)
        candidates.append((trace, evidence))

    adapters = adapters or AttributeModelAdapters()
    stage_overrides = {
        "gliner": use_gliner,
        "e5": use_e5,
        "keybert": use_keybert,
    }

    for stage in _STAGE_ORDER:
        enabled = _stage_enabled(payload, stage, stage_overrides[stage])
        adapter = getattr(adapters, stage)
        status = AttributeStageStatus(
            stage=stage, enabled=enabled, available=adapter is not None
        )
        if not enabled:
            # Keep disabled optional model stages out of the public passport.
            # The v1 runtime is rule/alias-based; model stages should only be
            # reported when a caller explicitly enables them or when they emit
            # a warning/execution trace.
            continue
        if adapter is None:
            warning = f"{stage}_adapter_unavailable"
            warnings.append(warning)
            status.warning = warning
            stage_status.append(status)
            continue
        try:
            adapter_output = adapter.extract(text, profile=profile_obj)
            status.executed = True
            status.emitted_candidates = len(adapter_output)
            status.available = True
            model_candidates = _build_model_candidates(
                adapter_output=adapter_output, alias_map=alias_map
            )
            for trace, evidence in model_candidates:
                proposed.append(trace)
                candidates.append((trace, evidence))
        except (
            Exception
        ) as exc:  # pragma: no cover - exercised in tests with a controlled stub
            warning = f"{stage}_stage_failed:{exc}"
            warnings.append(warning)
            status.warning = warning
        stage_status.append(status)

    for trace, evidence in sorted(
        candidates,
        key=lambda item: (
            -item[0].confidence,
            item[0].slot.value,
            item[0].value,
            item[0].source,
        ),
    ):
        reason = should_filter(
            slot=trace.slot,
            value=trace.value,
            global_stopwords=global_stopwords,
            slot_stopwords=slot_stopwords,
        )
        if reason is not None:
            filtered_out.append(trace.model_copy(update={"reason": reason}))
            continue

        key = (trace.slot, trace.value)
        if key in seen:
            filtered_out.append(trace.model_copy(update={"reason": "duplicate"}))
            continue

        slot_limit = profile_obj.slot_limits.get(trace.slot)
        current_slot_count = per_slot_counts.get(trace.slot, 0)
        if slot_limit is not None and current_slot_count >= slot_limit:
            filtered_out.append(
                trace.model_copy(update={"reason": f"slot_limit:{trace.slot.value}"})
            )
            continue

        if len(final_attributes) >= profile_obj.total_limit:
            filtered_out.append(trace.model_copy(update={"reason": "total_limit"}))
            warnings.append("attribute_total_limit_reached")
            continue

        seen.add(key)
        per_slot_counts[trace.slot] = current_slot_count + 1
        accepted.append(trace)
        final_attributes.append(
            ExtractedAttribute(
                slot=trace.slot,
                value=trace.value,
                source=trace.source,
                confidence=trace.confidence,
                evidences=[evidence],
            )
        )

    return AttributePack(
        text=text,
        profile_id=profile_obj.profile_id,
        snapshot=profile_obj.snapshot,
        alias_matcher_backend=alias_map.matcher_backend,
        attributes=final_attributes,
        passport=build_passport(
            profile_id=profile_obj.profile_id,
            normalized_text=normalized_text,
            proposed=proposed,
            accepted=accepted,
            filtered_out=filtered_out,
            warnings=warnings,
            stage_status=stage_status,
            snapshot=profile_obj.snapshot,
            alias_matcher_backend=alias_map.matcher_backend,
        )
        if debug
        else None,
    )
