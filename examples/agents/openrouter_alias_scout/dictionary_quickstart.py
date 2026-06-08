"""Dictionary import -> binding -> snapshot quickstart helpers.

The quickstart provides a dependency-free, headless contract for the first
operator journey:

    dictionary payload -> console validate/import -> Elasticsearch binding ->
    headless snapshot artifact export

The default report is safe and validation-first. It only mutates the Governance
API when explicit flags request import/binding creation/snapshot export.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlencode

JsonDict = dict[str, Any]


class DictionaryQuickstartClient(Protocol):
    """Minimal client protocol used by the quickstart executor."""

    def request(
        self, method: str, path: str, payload: Mapping[str, Any] | None = None
    ) -> Any: ...


@dataclass(frozen=True)
class DictionaryQuickstartConfig:
    """Config for the headless onboarding quickstart."""

    artifacts_dir: Path
    profile_name: str = "infra_incidents"
    profile_description: str = "Infrastructure incident terminology demo profile."
    binding_name: str = "infra-incidents-demo"
    binding_description: str = "Demo Elasticsearch binding for infra incidents."
    index_name: str = "skeinrank_agent_demo"
    text_fields: tuple[str, ...] = ("title", "text", "query")
    target_field: str = "skeinrank.canonical_terms"
    snapshot_version: str = "quickstart-v1"
    dictionary_filename: str = "dictionary.payload.json"
    binding_filename: str = "binding.payload.json"
    snapshot_filename: str = "snapshot.artifact.json"
    apply_import_by_default: bool = False
    create_binding_by_default: bool = False
    export_snapshot_by_default: bool = False

    @classmethod
    def from_mapping(
        cls, raw: Mapping[str, Any] | None, *, base_dir: Path | None = None
    ) -> "DictionaryQuickstartConfig":
        """Create config from optional JSON config values."""

        data = dict(raw or {})
        artifacts_dir = Path(
            str(data.get("artifacts_dir", "reports/dictionary-quickstart"))
        )
        if base_dir is not None and not artifacts_dir.is_absolute():
            artifacts_dir = base_dir / artifacts_dir
        text_fields_raw = data.get("text_fields", list(cls.text_fields))
        return cls(
            artifacts_dir=artifacts_dir,
            profile_name=str(data.get("profile_name", cls.profile_name)),
            profile_description=str(
                data.get("profile_description", cls.profile_description)
            ),
            binding_name=str(data.get("binding_name", cls.binding_name)),
            binding_description=str(
                data.get("binding_description", cls.binding_description)
            ),
            index_name=str(data.get("index_name", cls.index_name)),
            text_fields=tuple(str(item) for item in text_fields_raw),
            target_field=str(data.get("target_field", cls.target_field)),
            snapshot_version=str(data.get("snapshot_version", cls.snapshot_version)),
            dictionary_filename=str(
                data.get("dictionary_filename", cls.dictionary_filename)
            ),
            binding_filename=str(data.get("binding_filename", cls.binding_filename)),
            snapshot_filename=str(data.get("snapshot_filename", cls.snapshot_filename)),
            apply_import_by_default=bool(
                data.get("apply_import_by_default", cls.apply_import_by_default)
            ),
            create_binding_by_default=bool(
                data.get("create_binding_by_default", cls.create_binding_by_default)
            ),
            export_snapshot_by_default=bool(
                data.get("export_snapshot_by_default", cls.export_snapshot_by_default)
            ),
        )

    def with_overrides(
        self,
        *,
        artifacts_dir: Path | None = None,
        index_name: str | None = None,
        profile_name: str | None = None,
    ) -> "DictionaryQuickstartConfig":
        """Return a copy with CLI overrides applied."""

        return DictionaryQuickstartConfig(
            artifacts_dir=artifacts_dir or self.artifacts_dir,
            profile_name=profile_name or self.profile_name,
            profile_description=self.profile_description,
            binding_name=self.binding_name,
            binding_description=self.binding_description,
            index_name=index_name or self.index_name,
            text_fields=self.text_fields,
            target_field=self.target_field,
            snapshot_version=self.snapshot_version,
            dictionary_filename=self.dictionary_filename,
            binding_filename=self.binding_filename,
            snapshot_filename=self.snapshot_filename,
            apply_import_by_default=self.apply_import_by_default,
            create_binding_by_default=self.create_binding_by_default,
            export_snapshot_by_default=self.export_snapshot_by_default,
        )

    @property
    def dictionary_path(self) -> Path:
        return self.artifacts_dir / self.dictionary_filename

    @property
    def binding_path(self) -> Path:
        return self.artifacts_dir / self.binding_filename

    @property
    def snapshot_path(self) -> Path:
        return self.artifacts_dir / self.snapshot_filename


def build_dictionary_quickstart_plan(config: DictionaryQuickstartConfig) -> JsonDict:
    """Return a network-free plan for the dictionary/binding/snapshot quickstart."""

    return {
        "schema_version": "skeinrank.agent_dictionary_quickstart_plan.v1",
        "runner": "openrouter_alias_scout",
        "workflow": "dictionary_quickstart",
        "profile_name": config.profile_name,
        "binding_name": config.binding_name,
        "index_name": config.index_name,
        "artifacts_dir": str(config.artifacts_dir),
        "payloads": {
            "dictionary": str(config.dictionary_path),
            "binding": str(config.binding_path),
            "snapshot": str(config.snapshot_path),
        },
        "api_flow": [
            "POST /v1/console/dictionary/validate",
            "POST /v1/console/dictionary/import (explicit flag only)",
            "POST /v1/governance/elasticsearch/bindings (explicit flag only)",
            "GET /v1/headless/snapshots/export?binding_id=<id>&source=latest (explicit flag only)",
        ],
        "safe_defaults": {
            "network_calls_in_plan": False,
            "dictionary_import_enabled_by_default": config.apply_import_by_default,
            "binding_create_enabled_by_default": config.create_binding_by_default,
            "snapshot_export_enabled_by_default": config.export_snapshot_by_default,
            "runtime_mutation_enabled": False,
            "snapshot_publish_enabled": False,
        },
        "commands": {
            "write_payloads": [
                "python",
                "examples/agents/openrouter_alias_scout/run_alias_scout.py",
                "--write-dictionary-quickstart-payloads",
            ],
            "validate_only": [
                "python",
                "examples/agents/openrouter_alias_scout/run_alias_scout.py",
                "--run-dictionary-quickstart",
            ],
            "apply_import_and_create_binding": [
                "python",
                "examples/agents/openrouter_alias_scout/run_alias_scout.py",
                "--run-dictionary-quickstart",
                "--dictionary-quickstart-apply-import",
                "--dictionary-quickstart-create-binding",
            ],
        },
        "next_steps": [
            "Start the Governance API and run migrations before live quickstart commands.",
            "Run validate-only first; apply import and create binding only after reviewing the report.",
            "Use the exported source=latest snapshot artifact for headless workers/GitOps validation.",
        ],
    }


def build_sample_dictionary_payload(config: DictionaryQuickstartConfig) -> JsonDict:
    """Return the stable console dictionary payload used by the quickstart."""

    return {
        "schema_version": "skeinrank.dictionary.v1",
        "profile_name": config.profile_name,
        "profile_description": config.profile_description,
        "create_profile": True,
        "mode": "upsert",
        "terms": [
            {
                "canonical_value": "kubernetes",
                "slot": "technology",
                "description": "Container orchestration platform used in infra incidents.",
                "tags": ["infra", "orchestration", "cloud-native"],
                "aliases": [
                    {"value": "k8s", "confidence": 0.98},
                    {"value": "kube", "confidence": 0.95},
                    {"value": "kubectl", "confidence": 0.9},
                ],
            },
            {
                "canonical_value": "postgresql",
                "slot": "database",
                "description": "PostgreSQL database and related operational runbooks.",
                "tags": ["database", "storage", "backend"],
                "aliases": [
                    {"value": "pg", "confidence": 0.95},
                    {"value": "postgres", "confidence": 0.98},
                    {"value": "psql", "confidence": 0.9},
                ],
            },
            {
                "canonical_value": "elasticsearch",
                "slot": "search_engine",
                "description": "Elasticsearch search/indexing cluster terminology.",
                "tags": ["search", "indexing"],
                "aliases": [
                    {"value": "elastic", "confidence": 0.92},
                    {"value": "es", "confidence": 0.85},
                ],
            },
            {
                "canonical_value": "rabbitmq",
                "slot": "queue",
                "description": "RabbitMQ message broker and queue incidents.",
                "tags": ["messaging", "broker"],
                "aliases": [
                    {"value": "rabbit", "confidence": 0.9},
                    {"value": "amqp", "confidence": 0.82},
                ],
            },
        ],
        "profile_stop_list": [
            {
                "value": "queue",
                "target": "alias",
                "reason": "Too generic for alias discovery.",
            },
            {
                "value": "red",
                "target": "alias",
                "reason": "Elasticsearch status adjective.",
            },
            {
                "value": "shard",
                "target": "alias",
                "reason": "Known generic search/index term.",
            },
        ],
        "global_stop_list": [],
    }


def build_sample_binding_payload(config: DictionaryQuickstartConfig) -> JsonDict:
    """Return an Elasticsearch binding payload matching the sample dictionary."""

    return {
        "name": config.binding_name,
        "profile_name": config.profile_name,
        "description": config.binding_description,
        "index_name": config.index_name,
        "text_fields": list(config.text_fields),
        "target_field": config.target_field,
        "mode": "dry_run",
        "write_strategy": "reindex_alias_swap",
        "is_enabled": True,
    }


def write_dictionary_quickstart_payloads(
    config: DictionaryQuickstartConfig,
) -> JsonDict:
    """Write dictionary and binding payloads for copy/paste or curl usage."""

    config.artifacts_dir.mkdir(parents=True, exist_ok=True)
    dictionary_payload = build_sample_dictionary_payload(config)
    binding_payload = build_sample_binding_payload(config)
    config.dictionary_path.write_text(
        json.dumps(dictionary_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    config.binding_path.write_text(
        json.dumps(binding_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {
        "schema_version": "skeinrank.agent_dictionary_quickstart_payloads.v1",
        "runner": "openrouter_alias_scout",
        "dictionary_payload_path": str(config.dictionary_path),
        "binding_payload_path": str(config.binding_path),
        "terms_total": len(dictionary_payload["terms"]),
        "aliases_total": sum(
            len(term["aliases"]) for term in dictionary_payload["terms"]
        ),
        "profile_name": config.profile_name,
        "binding_name": config.binding_name,
        "index_name": config.index_name,
        "safe_defaults": {
            "network_calls": False,
            "runtime_mutation_enabled": False,
            "snapshot_publish_enabled": False,
        },
    }


def run_dictionary_quickstart(
    *,
    config: DictionaryQuickstartConfig,
    client: DictionaryQuickstartClient,
    apply_import: bool = False,
    create_binding: bool = False,
    export_snapshot: bool = False,
    binding_id: int | None = None,
) -> JsonDict:
    """Run the live quickstart flow through existing Governance API endpoints."""

    dictionary_payload = build_sample_dictionary_payload(config)
    binding_payload = build_sample_binding_payload(config)
    results: list[JsonDict] = []

    validation = client.request(
        "POST", "/v1/console/dictionary/validate", dictionary_payload
    )
    results.append(_stage("dictionary_validate", "completed", validation))

    import_response: Any = None
    if apply_import or config.apply_import_by_default:
        import_response = client.request(
            "POST", "/v1/console/dictionary/import", dictionary_payload
        )
        results.append(_stage("dictionary_import", "completed", import_response))
    else:
        results.append(
            _stage("dictionary_import", "skipped", None, "explicit_flag_required")
        )

    binding_response: Any = None
    if create_binding or config.create_binding_by_default:
        binding_response = client.request(
            "POST", "/v1/governance/elasticsearch/bindings", binding_payload
        )
        results.append(_stage("binding_create", "completed", binding_response))
        if binding_id is None:
            binding_id = _extract_id(binding_response)
    else:
        results.append(
            _stage("binding_create", "skipped", None, "explicit_flag_required")
        )

    snapshot_response: Any = None
    should_export_snapshot = export_snapshot or config.export_snapshot_by_default
    if should_export_snapshot:
        if binding_id is None:
            results.append(
                _stage("snapshot_export", "skipped", None, "missing_binding_id")
            )
        else:
            query = urlencode(
                {
                    "binding_id": binding_id,
                    "source": "latest",
                    "snapshot_version": config.snapshot_version,
                    "description": "Dictionary quickstart source=latest snapshot artifact.",
                }
            )
            snapshot_response = client.request(
                "GET", f"/v1/headless/snapshots/export?{query}", None
            )
            results.append(_stage("snapshot_export", "completed", snapshot_response))
            config.snapshot_path.parent.mkdir(parents=True, exist_ok=True)
            config.snapshot_path.write_text(
                json.dumps(snapshot_response, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
    else:
        results.append(
            _stage("snapshot_export", "skipped", None, "explicit_flag_required")
        )

    completed = [item for item in results if item["status"] == "completed"]
    skipped = [item for item in results if item["status"] == "skipped"]
    errors = [item for item in results if item["status"] == "error"]
    return {
        "schema_version": "skeinrank.agent_dictionary_quickstart_report.v1",
        "runner": "openrouter_alias_scout",
        "profile_name": config.profile_name,
        "binding_name": config.binding_name,
        "binding_id": binding_id,
        "index_name": config.index_name,
        "skeinrank_api_calls": True,
        "runtime_mutation_enabled": False,
        "snapshot_publish_enabled": False,
        "dictionary_import_requested": bool(apply_import),
        "binding_create_requested": bool(create_binding),
        "snapshot_export_requested": bool(export_snapshot),
        "summary": {
            "completed": len(completed),
            "skipped": len(skipped),
            "errors": len(errors),
            "dictionary_validated": _has_completed(results, "dictionary_validate"),
            "dictionary_imported": _has_completed(results, "dictionary_import"),
            "binding_created": _has_completed(results, "binding_create"),
            "snapshot_exported": _has_completed(results, "snapshot_export"),
        },
        "results": results,
        "safe_defaults": {
            "direct_dictionary_write": False,
            "runtime_mutation_enabled": False,
            "snapshot_publish_enabled": False,
            "snapshot_export_source": "latest",
        },
    }


def _stage(
    name: str, status: str, response: Any, reason: str | None = None
) -> JsonDict:
    item: JsonDict = {"stage": name, "status": status}
    if reason:
        item["reason"] = reason
    if response is not None:
        item["response"] = response
    return item


def _has_completed(results: Sequence[Mapping[str, Any]], stage: str) -> bool:
    return any(
        item.get("stage") == stage and item.get("status") == "completed"
        for item in results
    )


def _extract_id(response: Any) -> int | None:
    if isinstance(response, Mapping):
        value = response.get("id")
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
    return None


__all__ = [
    "DictionaryQuickstartConfig",
    "build_dictionary_quickstart_plan",
    "build_sample_binding_payload",
    "build_sample_dictionary_payload",
    "run_dictionary_quickstart",
    "write_dictionary_quickstart_payloads",
]
