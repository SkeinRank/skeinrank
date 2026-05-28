"""Support bundle export helpers for first-company pilots.

The bundle exporter is intentionally read-only. It collects local diagnostic
artifacts, selected project docs/config examples, optional HTTP health snapshots,
and sanitized environment metadata into one ZIP file that can be shared with an
operator or maintainer without exposing secrets.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import platform
import re
import socket
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

SUPPORT_BUNDLE_PLAN_VERSION = "skeinrank.support_bundle_plan.v1"
SUPPORT_BUNDLE_MANIFEST_VERSION = "skeinrank.support_bundle_manifest.v1"

DEFAULT_OUTPUT = Path("examples/pilots/reports/skeinrank-troubleshooting-bundle.zip")

DEFAULT_INCLUDE_GLOBS = (
    "README.md",
    "docs/README.md",
    "docs/pilots/first-company-pilot-runbook.md",
    "docs/pilots/troubleshooting-bundle-export.md",
    "docs/deployment/dev-stack-troubleshooting.md",
    "docs/deployment/backup-restore.md",
    "docs/deployment/env-and-secrets.md",
    "docs/benchmarks/retrieval-eval-baseline.md",
    "docs/benchmarks/synthetic-smoke-generator.md",
    "docs/benchmarks/cost-latency-throughput-report.md",
    "examples/pilots/README.md",
    "examples/pilots/elasticsearch_pilot.example.json",
    "examples/pilots/first_company_pilot_checklist.md",
    "examples/pilots/reports/*.json",
    "examples/benchmarks/platform_ops_v1/README.md",
    "examples/benchmarks/platform_ops_v1/corpus_manifest.json",
    "examples/benchmarks/platform_ops_v1/reports/*.json",
    "examples/benchmarks/platform_ops_v1/reports/synthetic/*.json",
    "examples/agents/openrouter_alias_scout/README.md",
    "examples/agents/openrouter_alias_scout/env.example",
    "examples/agents/openrouter_alias_scout/reports/**/*.json",
    "deploy/docker/benchmark.env.example",
    "deploy/docker/headless.env.example",
    "deploy/docker/openrouter-alias-scout.env.example",
    "docker-compose.dev.yml",
    "docker-compose.headless.yml",
    "Makefile",
)

GENERATED_REPORT_PATTERNS = (
    "examples/pilots/reports/*",
    "examples/benchmarks/platform_ops_v1/reports/*",
    "examples/agents/openrouter_alias_scout/reports/*",
)

SECRET_KEY_FRAGMENTS = (
    "api_key",
    "apikey",
    "authorization",
    "bearer",
    "password",
    "passwd",
    "secret",
    "token",
    "credential",
    "private_key",
)

SECRET_TEXT_PATTERNS = (
    re.compile(r"sk-or-v1-[A-Za-z0-9_-]+"),
    re.compile(r"(?i)(OPENROUTER_API_KEY\s*=\s*)[^\s\n\r]+"),
    re.compile(r"(?i)(SKEINRANK_AGENT_API_TOKEN\s*=\s*)[^\s\n\r]+"),
    re.compile(r"(?i)(Authorization\s*:\s*Bearer\s+)[A-Za-z0-9._~+/=-]+"),
    re.compile(r"(?i)(password\s*[=:]\s*)[^\s,}\]]+"),
    re.compile(r"(?i)(token\s*[=:]\s*)[^\s,}\]]+"),
    re.compile(r"(?i)(secret\s*[=:]\s*)[^\s,}\]]+"),
)


def build_support_bundle_plan(
    *,
    project_root: Path | str,
    out: Path | str = DEFAULT_OUTPUT,
    include_generated_reports: bool = True,
    api_url: str | None = None,
) -> dict[str, Any]:
    """Return a read-only plan for a support bundle export."""

    root = Path(project_root).resolve()
    output = _resolve_output(root, out)
    candidate_files = _collect_candidate_files(
        root, include_generated_reports=include_generated_reports
    )
    return {
        "schema_version": SUPPORT_BUNDLE_PLAN_VERSION,
        "status": "planned",
        "project_root": str(root),
        "output": str(output),
        "include_generated_reports": include_generated_reports,
        "candidate_files_total": len(candidate_files),
        "candidate_files": [_relative_to_root(root, path) for path in candidate_files],
        "api_snapshot": {
            "enabled": bool(api_url),
            "url": _safe_url(api_url) if api_url else None,
            "endpoints": ["/livez", "/readyz", "/schema/health"],
            "ops_report_endpoint": "/v1/ops/troubleshooting/report",
        },
        "redaction": {
            "enabled": True,
            "secret_key_fragments": list(SECRET_KEY_FRAGMENTS),
            "openrouter_tokens_redacted": True,
            "authorization_headers_redacted": True,
        },
        "safety": _safety(),
    }


def export_support_bundle(
    *,
    project_root: Path | str,
    out: Path | str = DEFAULT_OUTPUT,
    include_generated_reports: bool = True,
    api_url: str | None = None,
    api_token: str | None = None,
    extra_files: list[Path | str] | None = None,
) -> dict[str, Any]:
    """Export a sanitized troubleshooting bundle ZIP and return its manifest."""

    root = Path(project_root).resolve()
    output = _resolve_output(root, out)
    output.parent.mkdir(parents=True, exist_ok=True)

    files = _collect_candidate_files(
        root, include_generated_reports=include_generated_reports
    )
    for extra in extra_files or []:
        path = (
            (root / extra).resolve() if not Path(extra).is_absolute() else Path(extra)
        )
        if _is_safe_project_file(root, path) and path.exists() and path.is_file():
            files.append(path)
    files = sorted(set(files))

    generated_at = datetime.now(timezone.utc).isoformat()
    manifest: dict[str, Any] = {
        "schema_version": SUPPORT_BUNDLE_MANIFEST_VERSION,
        "status": "exported",
        "generated_at": generated_at,
        "project_root_basename": root.name,
        "bundle_path": str(output),
        "files": [],
        "api_snapshots": [],
        "missing_optional_files": _missing_optional_files(root),
        "redactions": {
            "enabled": True,
            "secrets_redacted": True,
            "raw_environment_included": False,
        },
        "safety": _safety(),
    }

    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        _write_json(bundle, "env/redacted_environment.json", _redacted_environment())
        _write_json(bundle, "system/runtime_metadata.json", _runtime_metadata())
        _write_text(bundle, "README.txt", _bundle_readme(generated_at))
        _write_text(bundle, "commands/replay_commands.txt", _replay_commands())

        api_snapshots = _collect_api_snapshots(api_url=api_url, api_token=api_token)
        manifest["api_snapshots"] = api_snapshots
        _write_json(bundle, "api/api_snapshots.json", api_snapshots)

        for path in files:
            rel = _relative_to_root(root, path)
            bundle_path = f"files/{rel}"
            raw = path.read_bytes()
            sanitized = _sanitize_bytes(raw, path)
            bundle.writestr(bundle_path, sanitized)
            manifest["files"].append(
                {
                    "source_path": rel,
                    "bundle_path": bundle_path,
                    "sha256": hashlib.sha256(sanitized).hexdigest(),
                    "size_bytes": len(sanitized),
                    "redacted": sanitized != raw,
                    "category": _classify_path(rel),
                }
            )

        # Write the manifest after files/api snapshots are known.
        _write_json(bundle, "manifest.json", manifest)

    return manifest


def inspect_support_bundle(bundle_path: Path | str) -> dict[str, Any]:
    """Read a bundle manifest without extracting the ZIP."""

    with zipfile.ZipFile(bundle_path, "r") as bundle:
        with bundle.open("manifest.json") as handle:
            data = json.loads(handle.read().decode("utf-8"))
    if data.get("schema_version") != SUPPORT_BUNDLE_MANIFEST_VERSION:
        raise ValueError("Unsupported support bundle manifest schema")
    return data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m skeinrank_governance_api.support_bundle",
        description="Export sanitized SkeinRank troubleshooting bundles.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan_parser = subparsers.add_parser("plan", help="Print an export plan.")
    _add_common_args(plan_parser)

    export_parser = subparsers.add_parser("export", help="Write a ZIP bundle.")
    _add_common_args(export_parser)
    export_parser.add_argument(
        "--no-generated-reports",
        action="store_true",
        help="Skip ignored/generated report directories.",
    )
    export_parser.add_argument(
        "--extra-file",
        action="append",
        default=[],
        help="Additional project-relative file to include.",
    )

    inspect_parser = subparsers.add_parser("inspect", help="Print bundle manifest.")
    inspect_parser.add_argument("--file", required=True, help="Bundle ZIP file.")

    args = parser.parse_args(argv)
    if args.command == "plan":
        plan = build_support_bundle_plan(
            project_root=Path(args.project_root),
            out=Path(args.out),
            include_generated_reports=True,
            api_url=args.api_url,
        )
        print(json.dumps(plan, indent=2, ensure_ascii=False))
        return 0
    if args.command == "export":
        manifest = export_support_bundle(
            project_root=Path(args.project_root),
            out=Path(args.out),
            include_generated_reports=not args.no_generated_reports,
            api_url=args.api_url,
            api_token=args.api_token,
            extra_files=[Path(item) for item in args.extra_file],
        )
        print(json.dumps(manifest, indent=2, ensure_ascii=False))
        return 0
    if args.command == "inspect":
        manifest = inspect_support_bundle(Path(args.file))
        print(json.dumps(manifest, indent=2, ensure_ascii=False))
        return 0
    parser.error(f"Unknown command: {args.command}")
    return 2


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--project-root",
        default="../..",
        help="Repository root. Defaults to ../.. when run from package dir.",
    )
    parser.add_argument(
        "--out",
        default=str(DEFAULT_OUTPUT),
        help="Output ZIP path. Project-relative paths are resolved from project root.",
    )
    parser.add_argument(
        "--api-url",
        default=os.environ.get("SKEINRANK_SUPPORT_BUNDLE_API_URL"),
        help="Optional Governance API base URL for read-only health snapshots.",
    )
    parser.add_argument(
        "--api-token",
        default=os.environ.get("SKEINRANK_SUPPORT_BUNDLE_API_TOKEN"),
        help="Optional bearer token for /v1/ops/troubleshooting/report.",
    )


def _resolve_output(project_root: Path, out: Path | str) -> Path:
    path = Path(out)
    if not path.is_absolute():
        path = project_root / path
    return path.resolve()


def _collect_candidate_files(
    project_root: Path, *, include_generated_reports: bool
) -> list[Path]:
    files: list[Path] = []
    for pattern in DEFAULT_INCLUDE_GLOBS:
        if not include_generated_reports and any(
            fnmatch.fnmatch(pattern, generated_pattern)
            or pattern.startswith(generated_pattern.rstrip("*"))
            for generated_pattern in GENERATED_REPORT_PATTERNS
        ):
            continue
        files.extend(
            path
            for path in project_root.glob(pattern)
            if path.is_file() and _is_safe_project_file(project_root, path)
        )
    return sorted(set(files))


def _missing_optional_files(project_root: Path) -> list[str]:
    missing: list[str] = []
    for pattern in DEFAULT_INCLUDE_GLOBS:
        if "*" in pattern:
            continue
        if not (project_root / pattern).exists():
            missing.append(pattern)
    return missing


def _is_safe_project_file(project_root: Path, path: Path) -> bool:
    try:
        path.resolve().relative_to(project_root.resolve())
    except ValueError:
        return False
    parts = set(path.parts)
    if ".git" in parts or "__pycache__" in parts or ".venv" in parts:
        return False
    if path.name.startswith(".env"):
        return False
    if path.suffix in {".db", ".sqlite", ".sqlite3", ".pyc"}:
        return False
    return True


def _sanitize_bytes(raw: bytes, path: Path) -> bytes:
    text_suffixes = {".json", ".jsonl", ".md", ".txt", ".yml", ".yaml", ".env", ""}
    if path.suffix.lower() not in text_suffixes:
        return raw
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw
    stripped = text.lstrip()
    if path.suffix.lower() == ".json" and stripped.startswith(("{", "[")):
        try:
            data = json.loads(text)
            return json.dumps(_redact_value(data), indent=2, ensure_ascii=False).encode(
                "utf-8"
            )
        except json.JSONDecodeError:
            pass
    if path.suffix.lower() == ".jsonl":
        lines: list[str] = []
        for line in text.splitlines():
            if not line.strip():
                lines.append(line)
                continue
            try:
                lines.append(
                    json.dumps(_redact_value(json.loads(line)), ensure_ascii=False)
                )
            except json.JSONDecodeError:
                lines.append(_redact_text(line))
        return ("\n".join(lines) + ("\n" if text.endswith("\n") else "")).encode(
            "utf-8"
        )
    return _redact_text(text).encode("utf-8")


def _redacted_environment() -> dict[str, Any]:
    allowed_prefixes = (
        "SKEINRANK_",
        "OPENROUTER_",
        "POSTGRES_",
        "RABBITMQ_",
        "ELASTICSEARCH_",
        "GOVERNANCE_API_",
    )
    env: dict[str, Any] = {}
    for key, value in sorted(os.environ.items()):
        if key.startswith(allowed_prefixes):
            env[key] = _redact_scalar(key, value)
    return {
        "schema_version": "skeinrank.support_bundle_environment.v1",
        "raw_environment_included": False,
        "variables": env,
    }


def _runtime_metadata() -> dict[str, Any]:
    return {
        "schema_version": "skeinrank.support_bundle_runtime_metadata.v1",
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
        "machine": platform.machine(),
        "hostname_hash": hashlib.sha256(socket.gethostname().encode()).hexdigest()[:16],
        "cwd_basename": Path.cwd().name,
    }


def _collect_api_snapshots(
    *, api_url: str | None, api_token: str | None
) -> list[dict[str, Any]]:
    if not api_url:
        return []
    base = api_url.rstrip("/")
    endpoints = [
        "/livez",
        "/readyz",
        "/schema/health",
        "/v1/ops/troubleshooting/report",
    ]
    snapshots: list[dict[str, Any]] = []
    for endpoint in endpoints:
        headers = {"Accept": "application/json"}
        if api_token and endpoint.startswith("/v1/ops"):
            headers["Authorization"] = f"Bearer {api_token}"
        url = f"{base}{endpoint}"
        try:
            request = Request(url, headers=headers, method="GET")
            with urlopen(request, timeout=5) as response:  # noqa: S310 - operator URL
                body = response.read().decode("utf-8")
                payload: Any
                try:
                    payload = _redact_value(json.loads(body))
                except json.JSONDecodeError:
                    payload = _redact_text(body[:2000])
                snapshots.append(
                    {
                        "endpoint": endpoint,
                        "status": "ok",
                        "http_status": response.status,
                        "payload": payload,
                    }
                )
        except HTTPError as exc:
            snapshots.append(
                {
                    "endpoint": endpoint,
                    "status": "http_error",
                    "http_status": exc.code,
                    "payload": _redact_text(
                        exc.read().decode("utf-8", "replace")[:2000]
                    ),
                }
            )
        except (URLError, TimeoutError, OSError) as exc:
            snapshots.append(
                {
                    "endpoint": endpoint,
                    "status": "unavailable",
                    "message": f"{type(exc).__name__}: {_redact_text(str(exc))}",
                }
            )
    return snapshots


def _redact_value(value: Any, *, key_hint: str = "") -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if _is_secret_key(key_text):
                redacted[key_text] = "***REDACTED***"
            else:
                redacted[key_text] = _redact_value(item, key_hint=key_text)
        return redacted
    if isinstance(value, list):
        return [_redact_value(item, key_hint=key_hint) for item in value]
    if isinstance(value, str):
        return _redact_scalar(key_hint, value)
    return value


def _redact_scalar(key: str, value: str) -> str:
    if _is_secret_key(key):
        return "***REDACTED***"
    return _redact_text(value)


def _is_secret_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return any(fragment in normalized for fragment in SECRET_KEY_FRAGMENTS)


def _redact_text(text: str) -> str:
    redacted = text
    for pattern in SECRET_TEXT_PATTERNS:
        redacted = pattern.sub(
            lambda match: f"{match.group(1)}***REDACTED***"
            if match.groups()
            else "***REDACTED***",
            redacted,
        )
    return redacted


def _write_json(bundle: zipfile.ZipFile, path: str, data: Any) -> None:
    bundle.writestr(path, json.dumps(data, indent=2, ensure_ascii=False))


def _write_text(bundle: zipfile.ZipFile, path: str, text: str) -> None:
    bundle.writestr(path, text)


def _relative_to_root(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _safe_url(url: str | None) -> str | None:
    if not url:
        return None
    if "://" not in url:
        return url
    scheme, rest = url.split("://", 1)
    if "@" not in rest:
        return url
    return f"{scheme}://***@{rest.rsplit('@', 1)[1]}"


def _classify_path(relative_path: str) -> str:
    if "/reports/" in relative_path:
        return "generated_report"
    if relative_path.startswith("docs/"):
        return "documentation"
    if relative_path.startswith("examples/"):
        return "example_or_config"
    if relative_path.startswith("deploy/") or relative_path.startswith(
        "docker-compose"
    ):
        return "deployment_config"
    return "project_metadata"


def _safety() -> dict[str, bool]:
    return {
        "openrouter_calls": False,
        "elasticsearch_calls": False,
        "database_calls": False,
        "runtime_mutation_enabled": False,
        "raw_secrets_included": False,
        "generated_bundle_committed_by_default": False,
    }


def _bundle_readme(generated_at: str) -> str:
    return f"""SkeinRank troubleshooting bundle\n\nGenerated at: {generated_at}\n\nThis ZIP is intended for operator/support diagnostics. It contains sanitized\nproject docs, example configs, local reports, optional API health snapshots, and\nredacted environment metadata. Raw .env files, database files, cache artifacts,\nand known secret values are intentionally excluded or redacted.\n\nStart with manifest.json, api/api_snapshots.json, and commands/replay_commands.txt.\n"""


def _replay_commands() -> str:
    return """Suggested local checks\n\nmake support-bundle-plan\nmake support-bundle-export\nmake support-bundle-inspect\nmake benchmark-performance-show\nmake pilot-report\ncd packages/skeinrank-governance-api && poetry run python -m skeinrank_governance_api.troubleshooting report --strict\n"""


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    raise SystemExit(main())
