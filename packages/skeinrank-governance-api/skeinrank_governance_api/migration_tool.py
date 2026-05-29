"""CLI tool for migrating dictionaries through the User Console API."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from skeinrank_governance.models import normalize_profile_name, normalize_value

from .dictionary_spec import (
    DICTIONARY_SCHEMA_VERSION,
    is_supported_dictionary_schema_version,
    load_mapping_document,
    resolve_dictionary_schema_version,
)
from .runtime_snapshots import (
    RuntimeSnapshotArtifactCache,
    runtime_snapshot_artifact_summary,
)
from .snapshot_evaluation import evaluate_runtime_snapshot_artifacts

DEFAULT_API_URL = "http://127.0.0.1:8010"
DEFAULT_TIMEOUT_SECONDS = 30.0
DICTIONARY_LINT_SCHEMA_VERSION = "skeinrank.dictionary_lint.v1"
DICTIONARY_APPLY_PLAN_SCHEMA_VERSION = "skeinrank.dictionary_apply_plan.v1"
IMPORT_MODES = frozenset({"upsert", "strict"})
STOP_LIST_TARGETS = frozenset({"alias", "canonical", "both"})


class MigrationToolError(RuntimeError):
    """Raised when the migration API request cannot be completed."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        response_body: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


class DictionaryMigrationClient:
    """Small stdlib HTTP client for the User Console dictionary API."""

    def __init__(
        self,
        api_url: str = DEFAULT_API_URL,
        *,
        token: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self.api_url = api_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    def validate_dictionary(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Validate a dictionary payload without applying changes."""

        return self._request("POST", "/v1/console/dictionary/validate", payload=payload)

    def import_dictionary(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Apply a dictionary payload through the console import endpoint."""

        return self._request("POST", "/v1/console/dictionary/import", payload=payload)

    def export_dictionary(
        self,
        profile_name: str,
        *,
        include_global_stop_list: bool = True,
    ) -> dict[str, Any]:
        """Export a profile dictionary in the stable migration JSON shape."""

        return self._request(
            "GET",
            "/v1/console/dictionary/export",
            query={
                "profile_name": profile_name,
                "include_global_stop_list": str(include_global_stop_list).lower(),
            },
        )

    def export_snapshot_artifact(
        self,
        binding_id: int,
        *,
        source: str = "latest",
        snapshot_version: str | None = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        """Export a binding-scoped runtime snapshot artifact."""

        query = {"binding_id": str(binding_id), "source": source}
        if snapshot_version:
            query["snapshot_version"] = snapshot_version
        if description:
            query["description"] = description
        return self._request(
            "GET",
            "/v1/headless/snapshots/export",
            query=query,
        )

    def _request(
        self,
        method: str,
        path: str,
        *,
        payload: Mapping[str, Any] | None = None,
        query: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        url = self._url(path, query=query)
        data: bytes | None = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        request = Request(url, data=data, headers=headers, method=method)
        try:
            with urlopen(request, timeout=self.timeout) as response:  # noqa: S310
                raw = response.read().decode("utf-8")
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise MigrationToolError(
                f"Console API request failed with HTTP {exc.code}: {body}",
                status_code=exc.code,
                response_body=body,
            ) from exc
        except URLError as exc:
            raise MigrationToolError(
                f"Console API request failed: {exc.reason}"
            ) from exc
        except TimeoutError as exc:
            raise MigrationToolError("Console API request timed out") from exc
        if not raw:
            return {}
        try:
            decoded = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise MigrationToolError(
                f"Console API returned non-JSON response: {raw}"
            ) from exc
        if not isinstance(decoded, dict):
            raise MigrationToolError("Console API returned JSON that is not an object")
        return decoded

    def _url(self, path: str, *, query: Mapping[str, str] | None = None) -> str:
        url = f"{self.api_url}{path}"
        if query:
            url = f"{url}?{urlencode(query)}"
        return url


def lint_dictionary_payload(
    payload: Mapping[str, Any],
    *,
    source: str | None = None,
) -> dict[str, Any]:
    """Run local JSON/YAML dictionary lint checks without contacting the API.

    The lint report intentionally checks only portable file-level problems. It
    does not inspect PostgreSQL state, existing aliases, RBAC, or scopes. Use
    ``skeinrank-migrate plan`` for the server-backed apply plan.
    """

    summary: dict[str, int] = {
        "terms_total": 0,
        "aliases_total": 0,
        "profile_stop_list_total": 0,
        "global_stop_list_total": 0,
        "duplicates": 0,
        "conflicts": 0,
        "errors": 0,
        "warnings": 0,
    }
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []

    def add_issue(
        bucket: list[dict[str, str]],
        *,
        code: str,
        message: str,
        path: str | None = None,
        severity: str,
    ) -> None:
        issue = {"code": code, "message": message, "severity": severity}
        if path is not None:
            issue["path"] = path
        bucket.append(issue)
        summary[f"{severity}s"] += 1
        if code.startswith("duplicate_"):
            summary["duplicates"] += 1
        if "collision" in code or "conflict" in code:
            summary["conflicts"] += 1

    schema_version = resolve_dictionary_schema_version(payload)
    if not is_supported_dictionary_schema_version(payload):
        add_issue(
            errors,
            code="unsupported_schema_version",
            message=(
                "Unsupported dictionary schema_version: "
                f"{schema_version}. Supported version: {DICTIONARY_SCHEMA_VERSION}."
            ),
            path="schema_version",
            severity="error",
        )

    profile_name = payload.get("profile_name")
    normalized_profile_name = ""
    if not isinstance(profile_name, str) or not profile_name.strip():
        add_issue(
            errors,
            code="missing_profile_name",
            message="Dictionary profile_name must be a non-empty string.",
            path="profile_name",
            severity="error",
        )
    else:
        normalized_profile_name = normalize_profile_name(profile_name)

    mode = payload.get("mode", "upsert")
    if not isinstance(mode, str) or mode.strip().lower() not in IMPORT_MODES:
        add_issue(
            errors,
            code="invalid_import_mode",
            message="Dictionary mode must be one of: strict, upsert.",
            path="mode",
            severity="error",
        )
        mode = str(mode)
    else:
        mode = mode.strip().lower()

    terms = payload.get("terms", [])
    if not isinstance(terms, list):
        add_issue(
            errors,
            code="invalid_terms_shape",
            message="Dictionary terms must be a list.",
            path="terms",
            severity="error",
        )
        terms = []

    seen_terms: dict[str, str] = {}
    seen_aliases: dict[str, tuple[str, str]] = {}
    for term_index, raw_term in enumerate(terms):
        term_path = f"terms[{term_index}]"
        if not isinstance(raw_term, Mapping):
            add_issue(
                errors,
                code="invalid_term_shape",
                message="Dictionary term entries must be objects.",
                path=term_path,
                severity="error",
            )
            continue
        summary["terms_total"] += 1
        canonical_value = raw_term.get("canonical_value")
        normalized_canonical = ""
        if not isinstance(canonical_value, str) or not canonical_value.strip():
            add_issue(
                errors,
                code="missing_canonical_value",
                message="Term canonical_value must be a non-empty string.",
                path=f"{term_path}.canonical_value",
                severity="error",
            )
        else:
            normalized_canonical = normalize_value(canonical_value)
            duplicate_path = seen_terms.get(normalized_canonical)
            if duplicate_path:
                add_issue(
                    errors,
                    code="duplicate_canonical_term",
                    message=f"Canonical term appears more than once: {canonical_value}",
                    path=f"{term_path}.canonical_value",
                    severity="error",
                )
            else:
                seen_terms[normalized_canonical] = f"{term_path}.canonical_value"

        slot = raw_term.get("slot")
        if not isinstance(slot, str) or not slot.strip():
            add_issue(
                errors,
                code="missing_slot",
                message="Term slot must be a non-empty string.",
                path=f"{term_path}.slot",
                severity="error",
            )

        tags = raw_term.get("tags", [])
        if tags is not None and not isinstance(tags, list):
            add_issue(
                errors,
                code="invalid_tags_shape",
                message="Term tags must be a list of strings when provided.",
                path=f"{term_path}.tags",
                severity="error",
            )
        elif isinstance(tags, list):
            for tag_index, tag in enumerate(tags):
                if not isinstance(tag, str) or not tag.strip():
                    add_issue(
                        errors,
                        code="invalid_tag_value",
                        message="Term tag values must be non-empty strings.",
                        path=f"{term_path}.tags[{tag_index}]",
                        severity="error",
                    )

        aliases = raw_term.get("aliases", [])
        if not isinstance(aliases, list):
            add_issue(
                errors,
                code="invalid_aliases_shape",
                message="Term aliases must be a list.",
                path=f"{term_path}.aliases",
                severity="error",
            )
            continue
        aliases_seen_for_term: set[str] = set()
        for alias_index, raw_alias in enumerate(aliases):
            alias_path = f"{term_path}.aliases[{alias_index}]"
            alias_value: str | None = None
            if isinstance(raw_alias, str):
                alias_value = raw_alias
            elif isinstance(raw_alias, Mapping):
                raw_value = raw_alias.get("value")
                if isinstance(raw_value, str):
                    alias_value = raw_value
                else:
                    add_issue(
                        errors,
                        code="missing_alias_value",
                        message="Alias object value must be a non-empty string.",
                        path=f"{alias_path}.value",
                        severity="error",
                    )
                    continue
            else:
                add_issue(
                    errors,
                    code="invalid_alias_shape",
                    message="Aliases must be strings or objects with a value field.",
                    path=alias_path,
                    severity="error",
                )
                continue

            if not alias_value.strip():
                add_issue(
                    errors,
                    code="empty_alias_value",
                    message="Alias value is empty after trimming.",
                    path=alias_path,
                    severity="error",
                )
                continue
            summary["aliases_total"] += 1
            normalized_alias = normalize_value(alias_value)
            if normalized_alias == normalized_canonical and normalized_canonical:
                add_issue(
                    warnings,
                    code="alias_matches_canonical",
                    message=f"Alias is the same as canonical value: {alias_value}",
                    path=alias_path,
                    severity="warning",
                )
            if normalized_alias in aliases_seen_for_term:
                add_issue(
                    warnings,
                    code="duplicate_alias_in_term",
                    message=f"Alias is repeated in the same term: {alias_value}",
                    path=alias_path,
                    severity="warning",
                )
                continue
            aliases_seen_for_term.add(normalized_alias)
            existing_alias = seen_aliases.get(normalized_alias)
            if existing_alias is None:
                seen_aliases[normalized_alias] = (normalized_canonical, alias_path)
            elif existing_alias[0] != normalized_canonical:
                add_issue(
                    errors,
                    code="alias_payload_collision",
                    message=(
                        f"Alias maps to multiple canonical terms in this file: "
                        f"{alias_value}"
                    ),
                    path=alias_path,
                    severity="error",
                )

    _lint_stop_list_entries(
        payload.get("profile_stop_list", []),
        base_path="profile_stop_list",
        summary=summary,
        errors=errors,
        warnings=warnings,
        add_issue=add_issue,
    )
    _lint_stop_list_entries(
        payload.get("global_stop_list", []),
        base_path="global_stop_list",
        summary=summary,
        errors=errors,
        warnings=warnings,
        add_issue=add_issue,
    )

    status = "valid" if not errors else "invalid"
    return {
        "schema_version": DICTIONARY_LINT_SCHEMA_VERSION,
        "status": status,
        "source": source,
        "dictionary_schema_version": schema_version,
        "profile_name": profile_name if isinstance(profile_name, str) else None,
        "normalized_profile_name": normalized_profile_name,
        "mode": mode,
        "summary": summary,
        "errors": errors,
        "warnings": warnings,
        "checks": {
            "local_only": True,
            "server_state_checked": False,
            "safe_for_apply_decision": False,
        },
    }


def _lint_stop_list_entries(
    entries: Any,
    *,
    base_path: str,
    summary: dict[str, int],
    errors: list[dict[str, str]],
    warnings: list[dict[str, str]],
    add_issue,
) -> None:
    if not isinstance(entries, list):
        add_issue(
            errors,
            code=f"invalid_{base_path}_shape",
            message=f"{base_path} must be a list.",
            path=base_path,
            severity="error",
        )
        return
    summary[f"{base_path}_total"] = len(entries)
    seen: set[tuple[str, str]] = set()
    for index, raw_entry in enumerate(entries):
        entry_path = f"{base_path}[{index}]"
        target = "both"
        value: str | None = None
        if isinstance(raw_entry, str):
            value = raw_entry
        elif isinstance(raw_entry, Mapping):
            raw_value = raw_entry.get("value")
            if isinstance(raw_value, str):
                value = raw_value
            else:
                add_issue(
                    errors,
                    code="missing_stop_list_value",
                    message="Stop-list object value must be a non-empty string.",
                    path=f"{entry_path}.value",
                    severity="error",
                )
            raw_target = raw_entry.get("target", "both")
            if isinstance(raw_target, str):
                target = raw_target.strip().lower()
            else:
                target = str(raw_target)
        else:
            add_issue(
                errors,
                code="invalid_stop_list_entry_shape",
                message="Stop-list entries must be strings or objects.",
                path=entry_path,
                severity="error",
            )
            continue
        if target not in STOP_LIST_TARGETS:
            add_issue(
                errors,
                code="invalid_stop_list_target",
                message="Stop-list target must be one of: alias, both, canonical.",
                path=f"{entry_path}.target",
                severity="error",
            )
        if value is None:
            continue
        if not value.strip():
            add_issue(
                errors,
                code="empty_stop_list_value",
                message="Stop-list value is empty after trimming.",
                path=entry_path,
                severity="error",
            )
            continue
        key = (target, normalize_value(value))
        if key in seen:
            add_issue(
                warnings,
                code="duplicate_stop_list_entry",
                message=f"Duplicate stop-list entry in {base_path}: {value}",
                path=entry_path,
                severity="warning",
            )
        seen.add(key)


def build_dictionary_apply_plan(
    payload: Mapping[str, Any],
    validation_report: Mapping[str, Any],
    *,
    source: str | None = None,
) -> dict[str, Any]:
    """Build a safe apply plan from the existing validation API response."""

    summary = validation_report.get("summary", {})
    if not isinstance(summary, Mapping):
        summary = {}
    errors = validation_report.get("errors", [])
    status = str(validation_report.get("status", "invalid"))
    safe_to_apply = status == "valid" and not errors
    operations = _build_plan_operations(payload, validation_report, summary)
    if not operations:
        operations = [
            {
                "action": "no_changes_detected",
                "count": 0,
                "description": "Validation did not report any create/update operations.",
            }
        ]
    plan_status = "ready" if safe_to_apply else "blocked"
    return {
        "schema_version": DICTIONARY_APPLY_PLAN_SCHEMA_VERSION,
        "status": plan_status,
        "safe_to_apply": safe_to_apply,
        "source": source,
        "profile_name": validation_report.get("profile_name")
        or payload.get("profile_name"),
        "normalized_profile_name": validation_report.get("normalized_profile_name"),
        "profile_exists": validation_report.get("profile_exists"),
        "mode": validation_report.get("mode") or payload.get("mode", "upsert"),
        "operations": operations,
        "summary": dict(summary),
        "validation": dict(validation_report),
        "notes": [
            "Plan is derived from the existing validate endpoint; no state was written.",
            "Run apply only when safe_to_apply is true and the plan was reviewed.",
        ],
    }


def _build_plan_operations(
    payload: Mapping[str, Any],
    validation_report: Mapping[str, Any],
    summary: Mapping[str, Any],
) -> list[dict[str, Any]]:
    operations: list[dict[str, Any]] = []
    create_profile = bool(payload.get("create_profile", True))
    if validation_report.get("profile_exists") is False and create_profile:
        operations.append(
            {
                "action": "create_profile",
                "count": 1,
                "description": "Create the target terminology profile before importing terms.",
            }
        )
    operation_fields = (
        ("would_create_terms", "create_terms", "Create canonical terms."),
        ("would_update_terms", "update_terms", "Update existing canonical terms."),
        ("would_create_aliases", "create_aliases", "Create aliases."),
        ("would_update_aliases", "update_aliases", "Update existing aliases."),
        (
            "would_create_profile_stop_list_entries",
            "create_profile_stop_list_entries",
            "Create profile stop-list entries.",
        ),
        (
            "would_update_profile_stop_list_entries",
            "update_profile_stop_list_entries",
            "Update profile stop-list entries.",
        ),
        (
            "would_create_global_stop_list_entries",
            "create_global_stop_list_entries",
            "Create global stop-list entries.",
        ),
        (
            "would_update_global_stop_list_entries",
            "update_global_stop_list_entries",
            "Update global stop-list entries.",
        ),
    )
    for summary_key, action, description in operation_fields:
        count = _as_int(summary.get(summary_key))
        if count > 0:
            operations.append(
                {"action": action, "count": count, "description": description}
            )
    return operations


def _as_int(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Run the migration CLI."""

    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help(sys.stderr)
        return 2

    token = args.token or os.environ.get("SKEINRANK_API_TOKEN")
    client = DictionaryMigrationClient(
        args.api_url,
        token=token,
        timeout=args.timeout,
    )
    try:
        if args.command == "lint":
            payload = _load_dictionary_object(args.file)
            result = lint_dictionary_payload(payload, source=args.file)
            _write_json(result, args.output, pretty=not args.compact)
            if result.get("status") != "valid" and not args.allow_invalid:
                return 2
            return 0
        if args.command == "validate":
            payload = _load_dictionary_object(args.file)
            result = client.validate_dictionary(payload)
            _write_json(result, args.output, pretty=not args.compact)
            if result.get("status") != "valid" and not args.allow_invalid:
                return 2
            return 0
        if args.command == "plan":
            payload = _load_dictionary_object(args.file)
            validation = client.validate_dictionary(payload)
            result = build_dictionary_apply_plan(payload, validation, source=args.file)
            _write_json(result, args.output, pretty=not args.compact)
            if not result.get("safe_to_apply") and not args.allow_invalid:
                return 2
            return 0
        if args.command == "apply":
            payload = _load_dictionary_object(args.file)
            if args.plan_output:
                validation = client.validate_dictionary(payload)
                plan = build_dictionary_apply_plan(
                    payload, validation, source=args.file
                )
                _write_json(plan, args.plan_output, pretty=not args.compact)
                if not plan.get("safe_to_apply"):
                    return 2
            result = client.import_dictionary(payload)
            _write_json(result, args.output, pretty=not args.compact)
            return 0
        if args.command == "export":
            result = client.export_dictionary(
                args.profile_name,
                include_global_stop_list=args.include_global_stop_list,
            )
            _write_json(result, args.output, pretty=not args.compact)
            return 0
        if args.command == "snapshot-export":
            result = client.export_snapshot_artifact(
                args.binding_id,
                source=args.source,
                snapshot_version=args.snapshot_version,
                description=args.description,
            )
            _write_json(result, args.output, pretty=not args.compact)
            return 0
        if args.command == "snapshot-inspect":
            loaded = RuntimeSnapshotArtifactCache().get(args.file)
            result = runtime_snapshot_artifact_summary(loaded)
            _write_json(result, args.output, pretty=not args.compact)
            return 0
        if args.command == "snapshot-eval":
            result = evaluate_runtime_snapshot_artifacts(
                before_path=args.before,
                after_path=args.after,
                queries_path=args.queries,
            )
            _write_json(result, args.output, pretty=not args.compact)
            return 0
    except (OSError, ValueError, MigrationToolError) as exc:
        print(f"skeinrank-migrate: {exc}", file=sys.stderr)
        return 1

    parser.error(f"unknown command: {args.command}")
    return 2


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""

    parser = argparse.ArgumentParser(
        prog="skeinrank-migrate",
        description="Validate, apply, and export SkeinRank dictionary migrations.",
    )
    parser.add_argument(
        "--api-url",
        default=os.environ.get("SKEINRANK_CONSOLE_API_URL", DEFAULT_API_URL),
        help=(
            "Governance API base URL. Defaults to SKEINRANK_CONSOLE_API_URL "
            f"or {DEFAULT_API_URL}."
        ),
    )
    parser.add_argument(
        "--token",
        default=None,
        help="Bearer token. Defaults to SKEINRANK_API_TOKEN when set.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help="HTTP request timeout in seconds.",
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Write compact JSON instead of pretty-printed JSON.",
    )
    subparsers = parser.add_subparsers(dest="command")

    lint_parser = subparsers.add_parser(
        "lint",
        help="Run local JSON/YAML dictionary lint checks without contacting the API.",
    )
    _add_subcommand_compact_option(lint_parser)
    lint_parser.add_argument(
        "file", help="Input JSON/YAML file path, or '-' for JSON stdin."
    )
    lint_parser.add_argument("-o", "--output", help="Write lint JSON to a file.")
    lint_parser.add_argument(
        "--allow-invalid",
        action="store_true",
        help="Return exit code 0 even when the lint report is invalid.",
    )

    validate_parser = subparsers.add_parser(
        "validate",
        help="Validate a dictionary migration JSON/YAML file without writing changes.",
    )
    _add_subcommand_compact_option(validate_parser)
    validate_parser.add_argument(
        "file", help="Input JSON/YAML file path, or '-' for stdin."
    )
    validate_parser.add_argument(
        "-o", "--output", help="Write response JSON to a file."
    )
    validate_parser.add_argument(
        "--allow-invalid",
        action="store_true",
        help="Return exit code 0 even when the validation report is invalid.",
    )

    plan_parser = subparsers.add_parser(
        "plan",
        help="Build a server-backed apply plan without writing changes.",
    )
    _add_subcommand_compact_option(plan_parser)
    plan_parser.add_argument(
        "file", help="Input JSON/YAML file path, or '-' for JSON stdin."
    )
    plan_parser.add_argument("-o", "--output", help="Write apply plan JSON to a file.")
    plan_parser.add_argument(
        "--allow-invalid",
        action="store_true",
        help="Return exit code 0 even when the apply plan is blocked.",
    )

    apply_parser = subparsers.add_parser(
        "apply",
        help="Apply a dictionary migration JSON/YAML file through the import API.",
    )
    _add_subcommand_compact_option(apply_parser)
    apply_parser.add_argument(
        "file", help="Input JSON/YAML file path, or '-' for JSON stdin."
    )
    apply_parser.add_argument("-o", "--output", help="Write response JSON to a file.")
    apply_parser.add_argument(
        "--plan-output",
        help=(
            "Validate first and write the reviewed apply plan JSON before import. "
            "If the plan is blocked, apply is not called."
        ),
    )

    export_parser = subparsers.add_parser(
        "export",
        help="Export a profile dictionary in the migration JSON shape.",
    )
    _add_subcommand_compact_option(export_parser)
    export_parser.add_argument(
        "--profile-name", required=True, help="Profile to export."
    )
    export_parser.add_argument("-o", "--output", help="Write export JSON to a file.")
    export_parser.add_argument(
        "--no-global-stop-list",
        action="store_false",
        dest="include_global_stop_list",
        help="Exclude the global stop list from export output.",
    )
    export_parser.set_defaults(include_global_stop_list=True)

    snapshot_export_parser = subparsers.add_parser(
        "snapshot-export",
        help="Export a binding-scoped runtime snapshot artifact.",
    )
    _add_subcommand_compact_option(snapshot_export_parser)
    snapshot_export_parser.add_argument(
        "--binding-id", type=int, required=True, help="Binding id to export."
    )
    snapshot_export_parser.add_argument(
        "--source",
        choices=("latest", "runtime"),
        default="latest",
        help=(
            "Snapshot source: latest builds from current profile state; "
            "runtime exports the binding-pinned runtime snapshot."
        ),
    )
    snapshot_export_parser.add_argument(
        "--snapshot-version",
        default=None,
        help="Optional version to use when building from latest profile state.",
    )
    snapshot_export_parser.add_argument(
        "--description", default=None, help="Optional artifact description."
    )
    snapshot_export_parser.add_argument(
        "-o", "--output", help="Write artifact JSON to a file."
    )

    snapshot_inspect_parser = subparsers.add_parser(
        "snapshot-inspect",
        help="Validate and summarize a local runtime snapshot artifact file.",
    )
    _add_subcommand_compact_option(snapshot_inspect_parser)
    snapshot_inspect_parser.add_argument(
        "file", help="Runtime snapshot artifact JSON file path."
    )
    snapshot_inspect_parser.add_argument(
        "-o", "--output", help="Write summary JSON to a file."
    )

    snapshot_eval_parser = subparsers.add_parser(
        "snapshot-eval",
        help="Compare two runtime snapshot artifacts and optional query plans.",
    )
    _add_subcommand_compact_option(snapshot_eval_parser)
    snapshot_eval_parser.add_argument(
        "--before", required=True, help="Baseline runtime snapshot artifact JSON."
    )
    snapshot_eval_parser.add_argument(
        "--after", required=True, help="Candidate runtime snapshot artifact JSON."
    )
    snapshot_eval_parser.add_argument(
        "--queries",
        default=None,
        help="Optional JSON/JSONL query set for canonicalization diffing.",
    )
    snapshot_eval_parser.add_argument(
        "-o", "--output", help="Write evaluation report JSON to a file."
    )
    return parser


def _add_subcommand_compact_option(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--compact",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Write compact JSON instead of pretty-printed JSON.",
    )


def _load_dictionary_object(path: str) -> dict[str, Any]:
    if path == "-":
        raw = sys.stdin.read()
        try:
            loaded = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in stdin: {exc}") from exc
        if not isinstance(loaded, dict):
            raise ValueError("Dictionary document root must be an object")
        return loaded
    return load_mapping_document(path)


def _load_json_object(path: str) -> dict[str, Any]:
    """Backward-compatible test helper for legacy JSON migration inputs."""

    return _load_dictionary_object(path)


def _write_json(
    payload: Mapping[str, Any],
    output_path: str | None,
    *,
    pretty: bool,
) -> None:
    if pretty:
        rendered = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    else:
        rendered = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    rendered = f"{rendered}\n"
    if output_path:
        Path(output_path).write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
