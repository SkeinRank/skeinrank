"""Small Elasticsearch discovery client used by governance API endpoints."""

from __future__ import annotations

import base64
import json
import socket
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from .config import GovernanceApiConfig

TEXT_FIELD_TYPES = {"text", "match_only_text"}
DISCRIMINATOR_FIELD_TYPES = {
    "keyword",
    "constant_keyword",
    "wildcard",
    "boolean",
    "byte",
    "short",
    "integer",
    "long",
    "unsigned_long",
    "date",
    "ip",
}


class ElasticsearchDiscoveryError(RuntimeError):
    """Raised when Elasticsearch discovery fails."""


@dataclass(frozen=True)
class ElasticsearchField:
    """Flattened Elasticsearch mapping field metadata."""

    name: str
    type: str
    is_text_candidate: bool
    is_discriminator_candidate: bool


class ElasticsearchDiscoveryClient:
    """Minimal stdlib Elasticsearch client for connection and mapping discovery."""

    def __init__(self, config: GovernanceApiConfig) -> None:
        self.url = (config.elasticsearch_url or "").rstrip("/")
        self.username = config.elasticsearch_username
        self.password = config.elasticsearch_password
        self.api_key = config.elasticsearch_api_key
        self.timeout_seconds = config.elasticsearch_timeout_seconds

    @property
    def is_configured(self) -> bool:
        return bool(self.url)

    def cluster_info(self) -> dict[str, Any]:
        return self._get_json("/")

    def list_indices(self) -> list[dict[str, Any]]:
        payload = self._get_json(
            "/_cat/indices?format=json&h=index,health,status,docs.count"
        )
        if not isinstance(payload, list):
            raise ElasticsearchDiscoveryError(
                "Unexpected Elasticsearch indices response"
            )
        indices: list[dict[str, Any]] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            name = str(item.get("index") or "").strip()
            if not name:
                continue
            docs_count = item.get("docs.count")
            indices.append(
                {
                    "name": name,
                    "health": item.get("health"),
                    "status": item.get("status"),
                    "docs_count": _parse_optional_int(docs_count),
                }
            )
        return sorted(indices, key=lambda index: index["name"])

    def index_fields(self, index_name: str) -> list[ElasticsearchField]:
        safe_index_name = quote(index_name, safe="")
        payload = self._get_json(f"/{safe_index_name}/_mapping")
        return extract_mapping_fields(payload, index_name=index_name)

    def _get_json(self, path: str) -> Any:
        if not self.url:
            raise ElasticsearchDiscoveryError("Elasticsearch URL is not configured")

        request = Request(f"{self.url}{path}", headers=self._headers())
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = _read_error_body(exc)
            raise ElasticsearchDiscoveryError(
                detail or f"Elasticsearch request failed with HTTP {exc.code}"
            ) from exc
        except (URLError, TimeoutError, socket.timeout) as exc:
            raise ElasticsearchDiscoveryError(
                f"Elasticsearch request failed: {exc}"
            ) from exc
        except json.JSONDecodeError as exc:
            raise ElasticsearchDiscoveryError(
                "Elasticsearch returned invalid JSON"
            ) from exc

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"ApiKey {self.api_key}"
        elif self.username and self.password:
            token = base64.b64encode(
                f"{self.username}:{self.password}".encode()
            ).decode()
            headers["Authorization"] = f"Basic {token}"
        return headers


def extract_mapping_fields(
    payload: Any, *, index_name: str | None = None
) -> list[ElasticsearchField]:
    """Flatten usable fields from an Elasticsearch mapping response."""

    mappings = _mapping_root(payload, index_name=index_name)
    properties = mappings.get("properties", {}) if isinstance(mappings, dict) else {}
    fields: list[ElasticsearchField] = []
    _collect_fields(properties, prefix="", output=fields)
    return sorted(fields, key=lambda field: field.name)


def _mapping_root(payload: Any, *, index_name: str | None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    if "mappings" in payload and isinstance(payload["mappings"], dict):
        return payload["mappings"]
    if index_name and isinstance(payload.get(index_name), dict):
        mapping = payload[index_name].get("mappings", {})
        return mapping if isinstance(mapping, dict) else {}
    if len(payload) == 1:
        value = next(iter(payload.values()))
        if isinstance(value, dict) and isinstance(value.get("mappings"), dict):
            return value["mappings"]
    return {}


def _collect_fields(
    properties: Any,
    *,
    prefix: str,
    output: list[ElasticsearchField],
) -> None:
    if not isinstance(properties, dict):
        return

    for field_name, definition in properties.items():
        if not isinstance(definition, dict):
            continue
        full_name = f"{prefix}.{field_name}" if prefix else str(field_name)
        field_type = str(definition.get("type") or "object")

        if "type" in definition:
            output.append(
                ElasticsearchField(
                    name=full_name,
                    type=field_type,
                    is_text_candidate=field_type in TEXT_FIELD_TYPES,
                    is_discriminator_candidate=field_type in DISCRIMINATOR_FIELD_TYPES,
                )
            )

        sub_properties = definition.get("properties")
        if isinstance(sub_properties, dict):
            _collect_fields(sub_properties, prefix=full_name, output=output)

        multi_fields = definition.get("fields")
        if isinstance(multi_fields, dict):
            _collect_fields(multi_fields, prefix=full_name, output=output)


def _parse_optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(str(value).replace(",", ""))
    except ValueError:
        return None


def _read_error_body(error: HTTPError) -> str | None:
    try:
        payload = json.loads(error.read().decode("utf-8"))
    except Exception:
        return None
    if isinstance(payload, dict):
        error_body = payload.get("error")
        if isinstance(error_body, dict):
            reason = error_body.get("reason")
            if isinstance(reason, str):
                return reason
        if isinstance(error_body, str):
            return error_body
    return None
