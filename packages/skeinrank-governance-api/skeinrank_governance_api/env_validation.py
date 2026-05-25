"""Environment preflight checks for SkeinRank production-ish deployments.

The checks in this module are intentionally file-based and side-effect free:
they validate ``.env``-style files before Docker Compose starts services.
They do not connect to PostgreSQL, RabbitMQ, Elasticsearch, or the Governance API.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

FORMAT_VERSION = "skeinrank.env_validation.v1"
DEFAULT_PROFILE = "production-compose"

REQUIRED_PRODUCTION_COMPOSE_KEYS: tuple[str, ...] = (
    "POSTGRES_DB",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "RABBITMQ_DEFAULT_USER",
    "RABBITMQ_DEFAULT_PASS",
    "SKEINRANK_ENV",
    "SKEINRANK_GOVERNANCE_API_ENV",
    "SKEINRANK_GOVERNANCE_API_AUTH_ENABLED",
    "SKEINRANK_GOVERNANCE_API_PRODUCTION_SECURITY_ENABLED",
    "SKEINRANK_GOVERNANCE_API_ADMIN_PASSWORD",
    "SKEINRANK_GOVERNANCE_API_CORS_ORIGINS",
    "VITE_SKEINRANK_GOVERNANCE_API_URL",
    "GRAFANA_ADMIN_PASSWORD",
)

SECRET_KEYS: tuple[str, ...] = (
    "POSTGRES_PASSWORD",
    "RABBITMQ_DEFAULT_PASS",
    "SKEINRANK_GOVERNANCE_API_ADMIN_PASSWORD",
    "SKEINRANK_GOVERNANCE_API_ELASTICSEARCH_PASSWORD",
    "SKEINRANK_GOVERNANCE_API_ELASTICSEARCH_API_KEY",
    "GRAFANA_ADMIN_PASSWORD",
)

PLACEHOLDER_TOKENS: tuple[str, ...] = (
    "change_me",
    "change-me",
    "changeme",
    "example.com",
    "example.local",
    "your-domain",
    "your-ui",
    "your-es",
)

BOOLEAN_KEYS: tuple[str, ...] = (
    "SKEINRANK_GOVERNANCE_API_AUTH_ENABLED",
    "SKEINRANK_GOVERNANCE_API_PRODUCTION_SECURITY_ENABLED",
    "SKEINRANK_GOVERNANCE_API_BOOTSTRAP_ADMIN",
    "SKEINRANK_GOVERNANCE_API_OBSERVABILITY_ENABLED",
    "SKEINRANK_GOVERNANCE_API_METRICS_ENABLED",
    "SKEINRANK_GOVERNANCE_API_TRACING_ENABLED",
    "SKEINRANK_GOVERNANCE_API_OTEL_CAPTURE_QUERY_TEXT",
)

_ALLOWED_BOOLEAN_VALUES = {"1", "0", "true", "false", "yes", "no", "on", "off"}


@dataclass(frozen=True)
class EnvValidationIssue:
    """A single environment preflight issue."""

    level: str
    key: str
    message: str
    hint: str


def load_env_file(path: str | Path) -> dict[str, str]:
    """Load a simple Docker/Compose compatible ``.env`` file.

    The parser intentionally supports the subset used by Docker Compose env
    files: ``KEY=value`` lines, optional ``export`` prefix, blank lines, and
    comments. It does not expand variables and does not execute shell syntax.
    """

    env_path = Path(path)
    values: dict[str, str] = {}
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        values[key] = _strip_optional_quotes(value.strip())
    return values


def validate_env_values(
    values: dict[str, str],
    *,
    profile: str = DEFAULT_PROFILE,
    strict: bool = False,
    source: str | None = None,
) -> dict[str, Any]:
    """Validate parsed environment values and return a JSON-safe report."""

    if profile != DEFAULT_PROFILE:
        raise ValueError(f"Unsupported env validation profile: {profile}")

    issues: list[EnvValidationIssue] = []
    for key in REQUIRED_PRODUCTION_COMPOSE_KEYS:
        if not _has_value(values.get(key)):
            issues.append(
                EnvValidationIssue(
                    level="error",
                    key=key,
                    message="required production Compose setting is missing or empty",
                    hint="Set this value in .env before running docker compose.",
                )
            )

    _check_expected_value(
        issues,
        values,
        key="SKEINRANK_ENV",
        expected="production",
        message="SKEINRANK_ENV should be production for docker-compose.prod.yml",
    )
    _check_expected_value(
        issues,
        values,
        key="SKEINRANK_GOVERNANCE_API_ENV",
        expected="production",
        message="SKEINRANK_GOVERNANCE_API_ENV should be production for docker-compose.prod.yml",
    )
    _check_expected_value(
        issues,
        values,
        key="SKEINRANK_GOVERNANCE_API_AUTH_ENABLED",
        expected="true",
        message="auth must be enabled in the production-ish profile",
    )
    _check_expected_value(
        issues,
        values,
        key="SKEINRANK_GOVERNANCE_API_PRODUCTION_SECURITY_ENABLED",
        expected="true",
        message="production security guardrails should stay enabled",
    )

    cors_origins = _csv_values(values.get("SKEINRANK_GOVERNANCE_API_CORS_ORIGINS"))
    if "*" in cors_origins:
        issues.append(
            EnvValidationIssue(
                level="error",
                key="SKEINRANK_GOVERNANCE_API_CORS_ORIGINS",
                message="wildcard CORS origin is unsafe for the production-ish profile",
                hint="Use the exact UI origin, for example https://skeinrank.example.com.",
            )
        )
    for origin in cors_origins:
        if _looks_like_placeholder(origin):
            issues.append(
                EnvValidationIssue(
                    level="warning",
                    key="SKEINRANK_GOVERNANCE_API_CORS_ORIGINS",
                    message="CORS origin still looks like a placeholder",
                    hint="Replace example domains with the real UI origin before sharing the stack.",
                )
            )

    api_url = values.get("VITE_SKEINRANK_GOVERNANCE_API_URL", "")
    if _has_value(api_url):
        parsed_api_url = urlparse(api_url)
        if parsed_api_url.scheme not in {"http", "https"} or not parsed_api_url.netloc:
            issues.append(
                EnvValidationIssue(
                    level="error",
                    key="VITE_SKEINRANK_GOVERNANCE_API_URL",
                    message="UI API URL must be an absolute http(s) URL",
                    hint="Use a value such as http://127.0.0.1:8010 for local pilots or your public API origin.",
                )
            )
        if _looks_like_placeholder(api_url):
            issues.append(
                EnvValidationIssue(
                    level="warning",
                    key="VITE_SKEINRANK_GOVERNANCE_API_URL",
                    message="UI API URL still looks like a placeholder",
                    hint="Replace example domains with the API URL users will actually reach.",
                )
            )

    elasticsearch_url = values.get("SKEINRANK_GOVERNANCE_API_ELASTICSEARCH_URL", "")
    if _has_value(elasticsearch_url):
        parsed_es_url = urlparse(elasticsearch_url)
        if parsed_es_url.scheme not in {"http", "https"} or not parsed_es_url.netloc:
            issues.append(
                EnvValidationIssue(
                    level="error",
                    key="SKEINRANK_GOVERNANCE_API_ELASTICSEARCH_URL",
                    message="Elasticsearch URL must be an absolute http(s) URL when configured",
                    hint="Leave it empty for first bootstrap, or set a reachable Elasticsearch/OpenSearch endpoint.",
                )
            )
        if _looks_like_placeholder(elasticsearch_url):
            issues.append(
                EnvValidationIssue(
                    level="error",
                    key="SKEINRANK_GOVERNANCE_API_ELASTICSEARCH_URL",
                    message="Elasticsearch URL still points to an example placeholder",
                    hint="Leave the value empty until a real endpoint is available; placeholder URLs keep /readyz degraded.",
                )
            )
    elif (
        values.get("SKEINRANK_GOVERNANCE_API_ELASTICSEARCH_USERNAME")
        or values.get("SKEINRANK_GOVERNANCE_API_ELASTICSEARCH_PASSWORD")
        or values.get("SKEINRANK_GOVERNANCE_API_ELASTICSEARCH_API_KEY")
    ):
        issues.append(
            EnvValidationIssue(
                level="error",
                key="SKEINRANK_GOVERNANCE_API_ELASTICSEARCH_URL",
                message="Elasticsearch credentials were provided without an Elasticsearch URL",
                hint="Set the URL as well, or clear Elasticsearch credentials for first bootstrap.",
            )
        )
    else:
        issues.append(
            EnvValidationIssue(
                level="warning",
                key="SKEINRANK_GOVERNANCE_API_ELASTICSEARCH_URL",
                message="Elasticsearch is not configured",
                hint="This is fine for first bootstrap; strict readiness will stay degraded until search is configured.",
            )
        )

    for key in SECRET_KEYS:
        value = values.get(key)
        if not _has_value(value):
            continue
        if _looks_like_placeholder(value or ""):
            issues.append(
                EnvValidationIssue(
                    level="error",
                    key=key,
                    message="secret still looks like a placeholder or unsafe default",
                    hint="Generate a unique high-entropy value and keep it out of version control.",
                )
            )
        elif len(value or "") < 16:
            issues.append(
                EnvValidationIssue(
                    level="warning",
                    key=key,
                    message="secret is shorter than the recommended minimum length",
                    hint="Use at least 16 characters; 32+ random characters is better for production.",
                )
            )

    for key in BOOLEAN_KEYS:
        value = values.get(key)
        if _has_value(value) and value.strip().lower() not in _ALLOWED_BOOLEAN_VALUES:
            issues.append(
                EnvValidationIssue(
                    level="error",
                    key=key,
                    message="boolean setting uses an unsupported value",
                    hint="Use one of: true, false, 1, 0, yes, no, on, off.",
                )
            )

    if values.get("SKEINRANK_GOVERNANCE_API_LOG_FORMAT", "").strip().lower() not in {
        "json",
        "",
    }:
        issues.append(
            EnvValidationIssue(
                level="warning",
                key="SKEINRANK_GOVERNANCE_API_LOG_FORMAT",
                message="plain logs are less useful for production troubleshooting",
                hint="Use SKEINRANK_GOVERNANCE_API_LOG_FORMAT=json for log ingestion.",
            )
        )

    errors = [issue for issue in issues if issue.level == "error"]
    warnings = [issue for issue in issues if issue.level == "warning"]
    status = "ok"
    if errors:
        status = "failed"
    elif warnings:
        status = "warning"
    if strict and warnings and status == "warning":
        status = "failed"

    return {
        "format_version": FORMAT_VERSION,
        "status": status,
        "strict": strict,
        "profile": profile,
        "source": source,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "checked_keys_count": len(values),
        "errors": [asdict(issue) for issue in errors],
        "warnings": [asdict(issue) for issue in warnings],
        "summary": {
            "errors": len(errors),
            "warnings": len(warnings),
            "elasticsearch_configured": _has_value(elasticsearch_url),
        },
    }


def validate_env_file(
    path: str | Path,
    *,
    profile: str = DEFAULT_PROFILE,
    strict: bool = False,
) -> dict[str, Any]:
    """Validate an env file path and return a JSON-safe report."""

    env_path = Path(path)
    values = load_env_file(env_path)
    return validate_env_values(
        values,
        profile=profile,
        strict=strict,
        source=str(env_path),
    )


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for env validation."""

    parser = argparse.ArgumentParser(
        prog="skeinrank-governance-env",
        description="Validate SkeinRank production Compose environment files.",
    )
    subparsers = parser.add_subparsers(dest="command")
    validate_parser = subparsers.add_parser("validate", help="Validate a .env file")
    validate_parser.add_argument("--file", default=".env", help="Path to the env file")
    validate_parser.add_argument(
        "--profile",
        default=DEFAULT_PROFILE,
        choices=(DEFAULT_PROFILE,),
        help="Validation profile to use",
    )
    validate_parser.add_argument(
        "--strict",
        action="store_true",
        help="Return a non-zero exit code when warnings are present",
    )

    args = parser.parse_args(argv)
    if args.command != "validate":
        parser.print_help()
        return 2

    report = validate_env_file(args.file, profile=args.profile, strict=args.strict)
    print(json.dumps(report, indent=2, sort_keys=False))
    return 0 if report["status"] != "failed" else 1


def _strip_optional_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def _has_value(value: str | None) -> bool:
    return value is not None and bool(value.strip())


def _csv_values(value: str | None) -> list[str]:
    if value is None:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _check_expected_value(
    issues: list[EnvValidationIssue],
    values: dict[str, str],
    *,
    key: str,
    expected: str,
    message: str,
) -> None:
    value = values.get(key)
    if value is None:
        return
    if value.strip().lower() != expected:
        issues.append(
            EnvValidationIssue(
                level="error",
                key=key,
                message=message,
                hint=f"Set {key}={expected}.",
            )
        )


def _looks_like_placeholder(value: str) -> bool:
    normalized = value.strip().lower()
    if not normalized:
        return False
    if normalized in {"password", "secret", "admin", "guest"}:
        return True
    return any(token in normalized for token in PLACEHOLDER_TOKENS)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
