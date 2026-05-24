"""Runtime API final smoke helpers for the OpenRouter alias scout.

Patch 42G adds a dependency-free runtime smoke contract for the final operator
journey after dictionary import, binding setup, and optional snapshot export. It
calls only existing runtime/headless API endpoints through the generic
``SkeinRankAgentClient.request`` method:

    POST /v1/text/canonicalize
    POST /v1/query/plan
    GET  /v1/headless/snapshots/export?binding_id=<id>&source=latest

The smoke is validation-oriented. It does not mutate dictionaries, publish
snapshots, or submit proposals.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlencode

JsonDict = dict[str, Any]


class RuntimeApiSmokeClient(Protocol):
    """Minimal client protocol used by the runtime API smoke executor."""

    def request(
        self, method: str, path: str, payload: Mapping[str, Any] | None = None
    ) -> Any: ...


@dataclass(frozen=True)
class RuntimeApiSmokeConfig:
    """Config for the Patch 42G runtime API final smoke."""

    artifacts_dir: Path
    profile_name: str = "infra_incidents"
    binding_id: int | None = None
    text: str = "pg timeout after k8s rollout"
    query: str = "pg timeout k8s rollout"
    text_fields: tuple[str, ...] = ("title", "text", "query")
    target_field: str = "skeinrank.canonical_terms"
    canonicalize_mode: str = "replace"
    include_evidence: bool = True
    max_matches: int = 20
    size: int = 5
    canonical_boost: float = 3.0
    expected_canonical_values: tuple[str, ...] = ("postgresql", "kubernetes")
    export_snapshot_by_default: bool = False
    snapshot_source: str = "latest"

    @classmethod
    def from_mapping(
        cls, raw: Mapping[str, Any] | None, *, base_dir: Path | None = None
    ) -> "RuntimeApiSmokeConfig":
        """Create config from optional JSON config values."""

        data = dict(raw or {})
        artifacts_dir = Path(str(data.get("artifacts_dir", "reports/runtime-smoke")))
        if base_dir is not None and not artifacts_dir.is_absolute():
            artifacts_dir = base_dir / artifacts_dir
        binding_id_raw = data.get("binding_id")
        text_fields = data.get("text_fields", list(cls.text_fields))
        expected = data.get(
            "expected_canonical_values", list(cls.expected_canonical_values)
        )
        return cls(
            artifacts_dir=artifacts_dir,
            profile_name=str(data.get("profile_name", cls.profile_name)),
            binding_id=int(binding_id_raw) if binding_id_raw is not None else None,
            text=str(data.get("text", cls.text)),
            query=str(data.get("query", cls.query)),
            text_fields=tuple(str(item) for item in text_fields),
            target_field=str(data.get("target_field", cls.target_field)),
            canonicalize_mode=str(data.get("canonicalize_mode", cls.canonicalize_mode)),
            include_evidence=bool(data.get("include_evidence", cls.include_evidence)),
            max_matches=int(data.get("max_matches", cls.max_matches)),
            size=int(data.get("size", cls.size)),
            canonical_boost=float(data.get("canonical_boost", cls.canonical_boost)),
            expected_canonical_values=tuple(str(item) for item in expected),
            export_snapshot_by_default=bool(
                data.get("export_snapshot_by_default", cls.export_snapshot_by_default)
            ),
            snapshot_source=str(data.get("snapshot_source", cls.snapshot_source)),
        )

    def with_overrides(
        self,
        *,
        artifacts_dir: Path | None = None,
        profile_name: str | None = None,
        binding_id: int | None = None,
        text: str | None = None,
        query: str | None = None,
        export_snapshot: bool | None = None,
    ) -> "RuntimeApiSmokeConfig":
        """Return a copy with CLI overrides applied."""

        return RuntimeApiSmokeConfig(
            artifacts_dir=artifacts_dir or self.artifacts_dir,
            profile_name=profile_name or self.profile_name,
            binding_id=binding_id if binding_id is not None else self.binding_id,
            text=text or self.text,
            query=query or self.query,
            text_fields=self.text_fields,
            target_field=self.target_field,
            canonicalize_mode=self.canonicalize_mode,
            include_evidence=self.include_evidence,
            max_matches=self.max_matches,
            size=self.size,
            canonical_boost=self.canonical_boost,
            expected_canonical_values=self.expected_canonical_values,
            export_snapshot_by_default=(
                export_snapshot
                if export_snapshot is not None
                else self.export_snapshot_by_default
            ),
            snapshot_source=self.snapshot_source,
        )

    def canonicalize_payload(self) -> JsonDict:
        payload: JsonDict = {
            "text": self.text,
            "mode": self.canonicalize_mode,
            "include_evidence": self.include_evidence,
            "max_matches": self.max_matches,
        }
        if self.binding_id is not None:
            payload["binding_id"] = self.binding_id
        else:
            payload["profile_name"] = self.profile_name
        return payload

    def query_plan_payload(self) -> JsonDict:
        payload: JsonDict = {
            "query": self.query,
            "text_fields": list(self.text_fields),
            "target_field": self.target_field,
            "size": self.size,
            "canonical_boost": self.canonical_boost,
            "include_evidence": self.include_evidence,
            "max_matches": self.max_matches,
        }
        if self.binding_id is not None:
            payload["binding_id"] = self.binding_id
        else:
            payload["profile_name"] = self.profile_name
        return payload


def build_runtime_api_smoke_plan(config: RuntimeApiSmokeConfig) -> JsonDict:
    """Return a network-free plan for the runtime API final smoke."""

    return {
        "schema_version": "skeinrank.agent_runtime_api_smoke_plan.v1",
        "runner": "openrouter_alias_scout",
        "patch": "42G",
        "profile_name": config.profile_name,
        "binding_id": config.binding_id,
        "artifacts_dir": str(config.artifacts_dir),
        "expected_canonical_values": list(config.expected_canonical_values),
        "api_flow": [
            "POST /v1/text/canonicalize",
            "POST /v1/query/plan",
            "GET /v1/headless/snapshots/export?binding_id=<id>&source=latest (optional)",
        ],
        "payloads": {
            "canonicalize": config.canonicalize_payload(),
            "query_plan": config.query_plan_payload(),
        },
        "safe_defaults": {
            "network_calls_in_plan": False,
            "runtime_mutation_enabled": False,
            "proposal_submission_enabled": False,
            "snapshot_publish_enabled": False,
            "snapshot_export_enabled_by_default": config.export_snapshot_by_default,
        },
        "commands": {
            "run": [
                "python",
                "examples/agents/openrouter_alias_scout/run_alias_scout.py",
                "--run-runtime-api-smoke",
            ],
            "write_report": [
                "python",
                "examples/agents/openrouter_alias_scout/run_alias_scout.py",
                "--write-runtime-api-smoke-report",
                "reports/runtime-smoke/runtime-api-smoke.json",
            ],
        },
        "next_steps": [
            "Run migrations and start the Governance API before live smoke commands.",
            "Run the dictionary quickstart first when the profile does not exist yet.",
            "Use --runtime-smoke-binding-id plus --runtime-smoke-export-snapshot to test binding-scoped export.",
        ],
    }


def run_runtime_api_smoke(
    *,
    client: RuntimeApiSmokeClient,
    config: RuntimeApiSmokeConfig,
    export_snapshot: bool | None = None,
) -> JsonDict:
    """Run the live runtime API smoke through existing SkeinRank endpoints."""

    should_export_snapshot = (
        config.export_snapshot_by_default
        if export_snapshot is None
        else bool(export_snapshot)
    )
    steps: list[JsonDict] = []
    responses: JsonDict = {}

    canonicalize_response = _call_step(
        steps,
        name="text_canonicalize",
        method="POST",
        path="/v1/text/canonicalize",
        payload=config.canonicalize_payload(),
        client=client,
        validator=lambda response: _validate_canonicalize_response(response, config),
    )
    if canonicalize_response is not None:
        responses["canonicalize"] = canonicalize_response

    query_plan_response = _call_step(
        steps,
        name="query_plan",
        method="POST",
        path="/v1/query/plan",
        payload=config.query_plan_payload(),
        client=client,
        validator=lambda response: _validate_query_plan_response(response, config),
    )
    if query_plan_response is not None:
        responses["query_plan"] = query_plan_response

    if should_export_snapshot:
        if config.binding_id is None:
            steps.append(
                {
                    "name": "snapshot_export",
                    "status": "skipped",
                    "reason": "binding_id_required_for_snapshot_export",
                    "network_calls": False,
                }
            )
        else:
            query = urlencode(
                {"binding_id": str(config.binding_id), "source": config.snapshot_source}
            )
            snapshot_response = _call_step(
                steps,
                name="snapshot_export",
                method="GET",
                path=f"/v1/headless/snapshots/export?{query}",
                payload=None,
                client=client,
                validator=_validate_snapshot_export_response,
            )
            if snapshot_response is not None:
                responses["snapshot_export"] = snapshot_response
    else:
        steps.append(
            {
                "name": "snapshot_export",
                "status": "skipped",
                "reason": "snapshot_export_not_requested",
                "network_calls": False,
            }
        )

    summary = _summarize_steps(steps)
    status = "passed" if summary["failed"] == 0 else "failed"
    if status == "passed" and summary["warnings"]:
        status = "passed_with_warnings"

    return {
        "schema_version": "skeinrank.agent_runtime_api_smoke.v1",
        "runner": "openrouter_alias_scout",
        "patch": "42G",
        "status": status,
        "recommended_exit_code": 0 if status.startswith("passed") else 2,
        "profile_name": config.profile_name,
        "binding_id": config.binding_id,
        "expected_canonical_values": list(config.expected_canonical_values),
        "summary": summary,
        "steps": steps,
        "responses": responses,
        "runtime_mutation_enabled": False,
        "snapshot_publish_enabled": False,
        "proposal_submission_enabled": False,
        "skeinrank_api_calls": True,
        "openrouter_calls": False,
        "elasticsearch_calls": False,
        "next_steps": [
            "Inspect canonicalize/query_plan responses before enabling runtime consumers.",
            "Use binding-scoped smoke after creating and exporting a runtime binding snapshot.",
            "Keep proposal approval and snapshot publishing in the governed flow.",
        ],
    }


def _call_step(
    steps: list[JsonDict],
    *,
    name: str,
    method: str,
    path: str,
    payload: Mapping[str, Any] | None,
    client: RuntimeApiSmokeClient,
    validator,
) -> JsonDict | None:
    try:
        response = client.request(method, path, payload)
        validation = validator(response)
        status = "passed" if validation["passed"] else "failed"
        if status == "passed" and validation.get("warnings"):
            status = "warning"
        steps.append(
            {
                "name": name,
                "status": status,
                "network_calls": True,
                "path": path,
                "method": method,
                "validation": validation,
            }
        )
        return response if isinstance(response, dict) else {"value": response}
    except (
        Exception
    ) as exc:  # pragma: no cover - exact exception type comes from client.
        steps.append(
            {
                "name": name,
                "status": "failed",
                "network_calls": True,
                "path": path,
                "method": method,
                "error": str(exc),
            }
        )
        return None


def _validate_canonicalize_response(
    response: Any, config: RuntimeApiSmokeConfig
) -> JsonDict:
    if not isinstance(response, Mapping):
        return {"passed": False, "reason": "response_is_not_object", "warnings": []}
    canonical_values = _string_set(response.get("canonical_values"))
    expected = set(config.expected_canonical_values)
    missing = sorted(expected - canonical_values)
    warnings = []
    if missing:
        warnings.append(f"Missing expected canonical values: {', '.join(missing)}")
    return {
        "passed": bool(response.get("profile_name"))
        and "canonical_text" in response
        and isinstance(response.get("matched_aliases", []), list),
        "changed": bool(response.get("changed")),
        "canonical_values": sorted(canonical_values),
        "matched_aliases": response.get("matched_aliases", []),
        "missing_expected_canonicals": missing,
        "warnings": warnings,
    }


def _validate_query_plan_response(
    response: Any, config: RuntimeApiSmokeConfig
) -> JsonDict:
    if not isinstance(response, Mapping):
        return {"passed": False, "reason": "response_is_not_object", "warnings": []}
    canonical_values = _string_set(response.get("canonical_values"))
    expected = set(config.expected_canonical_values)
    missing = sorted(expected - canonical_values)
    warnings = []
    if missing:
        warnings.append(f"Missing expected canonical values: {', '.join(missing)}")
    elasticsearch = response.get("elasticsearch")
    return {
        "passed": bool(response.get("profile_name"))
        and "canonical_query" in response
        and isinstance(elasticsearch, Mapping),
        "changed": bool(response.get("changed")),
        "canonical_values": sorted(canonical_values),
        "matched_aliases": response.get("matched_aliases", []),
        "elasticsearch_query_present": isinstance(elasticsearch, Mapping),
        "missing_expected_canonicals": missing,
        "warnings": warnings,
    }


def _validate_snapshot_export_response(response: Any) -> JsonDict:
    if not isinstance(response, Mapping):
        return {"passed": False, "reason": "response_is_not_object", "warnings": []}
    has_snapshot = bool(response.get("snapshot") or response.get("aliases"))
    return {
        "passed": bool(response.get("schema_version")) or has_snapshot,
        "schema_version": response.get("schema_version"),
        "has_aliases": bool(response.get("aliases")),
        "warnings": []
        if has_snapshot
        else ["Snapshot artifact did not include aliases."],
    }


def _summarize_steps(steps: Sequence[Mapping[str, Any]]) -> JsonDict:
    counts = {"passed": 0, "warnings": 0, "failed": 0, "skipped": 0}
    for step in steps:
        status = str(step.get("status") or "")
        if status == "passed":
            counts["passed"] += 1
        elif status == "warning":
            counts["warnings"] += 1
        elif status == "skipped":
            counts["skipped"] += 1
        else:
            counts["failed"] += 1
    return {
        "steps_total": len(steps),
        **counts,
        "runtime_api_calls": sum(1 for step in steps if step.get("network_calls")),
    }


def _string_set(value: Any) -> set[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return set()
    return {str(item) for item in value}


__all__ = [
    "RuntimeApiSmokeConfig",
    "build_runtime_api_smoke_plan",
    "run_runtime_api_smoke",
]
