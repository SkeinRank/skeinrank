"""Shared dictionary import/export specification helpers."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

DICTIONARY_SCHEMA_VERSION = "skeinrank.dictionary.v1"
SUPPORTED_DICTIONARY_SCHEMA_VERSIONS = frozenset({DICTIONARY_SCHEMA_VERSION})
YAML_SUFFIXES = frozenset({".yaml", ".yml"})


def resolve_dictionary_schema_version(payload: Mapping[str, Any]) -> str:
    """Return the payload schema version, defaulting legacy payloads to v1."""

    raw_version = payload.get("schema_version")
    if raw_version is None or str(raw_version).strip() == "":
        return DICTIONARY_SCHEMA_VERSION
    return str(raw_version).strip()


def is_supported_dictionary_schema_version(payload: Mapping[str, Any]) -> bool:
    """Return whether the payload declares a supported dictionary schema version."""

    return (
        resolve_dictionary_schema_version(payload)
        in SUPPORTED_DICTIONARY_SCHEMA_VERSIONS
    )


def load_mapping_document(path: str) -> dict[str, Any]:
    """Load a dictionary document from JSON or YAML.

    JSON remains the canonical API/runtime interchange format. YAML is supported as
    a human-editable input format for CLI/GitOps files when PyYAML is available.
    """

    raw = Path(path).read_text(encoding="utf-8")
    loaded = _load_raw_mapping(raw, source=path)
    return loaded


def _load_raw_mapping(raw: str, *, source: str) -> dict[str, Any]:
    suffix = Path(source).suffix.lower()
    if suffix in YAML_SUFFIXES:
        loaded = _load_yaml(raw, source=source)
    else:
        import json

        try:
            loaded = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in {source}: {exc}") from exc
    if not isinstance(loaded, dict):
        raise ValueError("Dictionary document root must be an object")
    return loaded


def _load_yaml(raw: str, *, source: str) -> Any:
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise ValueError(
            "YAML dictionary input requires PyYAML to be installed. "
            "Use JSON or install the API with uvicorn[standard]/PyYAML."
        ) from exc
    try:
        return yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML in {source}: {exc}") from exc
