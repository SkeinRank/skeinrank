from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from .types import AttributeSlot

AttributeProfilePayload = dict[str, Any]
AttributeProfileInput = str | Mapping[str, Any]


def _string_list(values: Iterable[str] | str) -> list[str]:
    if isinstance(values, str):
        values = [values]
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        out.append(text)
        seen.add(text)
    return out


def _slot_value(slot: AttributeSlot | str) -> str:
    return AttributeSlot(str(slot)).value


def build_attribute_profile(
    *,
    aliases: Mapping[str, Iterable[str] | str],
    slots: Mapping[str, AttributeSlot | str],
    profile_id: str = "custom",
    description: str = "Custom SkeinRank terminology profile.",
    snapshot_version: str | None = None,
    snapshot_source: str = "python",
    alias_matcher_backend: str = "aho_corasick",
    total_limit: int = 20,
    slot_limits: Mapping[AttributeSlot | str, int] | None = None,
    global_stopwords: Iterable[str] | None = None,
    slot_stopwords: Mapping[AttributeSlot | str, Iterable[str]] | None = None,
    regex_rules: Iterable[Mapping[str, Any]] | None = None,
    default_confidence: float = 0.95,
    include_canonical_as_alias: bool = True,
) -> AttributeProfilePayload:
    """Build an in-memory terminology profile from Python dictionaries.

    This is the quickest way to bring your own company terminology without
    writing the full JSON snapshot by hand.
    """
    profile_id = profile_id.strip()
    if not profile_id:
        raise ValueError("profile_id must not be empty")
    if total_limit < 1:
        raise ValueError("total_limit must be >= 1")
    if not aliases:
        raise ValueError("aliases must not be empty")

    alias_rows: list[dict[str, Any]] = []
    for canonical, raw_aliases in aliases.items():
        canonical_value = str(canonical).strip()
        if not canonical_value:
            raise ValueError("canonical values must not be empty")
        if canonical_value not in slots:
            raise ValueError(f"Missing slot for canonical value: {canonical_value}")
        slot = _slot_value(slots[canonical_value])
        values = _string_list(raw_aliases)
        if include_canonical_as_alias:
            values = _string_list([canonical_value, *values])
        if not values:
            raise ValueError(
                f"No aliases provided for canonical value: {canonical_value}"
            )
        for alias in values:
            alias_rows.append(
                {
                    "alias": alias,
                    "canonical": canonical_value,
                    "slot": slot,
                    "confidence": float(default_confidence),
                }
            )

    slot_limits_payload = {
        _slot_value(slot): int(limit) for slot, limit in (slot_limits or {}).items()
    }
    slot_stopwords_payload = {
        _slot_value(slot): _string_list(values)
        for slot, values in (slot_stopwords or {}).items()
    }

    return {
        "profile_id": profile_id,
        "description": description,
        "total_limit": int(total_limit),
        "slot_limits": slot_limits_payload,
        "global_stopwords": _string_list(global_stopwords or []),
        "slot_stopwords": slot_stopwords_payload,
        "aliases": alias_rows,
        "regex_rules": [dict(item) for item in (regex_rules or [])],
        "snapshot": {
            "version": snapshot_version or f"{profile_id}@local",
            "source": snapshot_source,
            "description": f"Runtime profile snapshot for {profile_id}.",
        },
        "alias_matcher": {"backend": alias_matcher_backend},
    }


def build_attribute_profile_template(
    *,
    profile_id: str = "company_terms",
    description: str | None = None,
    snapshot_version: str | None = None,
    alias_matcher_backend: str = "aho_corasick",
) -> AttributeProfilePayload:
    """Build a starter terminology profile in the grouped alias format.

    The template is intentionally small but valid: users can edit it, validate it,
    and pass it to ``--profile-file`` without knowing the full snapshot schema.
    """
    profile_id = profile_id.strip()
    if not profile_id:
        raise ValueError("profile_id must not be empty")

    resolved_description = description or "Company terminology profile."
    resolved_snapshot_version = snapshot_version or f"{profile_id}@v1"
    return {
        "profile_id": profile_id,
        "description": resolved_description,
        "total_limit": 20,
        "slot_limits": {},
        "global_stopwords": [],
        "slot_stopwords": {},
        "aliases": [
            {
                "slot": "TOOL",
                "canonical": "kubernetes",
                "aliases": ["k8s", "kube", "kuber"],
                "confidence": 0.95,
            },
            {
                "slot": "DB",
                "canonical": "postgresql",
                "aliases": ["pg", "postgres", "psql"],
                "confidence": 0.95,
            },
        ],
        "regex_rules": [],
        "snapshot": {
            "version": resolved_snapshot_version,
            "source": "file",
            "description": f"Starter profile snapshot for {profile_id}.",
        },
        "alias_matcher": {"backend": alias_matcher_backend},
    }


def write_attribute_profile_template(
    path: str | Path,
    *,
    profile_id: str | None = None,
    description: str | None = None,
    snapshot_version: str | None = None,
    overwrite: bool = False,
) -> Path:
    """Write a starter terminology profile to ``path``.

    Existing files are not overwritten unless ``overwrite=True``.
    """
    profile_path = Path(path)
    if profile_path.exists() and not overwrite:
        raise FileExistsError(
            f"Profile already exists: {profile_path}. Use overwrite=True to replace it."
        )
    resolved_profile_id = profile_id or profile_path.stem or "company_terms"
    payload = build_attribute_profile_template(
        profile_id=resolved_profile_id,
        description=description,
        snapshot_version=snapshot_version,
    )
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return profile_path


def load_attribute_profile(path: str | Path) -> AttributeProfilePayload:
    """Load a terminology profile snapshot from JSON."""
    profile_path = Path(path)
    payload = json.loads(profile_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object in profile file: {profile_path}")
    if "profile_id" not in payload:
        raise ValueError(f"Profile file is missing profile_id: {profile_path}")
    if "aliases" not in payload:
        raise ValueError(f"Profile file is missing aliases: {profile_path}")
    return payload
