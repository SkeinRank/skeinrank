"""Elasticsearch evidence connector for the OpenRouter alias scout example.

Patch 41E keeps the connector dependency-light and optional. It queries an
operator-configured Elasticsearch/OpenSearch-compatible endpoint, normalizes hits
into the local evidence-record shape, and then reuses the deterministic evidence
sampler from Patch 40I. It never mutates Elasticsearch, SkeinRank, snapshots, or
proposal state.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

try:  # pragma: no cover - import style depends on how the example is executed.
    from .candidate_discovery import AliasCandidate
    from .evidence_sampler import (
        EvidenceSamplerConfig,
        build_candidate_evidence_pack,
        sample_evidence_windows,
    )
except ImportError:  # pragma: no cover
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from candidate_discovery import AliasCandidate
    from evidence_sampler import (
        EvidenceSamplerConfig,
        build_candidate_evidence_pack,
        sample_evidence_windows,
    )

JsonDict = dict[str, Any]
ElasticsearchTransport = Callable[[str, str, Mapping[str, Any] | None], Any]

DEFAULT_TEXT_FIELDS = ("title", "text", "message", "content", "body", "snippet")
DEFAULT_SOURCE_ID_FIELDS = ("id", "doc_id", "document_id", "trace_id")


class ElasticsearchSourceError(RuntimeError):
    """Base error raised by the optional Elasticsearch evidence connector."""


class ElasticsearchSourceApiError(ElasticsearchSourceError):
    """Raised when Elasticsearch returns a non-2xx response."""

    def __init__(self, status_code: int, detail: Any) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"Elasticsearch returned {status_code}: {detail}")


@dataclass(frozen=True)
class ElasticsearchSourceConfig:
    """Settings for optional Elasticsearch evidence sampling."""

    url: str = "http://127.0.0.1:9200"
    index: str = "skeinrank-agent-evidence"
    text_fields: tuple[str, ...] = DEFAULT_TEXT_FIELDS
    source_id_fields: tuple[str, ...] = DEFAULT_SOURCE_ID_FIELDS
    max_docs_per_candidate: int = 5
    request_timeout_seconds: float = 10.0
    api_key_env: str | None = "ELASTICSEARCH_API_KEY"
    api_key_auth_scheme: str = "ApiKey"

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any] | None) -> "ElasticsearchSourceConfig":
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
                raise ValueError(f"elasticsearch_source.{name} must be a string list")
            normalized = tuple(item.strip() for item in value if item.strip())
            return normalized or default

        return cls(
            url=str(raw.get("url", cls.url)),
            index=str(raw.get("index", cls.index)),
            text_fields=_string_tuple("text_fields", DEFAULT_TEXT_FIELDS),
            source_id_fields=_string_tuple(
                "source_id_fields", DEFAULT_SOURCE_ID_FIELDS
            ),
            max_docs_per_candidate=int(
                raw.get("max_docs_per_candidate", cls.max_docs_per_candidate)
            ),
            request_timeout_seconds=float(
                raw.get("request_timeout_seconds", cls.request_timeout_seconds)
            ),
            api_key_env=raw.get("api_key_env", cls.api_key_env),
            api_key_auth_scheme=str(
                raw.get("api_key_auth_scheme", cls.api_key_auth_scheme)
            ),
        )

    def with_overrides(
        self,
        *,
        url: str | None = None,
        index: str | None = None,
        text_fields: Sequence[str] | None = None,
        max_docs_per_candidate: int | None = None,
        api_key_env: str | None = None,
    ) -> "ElasticsearchSourceConfig":
        """Return a copy with CLI override values applied."""

        return ElasticsearchSourceConfig(
            url=url or self.url,
            index=index or self.index,
            text_fields=tuple(text_fields) if text_fields else self.text_fields,
            source_id_fields=self.source_id_fields,
            max_docs_per_candidate=(
                max_docs_per_candidate
                if max_docs_per_candidate is not None
                else self.max_docs_per_candidate
            ),
            request_timeout_seconds=self.request_timeout_seconds,
            api_key_env=api_key_env if api_key_env is not None else self.api_key_env,
            api_key_auth_scheme=self.api_key_auth_scheme,
        )

    def api_key(self) -> str | None:
        """Read the optional Elasticsearch API key from the environment."""

        return os.getenv(self.api_key_env) if self.api_key_env else None

    def to_plan(self) -> JsonDict:
        """Return a redacted, network-free plan for this connector."""

        api_key_available = bool(self.api_key())
        return {
            "schema_version": "skeinrank.agent_elasticsearch_evidence_plan.v1",
            "runner": "openrouter_alias_scout",
            "elasticsearch_calls": False,
            "url": self.url,
            "index": self.index,
            "text_fields": list(self.text_fields),
            "source_id_fields": list(self.source_id_fields),
            "max_docs_per_candidate": self.max_docs_per_candidate,
            "api_key_env": self.api_key_env,
            "api_key_available": api_key_available,
            "safety": {
                "readonly": True,
                "mutating_elasticsearch_calls": False,
                "skeinrank_api_calls": False,
                "openrouter_calls": False,
                "runtime_mutation_enabled": False,
            },
            "next_steps": [
                "Run --sample-evidence-from-elasticsearch against a small index.",
                "Inspect evidence windows before live LLM review.",
                "Keep proposal submission behind validation and review policies.",
            ],
        }


@dataclass(frozen=True)
class ElasticsearchSourceClient:
    """Small stdlib Elasticsearch/OpenSearch-compatible client."""

    config: ElasticsearchSourceConfig
    transport: ElasticsearchTransport | None = None

    def search_candidate(self, candidate_alias: str) -> JsonDict:
        """Search configured text fields for one candidate alias."""

        payload = build_elasticsearch_search_payload(
            candidate_alias,
            text_fields=self.config.text_fields,
            size=self.config.max_docs_per_candidate,
        )
        return self.request("POST", f"/{quote(self.config.index)}/_search", payload)

    def request(
        self, method: str, path: str, payload: Mapping[str, Any] | None = None
    ) -> Any:
        """Execute an Elasticsearch request and decode JSON responses."""

        if self.transport is not None:
            return self.transport(method.upper(), path, payload)

        url = f"{self.config.url.rstrip('/')}{path}"
        headers = {"Accept": "application/json"}
        data: bytes | None = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(payload).encode("utf-8")
        api_key = self.config.api_key()
        if api_key:
            headers["Authorization"] = f"{self.config.api_key_auth_scheme} {api_key}"

        request = Request(url, data=data, headers=headers, method=method.upper())
        try:
            # The URL is operator-configured for this local deployment connector.
            with urlopen(  # noqa: S310
                request, timeout=self.config.request_timeout_seconds
            ) as response:
                body = response.read().decode("utf-8")
                return json.loads(body) if body else None
        except HTTPError as exc:
            body = exc.read().decode("utf-8")
            try:
                detail: Any = json.loads(body)
            except json.JSONDecodeError:
                detail = body or exc.reason
            raise ElasticsearchSourceApiError(exc.code, detail) from exc
        except URLError as exc:
            raise ElasticsearchSourceError(
                f"Could not reach Elasticsearch evidence source: {exc}"
            ) from exc


def build_elasticsearch_search_payload(
    candidate_alias: str, *, text_fields: Sequence[str], size: int
) -> JsonDict:
    """Build a deterministic Elasticsearch _search payload for one candidate."""

    fields = [field for field in text_fields if field]
    if not fields:
        raise ValueError("At least one Elasticsearch text field is required")
    return {
        "size": max(int(size), 1),
        "track_total_hits": False,
        "query": {
            "multi_match": {
                "query": candidate_alias,
                "fields": fields,
                "type": "best_fields",
                "operator": "or",
            }
        },
        "_source": True,
    }


def elasticsearch_hits_to_records(
    response: Mapping[str, Any], *, config: ElasticsearchSourceConfig
) -> list[JsonDict]:
    """Normalize Elasticsearch hits into evidence records."""

    hits_value = response.get("hits", {})
    if not isinstance(hits_value, Mapping):
        return []
    raw_hits = hits_value.get("hits", [])
    if not isinstance(raw_hits, list):
        return []

    records: list[JsonDict] = []
    for rank, hit in enumerate(raw_hits, 1):
        if not isinstance(hit, Mapping):
            continue
        source = hit.get("_source")
        if not isinstance(source, Mapping):
            source = {}
        record = _source_to_record(source, hit=hit, rank=rank, config=config)
        if _record_has_text(record, config.text_fields):
            records.append(record)
    return records


def build_elasticsearch_evidence_report(
    candidates: Sequence[AliasCandidate],
    *,
    client: ElasticsearchSourceClient,
    source_config: ElasticsearchSourceConfig,
    evidence_config: EvidenceSamplerConfig,
    binding_id: int | None = None,
    profile_name: str | None = None,
) -> JsonDict:
    """Search Elasticsearch for candidates and return sampled evidence windows."""

    samples: list[JsonDict] = []
    total_records = 0
    total_windows = 0
    errors: list[JsonDict] = []

    for candidate in candidates:
        try:
            response = client.search_candidate(candidate.surface)
            records = elasticsearch_hits_to_records(response, config=source_config)
        except ElasticsearchSourceError as exc:
            records = []
            errors.append({"candidate_alias": candidate.surface, "error": str(exc)})
        windows = sample_evidence_windows(
            candidate.surface, records, config=evidence_config
        )
        pack = build_candidate_evidence_pack(
            candidate,
            windows,
            binding_id=binding_id,
            profile_name=profile_name,
        )
        total_records += len(records)
        total_windows += len(windows)
        samples.append(
            {
                "candidate_alias": candidate.surface,
                "records_returned": len(records),
                "windows_found": len(windows),
                "total_chars": sum(len(window.text) for window in windows),
                "evidence_windows": [window.to_dict() for window in windows],
                "candidate_pack": pack,
            }
        )

    return {
        "schema_version": "skeinrank.agent_elasticsearch_evidence_sampling.v1",
        "runner": "openrouter_alias_scout",
        "llm_enabled": False,
        "openrouter_calls": False,
        "skeinrank_api_calls": False,
        "elasticsearch_calls": True,
        "readonly": True,
        "binding_id": binding_id,
        "profile_name": profile_name,
        "candidate_count": len(candidates),
        "records_returned": total_records,
        "total_evidence_windows": total_windows,
        "config": {
            "url": source_config.url,
            "index": source_config.index,
            "text_fields": list(source_config.text_fields),
            "max_docs_per_candidate": source_config.max_docs_per_candidate,
            "evidence_max_windows": evidence_config.max_windows,
            "evidence_max_total_chars": evidence_config.max_total_chars,
        },
        "samples": samples,
        "errors": errors,
        "safety": {
            "mutating_elasticsearch_calls": False,
            "runtime_mutation_enabled": False,
            "snapshot_publish_enabled": False,
        },
    }


def collect_elasticsearch_evidence_records(
    candidates: Sequence[AliasCandidate],
    *,
    client: ElasticsearchSourceClient,
    source_config: ElasticsearchSourceConfig,
) -> list[JsonDict]:
    """Collect normalized evidence records for JSONL export/debugging."""

    records: list[JsonDict] = []
    seen_ids: set[str] = set()
    for candidate in candidates:
        response = client.search_candidate(candidate.surface)
        for record in elasticsearch_hits_to_records(response, config=source_config):
            record_id = str(record.get("id") or record.get("doc_id") or "")
            key = f"{record.get('index')}:{record_id}"
            if key in seen_ids:
                continue
            seen_ids.add(key)
            records.append(record)
    return records


def _source_to_record(
    source: Mapping[str, Any],
    *,
    hit: Mapping[str, Any],
    rank: int,
    config: ElasticsearchSourceConfig,
) -> JsonDict:
    record: JsonDict = dict(source)
    source_id = _source_id(source, hit, config)
    record.setdefault("id", source_id)
    record["source_type"] = "elasticsearch"
    record["index"] = hit.get("_index")
    record["score"] = hit.get("_score")
    record["rank"] = rank
    return record


def _source_id(
    source: Mapping[str, Any], hit: Mapping[str, Any], config: ElasticsearchSourceConfig
) -> str:
    for field_name in config.source_id_fields:
        value = source.get(field_name)
        if value is not None and str(value).strip():
            return str(value).strip()
    hit_id = hit.get("_id")
    if hit_id is not None and str(hit_id).strip():
        return str(hit_id).strip()
    return f"hit-{hit.get('_index', 'unknown')}-{hit.get('_score', '0')}"


def _record_has_text(record: Mapping[str, Any], text_fields: Sequence[str]) -> bool:
    for field_name in text_fields:
        value = record.get(field_name)
        if isinstance(value, str) and value.strip():
            return True
    return False


__all__ = [
    "ElasticsearchSourceApiError",
    "ElasticsearchSourceClient",
    "ElasticsearchSourceConfig",
    "ElasticsearchSourceError",
    "build_elasticsearch_evidence_report",
    "build_elasticsearch_search_payload",
    "collect_elasticsearch_evidence_records",
    "elasticsearch_hits_to_records",
]
