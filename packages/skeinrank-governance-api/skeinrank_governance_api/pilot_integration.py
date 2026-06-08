"""Pilot import and integration path for real Elasticsearch indices.

This CLI is intentionally dependency-light and HTTP-only. It gives operators a
repeatable validation path for a company Elasticsearch environment:

1. check the Governance API and Elasticsearch connection;
2. validate/apply a small seed dictionary;
3. create or reuse an Elasticsearch binding;
4. run read-only evidence and query-plan checks;
5. write a JSON report that can be shared with reviewers.

No OpenRouter calls are made here and no proposals are approved/applied. Live
agent validation remains a separate, opt-in workflow.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from pathlib import Path
from typing import Any

PILOT_CONFIG_SCHEMA_VERSION = "skeinrank.pilot.integration.v1"
PILOT_REPORT_SCHEMA_VERSION = "skeinrank.pilot.integration_report.v1"
DEFAULT_API_URL = "http://127.0.0.1:8010"
DEFAULT_REPORT = "pilot-integration-report.json"


class PilotIntegrationError(RuntimeError):
    """Raised for operator-facing pilot integration errors."""


class PilotApiError(PilotIntegrationError):
    """Raised when the Governance API returns a non-2xx status."""

    def __init__(self, status_code: int, detail: Any) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"SkeinRank API returned {status_code}: {detail}")


class PilotApiClient:
    """Small stdlib JSON client for pilot automation."""

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_API_URL,
        token: str | None = None,
        username: str | None = None,
        password: str | None = None,
        role: str = "admin",
        timeout_seconds: float = 20.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.username = username
        self.password = password
        self.role = role
        self.timeout_seconds = timeout_seconds

    def ensure_token(self) -> str | None:
        """Login when username/password are configured and no token is present."""

        if self.token:
            return self.token
        if self.username and self.password:
            response = self.request(
                "POST",
                "/v1/auth/login",
                {"username": self.username, "password": self.password},
                authenticate=False,
            )
            token = response.get("access_token") if isinstance(response, dict) else None
            if not token:
                raise PilotIntegrationError("Auth login did not return access_token.")
            self.token = str(token)
        return self.token

    def request(
        self,
        method: str,
        path: str,
        payload: Mapping[str, Any] | None = None,
        *,
        authenticate: bool = True,
    ) -> Any:
        """Execute a JSON request against the Governance API."""

        url = f"{self.base_url}{path}"
        headers = {
            "Accept": "application/json",
            "X-SkeinRank-Role": self.role,
        }
        if authenticate and self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        data: bytes | None = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=data,
            headers=headers,
            method=method.upper(),
        )
        try:
            with urllib.request.urlopen(  # noqa: S310 - operator-configured local URL.
                request,
                timeout=self.timeout_seconds,
            ) as response:
                body = response.read().decode("utf-8")
                return json.loads(body) if body else None
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8")
            try:
                detail: Any = json.loads(body)
            except json.JSONDecodeError:
                detail = body or exc.reason
            raise PilotApiError(exc.code, detail) from exc
        except urllib.error.URLError as exc:
            raise PilotIntegrationError(
                f"Could not reach SkeinRank Governance API at {self.base_url}: {exc}"
            ) from exc


def load_pilot_config(path: str | Path) -> dict[str, Any]:
    """Load and minimally validate a pilot integration JSON config."""

    config_path = Path(path)
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PilotIntegrationError(f"Pilot config not found: {config_path}") from exc
    except json.JSONDecodeError as exc:
        raise PilotIntegrationError(f"Pilot config is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise PilotIntegrationError("Pilot config must be a JSON object.")
    if payload.get("schema_version") != PILOT_CONFIG_SCHEMA_VERSION:
        raise PilotIntegrationError(
            "Unsupported pilot config schema_version: "
            f"{payload.get('schema_version')!r}; expected {PILOT_CONFIG_SCHEMA_VERSION}"
        )
    for required in ("pilot_name", "dictionary", "binding"):
        if required not in payload:
            raise PilotIntegrationError(
                f"Pilot config missing required key: {required}"
            )
    return payload


def build_pilot_plan(config: Mapping[str, Any], *, api_url: str) -> dict[str, Any]:
    """Return an offline plan. No network calls are made."""

    dictionary = _mapping(config["dictionary"], "dictionary")
    binding = _mapping(config["binding"], "binding")
    evidence_checks = _list_of_mappings(
        config.get("evidence_checks", []), "evidence_checks"
    )
    runtime_queries = _list_of_mappings(
        config.get("runtime_queries", []), "runtime_queries"
    )
    terms = _list_of_mappings(dictionary.get("terms", []), "dictionary.terms")

    return {
        "schema_version": "skeinrank.pilot.integration_plan.v1",
        "pilot_name": str(config["pilot_name"]),
        "api_url": api_url,
        "profile_name": str(dictionary.get("profile_name") or ""),
        "binding": {
            "name": str(binding.get("name") or ""),
            "index_name": str(binding.get("index_name") or ""),
            "text_fields": list(binding.get("text_fields") or []),
            "target_field": str(binding.get("target_field") or ""),
            "mode": str(binding.get("mode") or "dry_run"),
        },
        "dictionary": {
            "terms_total": len(terms),
            "aliases_total": sum(len(term.get("aliases") or []) for term in terms),
            "stop_list_total": len(dictionary.get("profile_stop_list") or []),
        },
        "checks": {
            "evidence_checks": len(evidence_checks),
            "runtime_queries": len(runtime_queries),
        },
        "network_calls": False,
        "openrouter_calls": False,
        "runtime_mutation_enabled": False,
        "safety": {
            "dictionary_apply_requires_seed_command": True,
            "binding_create_requires_seed_command": True,
            "pilot_eval_is_read_only": True,
            "openrouter_is_not_called": True,
            "proposal_submit_enabled": False,
            "approve_apply_enabled": False,
        },
        "recommended_flow": [
            "make pilot-preflight",
            "make pilot-seed",
            "make pilot-eval",
            "make pilot-report",
        ],
    }


def run_pilot_preflight(
    client: PilotApiClient, config: Mapping[str, Any]
) -> dict[str, Any]:
    """Check API, schema, Elasticsearch connection, index, and mapping fields."""

    client.ensure_token()
    binding = _mapping(config["binding"], "binding")
    index_name = str(binding["index_name"])
    expected_text_fields = [str(field) for field in binding.get("text_fields") or []]
    target_field = str(binding.get("target_field") or "")

    health = client.request("GET", "/healthz")
    schema_health = client.request("GET", "/schema/health")
    es_status = client.request("GET", "/v1/governance/elasticsearch/connection/status")
    mapping = client.request(
        "GET",
        f"/v1/governance/elasticsearch/indices/{urllib.parse.quote(index_name, safe='')}/mapping",
    )
    mapping_fields = {str(field.get("name")) for field in mapping.get("fields", [])}
    missing_text_fields = sorted(set(expected_text_fields) - mapping_fields)
    target_field_present = target_field in mapping_fields
    status = "passed" if not missing_text_fields else "failed"

    return {
        "schema_version": "skeinrank.pilot.preflight_report.v1",
        "status": status,
        "api": {
            "healthz_status": health.get("status")
            if isinstance(health, dict)
            else None,
            "schema_ok": schema_health.get("ok")
            if isinstance(schema_health, dict)
            else None,
            "current_revision": schema_health.get("current_revision")
            if isinstance(schema_health, dict)
            else None,
        },
        "elasticsearch": {
            "configured": es_status.get("configured")
            if isinstance(es_status, dict)
            else None,
            "ok": es_status.get("ok") if isinstance(es_status, dict) else None,
            "cluster_name": es_status.get("cluster_name")
            if isinstance(es_status, dict)
            else None,
            "cluster_version": es_status.get("cluster_version")
            if isinstance(es_status, dict)
            else None,
        },
        "index": {
            "name": index_name,
            "mapping_fields_total": len(mapping_fields),
            "expected_text_fields": expected_text_fields,
            "missing_text_fields": missing_text_fields,
            "target_field": target_field,
            "target_field_present": target_field_present,
        },
        "checks": [
            _check(
                "api_healthz_ok",
                health.get("status") == "ok",
                {"status": health.get("status")},
            ),
            _check(
                "schema_health_ok",
                bool(schema_health.get("ok"))
                and bool(schema_health.get("current_matches_head")),
                {
                    "ok": schema_health.get("ok"),
                    "current_matches_head": schema_health.get("current_matches_head"),
                },
            ),
            _check(
                "elasticsearch_connection_ok",
                bool(es_status.get("ok")),
                {"configured": es_status.get("configured"), "ok": es_status.get("ok")},
            ),
            _check(
                "pilot_text_fields_present",
                not missing_text_fields,
                {"missing_text_fields": missing_text_fields},
            ),
        ],
    }


def seed_pilot_integration(
    client: PilotApiClient, config: Mapping[str, Any]
) -> dict[str, Any]:
    """Apply dictionary and create/reuse a dry-run Elasticsearch binding."""

    client.ensure_token()
    dictionary = _mapping(config["dictionary"], "dictionary")
    binding = dict(_mapping(config["binding"], "binding"))
    profile_name = str(dictionary["profile_name"])

    validation = client.request("POST", "/v1/console/dictionary/validate", dictionary)
    applied = client.request("POST", "/v1/console/dictionary/import", dictionary)
    binding_payload = {**binding, "profile_name": profile_name}
    binding_result = _create_or_reuse_binding(client, binding_payload)

    return {
        "schema_version": "skeinrank.pilot.seed_report.v1",
        "status": "seeded",
        "profile_name": profile_name,
        "dictionary_validation": _dictionary_summary(validation),
        "dictionary_import": _dictionary_summary(applied),
        "binding": binding_result,
    }


def run_pilot_evaluation(
    client: PilotApiClient, config: Mapping[str, Any]
) -> dict[str, Any]:
    """Run read-only evidence and runtime-query checks for a pilot binding."""

    client.ensure_token()
    dictionary = _mapping(config["dictionary"], "dictionary")
    binding = _resolve_binding(client, config)
    binding_id = int(binding["id"])
    evidence_checks = _run_evidence_checks(client, config, binding_id)
    runtime_checks = _run_runtime_checks(client, config, binding_id)
    checks = evidence_checks + runtime_checks
    checks_failed = sum(1 for check in checks if check["status"] != "passed")
    status = "passed" if checks_failed == 0 else "failed"

    return {
        "schema_version": PILOT_REPORT_SCHEMA_VERSION,
        "pilot_name": str(config["pilot_name"]),
        "status": status,
        "profile_name": str(dictionary["profile_name"]),
        "binding": {
            "id": binding_id,
            "name": binding.get("name"),
            "index_name": binding.get("index_name"),
            "mode": binding.get("mode"),
            "is_enabled": binding.get("is_enabled"),
        },
        "checks_total": len(checks),
        "checks_failed": checks_failed,
        "evidence_checks": evidence_checks,
        "runtime_checks": runtime_checks,
        "safety": {
            "openrouter_calls": False,
            "proposal_submit_enabled": False,
            "approve_apply_enabled": False,
            "runtime_mutation_enabled": False,
            "elasticsearch_write_enabled": False,
        },
    }


def write_json_report(payload: Mapping[str, Any], path: str | Path) -> Path:
    """Write a pretty JSON report and return its absolute path."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return output_path.resolve()


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a safe pilot import/integration path for a real Elasticsearch index.",
    )
    parser.add_argument(
        "command", choices=["plan", "preflight", "seed", "eval", "run", "report"]
    )
    parser.add_argument(
        "--config", required=True, help="Path to a pilot integration JSON config."
    )
    parser.add_argument(
        "--api-url", default=os.getenv("SKEINRANK_PILOT_API_URL", DEFAULT_API_URL)
    )
    parser.add_argument("--token", default=os.getenv("SKEINRANK_PILOT_API_TOKEN"))
    parser.add_argument(
        "--username", default=os.getenv("SKEINRANK_PILOT_ADMIN_USERNAME")
    )
    parser.add_argument(
        "--password", default=os.getenv("SKEINRANK_PILOT_ADMIN_PASSWORD")
    )
    parser.add_argument(
        "--out", default=DEFAULT_REPORT, help="Report output path for eval/run."
    )
    parser.add_argument(
        "--file", help="Existing report file to print with the report command."
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    try:
        if args.command == "report":
            report_path = Path(args.file or args.out)
            if not report_path.exists():
                raise PilotIntegrationError(f"Pilot report not found: {report_path}")
            print(report_path.read_text(encoding="utf-8"), end="")
            return 0

        config = load_pilot_config(args.config)
        if args.command == "plan":
            print(json.dumps(build_pilot_plan(config, api_url=args.api_url), indent=2))
            return 0

        client = PilotApiClient(
            base_url=args.api_url,
            token=args.token,
            username=args.username,
            password=args.password,
        )
        if args.command == "preflight":
            result = run_pilot_preflight(client, config)
            print(json.dumps(result, indent=2))
            return 0 if result.get("status") == "passed" else 2
        if args.command == "seed":
            result = seed_pilot_integration(client, config)
            print(json.dumps(result, indent=2))
            return 0
        if args.command == "eval":
            result = run_pilot_evaluation(client, config)
            path = write_json_report(result, args.out)
            print(
                json.dumps(
                    {
                        "status": result["status"],
                        "report": str(path),
                        "checks_failed": result["checks_failed"],
                    },
                    indent=2,
                )
            )
            return 0 if result["status"] == "passed" else 2
        if args.command == "run":
            preflight = run_pilot_preflight(client, config)
            if preflight.get("status") != "passed":
                print(json.dumps(preflight, indent=2))
                return 2
            seed = seed_pilot_integration(client, config)
            evaluation = run_pilot_evaluation(client, config)
            result = {
                "schema_version": "skeinrank.pilot.integration_run.v1",
                "status": evaluation["status"],
                "preflight": preflight,
                "seed": seed,
                "evaluation": evaluation,
            }
            path = write_json_report(result, args.out)
            print(
                json.dumps(
                    {
                        "status": result["status"],
                        "report": str(path),
                        "checks_failed": evaluation["checks_failed"],
                    },
                    indent=2,
                )
            )
            return 0 if result["status"] == "passed" else 2
    except PilotIntegrationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 2


def _create_or_reuse_binding(
    client: PilotApiClient, binding_payload: Mapping[str, Any]
) -> dict[str, Any]:
    try:
        created = client.request(
            "POST", "/v1/governance/elasticsearch/bindings", binding_payload
        )
        return {"created": True, "binding": created}
    except PilotApiError as exc:
        if exc.status_code != 409:
            raise
    existing = _find_binding(client, binding_payload)
    if existing is None:
        raise PilotIntegrationError(
            "Binding create returned conflict, but an existing matching binding was not found."
        )
    return {"created": False, "binding": existing, "reason": "existing_binding_reused"}


def _resolve_binding(
    client: PilotApiClient, config: Mapping[str, Any]
) -> dict[str, Any]:
    binding = _mapping(config["binding"], "binding")
    dictionary = _mapping(config["dictionary"], "dictionary")
    payload = {**binding, "profile_name": dictionary["profile_name"]}
    existing = _find_binding(client, payload)
    if existing is None:
        raise PilotIntegrationError(
            "Pilot binding was not found. Run `make pilot-seed` before pilot evaluation."
        )
    return existing


def _find_binding(
    client: PilotApiClient, binding_payload: Mapping[str, Any]
) -> dict[str, Any] | None:
    profile_name = urllib.parse.quote(str(binding_payload["profile_name"]), safe="")
    bindings = client.request(
        "GET", f"/v1/governance/elasticsearch/bindings?profile_name={profile_name}"
    )
    if not isinstance(bindings, list):
        return None
    expected_name = str(binding_payload["name"])
    expected_index = str(binding_payload["index_name"])
    for binding in bindings:
        if (
            binding.get("name") == expected_name
            and binding.get("index_name") == expected_index
        ):
            return binding
    return None


def _run_evidence_checks(
    client: PilotApiClient, config: Mapping[str, Any], binding_id: int
) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for item in _list_of_mappings(config.get("evidence_checks", []), "evidence_checks"):
        alias = str(item["query"])
        canonical = item.get("canonical_value")
        min_documents = int(item.get("min_documents", 1))
        response = client.request(
            "POST",
            f"/v1/governance/elasticsearch/bindings/{binding_id}/evidence",
            {
                "query": alias,
                "canonical_value": canonical,
                "max_documents": int(item.get("max_documents", 5)),
                "context_chars": int(item.get("context_chars", 80)),
            },
        )
        documents = response.get("documents", []) if isinstance(response, dict) else []
        passed = len(documents) >= min_documents
        checks.append(
            {
                "name": f"evidence_found_for_{_safe_name(alias)}",
                "status": "passed" if passed else "failed",
                "message": f"Evidence check for {alias} returned {len(documents)} documents.",
                "details": {
                    "alias": alias,
                    "canonical": canonical,
                    "documents": len(documents),
                    "min_documents": min_documents,
                },
            }
        )
    return checks


def _run_runtime_checks(
    client: PilotApiClient, config: Mapping[str, Any], binding_id: int
) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for item in _list_of_mappings(config.get("runtime_queries", []), "runtime_queries"):
        query = str(item["query"])
        expected = [str(value) for value in item.get("expected_canonicals", [])]
        response = client.request(
            "POST",
            "/v1/query/plan",
            {
                "binding_id": binding_id,
                "query": query,
                "include_evidence": bool(item.get("include_evidence", True)),
                "size": int(item.get("size", 10)),
            },
        )
        found = [str(value) for value in response.get("canonical_values", [])]
        missing = sorted(set(expected) - set(found))
        passed = not missing
        checks.append(
            {
                "name": f"query_plan_matches_{_safe_name(query)}",
                "status": "passed" if passed else "failed",
                "message": f"Runtime query plan matched {len(expected) - len(missing)}/{len(expected)} expected canonicals.",
                "details": {
                    "query": query,
                    "expected": expected,
                    "found": found,
                    "missing": missing,
                },
            }
        )
    return checks


def _dictionary_summary(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {"status": "unknown"}
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    return {
        "status": payload.get("status"),
        "profile_name": payload.get("profile_name"),
        "errors": len(payload.get("errors") or []),
        "warnings": len(payload.get("warnings") or []),
        "summary": summary,
    }


def _check(name: str, passed: bool, details: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "name": name,
        "status": "passed" if passed else "failed",
        "details": dict(details),
    }


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise PilotIntegrationError(f"{name} must be an object.")
    return value


def _list_of_mappings(value: Any, name: str) -> list[Mapping[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise PilotIntegrationError(f"{name} must be a list.")
    result: list[Mapping[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise PilotIntegrationError(f"{name}[{index}] must be an object.")
        result.append(item)
    return result


def _safe_name(value: str) -> str:
    return "".join(char.lower() if char.isalnum() else "_" for char in value).strip(
        "_"
    )[:80]


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
