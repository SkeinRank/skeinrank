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

from .dictionary_spec import load_mapping_document
from .runtime_snapshots import (
    RuntimeSnapshotArtifactCache,
    runtime_snapshot_artifact_summary,
)

DEFAULT_API_URL = "http://127.0.0.1:8010"
DEFAULT_TIMEOUT_SECONDS = 30.0


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
        if args.command == "validate":
            payload = _load_dictionary_object(args.file)
            result = client.validate_dictionary(payload)
            _write_json(result, args.output, pretty=not args.compact)
            if result.get("status") != "valid" and not args.allow_invalid:
                return 2
            return 0
        if args.command == "apply":
            payload = _load_dictionary_object(args.file)
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

    apply_parser = subparsers.add_parser(
        "apply",
        help="Apply a dictionary migration JSON/YAML file through the import API.",
    )
    _add_subcommand_compact_option(apply_parser)
    apply_parser.add_argument(
        "file", help="Input JSON/YAML file path, or '-' for stdin."
    )
    apply_parser.add_argument("-o", "--output", help="Write response JSON to a file.")

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
