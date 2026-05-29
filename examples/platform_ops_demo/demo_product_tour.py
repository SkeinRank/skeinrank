#!/usr/bin/env python3
"""Run a safe smoke check for the seeded SkeinRank product demo.

The tour is intentionally stdlib-only so it can run from a clean checkout after
``docker compose -f docker-compose.dev.yml up`` and ``make demo-reset``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from seed_platform_demo import (  # noqa: E402
    BINDING_NAME,
    DEFAULT_API_URL,
    DEFAULT_ELASTICSEARCH_URL,
    DEFAULT_PASSWORD,
    DEFAULT_UI_URL,
    DEFAULT_USERNAME,
    DEMO_QUERY,
    INDEX_NAME,
    PROFILE_NAME,
    RUNTIME_ALIAS,
    DemoSeedError,
    JsonHttpClient,
    authenticate,
    ensure_safe_urls,
    find_existing_binding,
    is_local_url,
    load_guided_walkthrough,
    quote_index_name,
    walkthrough_summary,
)

SCHEMA_VERSION = "skeinrank.demo_product_tour_report.v1"
DEFAULT_REPORT_PATH = SCRIPT_DIR / "reports" / "platform_ops_demo_tour_report.json"
REQUIRED_CANONICAL_VALUES = {"kubernetes", "postgresql", "project phoenix"}
REQUIRED_PROPOSALS = {"edge", "EKS", "OpenSearch", "prod"}
READ_ONLY_ENDPOINTS = (
    "GET /livez",
    "GET /readyz",
    "GET /v1/auth/me",
    "GET /v1/governance/profiles/platform_ops/terms",
    "GET /v1/governance/elasticsearch/bindings?profile_name=platform_ops",
    "GET /v1/governance/profiles/platform_ops/suggestions",
    "POST /v1/query/plan (read-only planning)",
    "GET /_count for demo indices",
)


@dataclass(frozen=True)
class DemoTourConfig:
    """Runtime configuration for the one-command demo tour smoke check."""

    api_url: str
    elasticsearch_url: str
    ui_url: str
    username: str
    password: str
    force_non_local: bool
    skip_ui_check: bool
    plan_only: bool
    write_report: Path | None


def parse_args(argv: list[str] | None = None) -> DemoTourConfig:
    """Parse CLI arguments into a DemoTourConfig."""

    parser = argparse.ArgumentParser(
        description="Run the SkeinRank seeded demo product tour smoke check.",
    )
    parser.add_argument(
        "--api-url",
        default=os.getenv("SKEINRANK_DEMO_API_URL", DEFAULT_API_URL),
        help=f"Governance API URL. Default: {DEFAULT_API_URL}",
    )
    parser.add_argument(
        "--elasticsearch-url",
        default=os.getenv(
            "SKEINRANK_DEMO_ELASTICSEARCH_URL",
            DEFAULT_ELASTICSEARCH_URL,
        ),
        help=f"Elasticsearch URL. Default: {DEFAULT_ELASTICSEARCH_URL}",
    )
    parser.add_argument(
        "--ui-url",
        default=os.getenv("SKEINRANK_DEMO_UI_URL", DEFAULT_UI_URL),
        help=f"UI URL. Default: {DEFAULT_UI_URL}",
    )
    parser.add_argument(
        "--username",
        default=os.getenv("SKEINRANK_DEMO_ADMIN_USERNAME", DEFAULT_USERNAME),
        help="Admin username for the local demo stack.",
    )
    parser.add_argument(
        "--password",
        default=os.getenv("SKEINRANK_DEMO_ADMIN_PASSWORD", DEFAULT_PASSWORD),
        help="Admin password for the local demo stack.",
    )
    parser.add_argument(
        "--force-non-local",
        action="store_true",
        help="Allow non-local API/Elasticsearch/UI URLs. Use with care.",
    )
    parser.add_argument(
        "--skip-ui-check",
        action="store_true",
        help="Skip the HTTP check for the React dev server.",
    )
    parser.add_argument(
        "--plan",
        action="store_true",
        help="Print the tour plan without calling API, UI, or Elasticsearch.",
    )
    parser.add_argument(
        "--write-report",
        type=Path,
        default=None,
        help=(
            "Write the smoke report JSON. Defaults to no file. "
            f"Makefile uses {DEFAULT_REPORT_PATH.relative_to(SCRIPT_DIR.parent.parent)}."
        ),
    )
    args = parser.parse_args(argv)
    return DemoTourConfig(
        api_url=args.api_url,
        elasticsearch_url=args.elasticsearch_url,
        ui_url=args.ui_url,
        username=args.username,
        password=args.password,
        force_non_local=args.force_non_local,
        skip_ui_check=args.skip_ui_check,
        plan_only=args.plan,
        write_report=args.write_report,
    )


def check_safe_urls(config: DemoTourConfig) -> None:
    """Prevent accidental demo tour calls against non-local systems by default."""

    class _SeedCompatibleConfig:
        api_url = config.api_url
        elasticsearch_url = config.elasticsearch_url
        force_non_local = config.force_non_local

    ensure_safe_urls(_SeedCompatibleConfig())
    if (
        not config.force_non_local
        and not config.skip_ui_check
        and not is_local_url(config.ui_url)
    ):
        raise DemoSeedError(
            "Refusing to check non-local UI URL by default: "
            f"{config.ui_url}. Pass --force-non-local to override."
        )


def http_probe(url: str) -> dict[str, Any]:
    """Return a small HTTP probe summary without assuming a JSON response."""

    request = urllib.request.Request(
        url, headers={"Accept": "text/html,application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            body = response.read(256)
            status = getattr(response, "status", 200)
            content_type = response.headers.get("Content-Type", "")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise DemoSeedError(f"HTTP {exc.code} GET {url}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise DemoSeedError(f"Cannot reach {url}: {exc.reason}") from exc
    return {
        "status_code": status,
        "content_type": content_type,
        "body_preview_bytes": len(body),
    }


def check(name: str, passed: bool, **details: Any) -> dict[str, Any]:
    """Build a stable check result object."""

    return {"name": name, "status": "passed" if passed else "failed", **details}


def warning(name: str, **details: Any) -> dict[str, Any]:
    """Build a stable warning result object."""

    return {"name": name, "status": "warning", **details}


def _sorted_missing(expected: set[str], actual: set[str]) -> list[str]:
    return sorted(expected - actual)


def build_plan(config: DemoTourConfig) -> dict[str, Any]:
    """Build an offline product tour plan without touching local services."""

    walkthrough = load_guided_walkthrough()
    summary = walkthrough_summary(walkthrough)
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "planned",
        "demo": {
            "profile": PROFILE_NAME,
            "binding_name": BINDING_NAME,
            "index": INDEX_NAME,
            "runtime_alias": RUNTIME_ALIAS,
            "query": DEMO_QUERY,
            "ui_url": config.ui_url,
            "api_url": config.api_url,
            "elasticsearch_url": config.elasticsearch_url,
        },
        "walkthrough": {
            "tabs": summary["tabs"],
            "steps": walkthrough.get("guided_steps", []),
            "demo_proposals": walkthrough.get("demo_proposals", []),
        },
        "commands": {
            "seed_or_reset": "make demo-reset",
            "read_only_smoke": "make demo-tour-smoke",
            "one_command_tour": "make demo-tour",
            "show_report": "make demo-tour-show",
        },
        "safety": {
            "network_calls": False,
            "database_mutation_enabled": False,
            "elasticsearch_mutation_enabled": False,
            "runtime_mutation_enabled": False,
            "legacy_write_tools_enabled_by_default": False,
            "read_only_smoke_endpoints": list(READ_ONLY_ENDPOINTS),
        },
    }


def find_pending_demo_proposals(suggestions: list[dict[str, Any]]) -> dict[str, Any]:
    """Return proposal aliases and missing proposal aliases for the tour report."""

    aliases: set[str] = set()
    rows: list[dict[str, Any]] = []
    for suggestion in suggestions:
        alias = str(suggestion.get("alias_value") or "")
        status = str(suggestion.get("status") or "")
        if alias in REQUIRED_PROPOSALS and status == "pending":
            aliases.add(alias)
            rows.append(
                {
                    "id": suggestion.get("id"),
                    "alias_value": alias,
                    "canonical_value": suggestion.get("canonical_value"),
                    "status": status,
                    "confidence": suggestion.get("confidence"),
                    "source": suggestion.get("source"),
                    "proposal_source_type": suggestion.get("proposal_source_type"),
                    "proposal_source_name": suggestion.get("proposal_source_name"),
                }
            )
    return {
        "pending_aliases": sorted(aliases),
        "missing_aliases": _sorted_missing(REQUIRED_PROPOSALS, aliases),
        "rows": sorted(rows, key=lambda item: str(item.get("alias_value") or "")),
    }


def run_smoke(config: DemoTourConfig) -> dict[str, Any]:
    """Run the read-oriented product tour smoke check against local services."""

    check_safe_urls(config)
    api_public = JsonHttpClient(config.api_url)
    es = JsonHttpClient(config.elasticsearch_url)
    checks: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    livez = api_public.get("/livez")
    checks.append(check("api_livez", isinstance(livez, dict), response=livez))
    readyz = api_public.get("/readyz")
    checks.append(check("api_readyz", isinstance(readyz, dict), response=readyz))
    es_root = es.get("/")
    checks.append(
        check(
            "elasticsearch_root",
            isinstance(es_root, dict),
            name_value=es_root.get("name") if isinstance(es_root, dict) else None,
        )
    )

    if config.skip_ui_check:
        warnings.append(warning("ui_root", reason="skipped"))
    else:
        ui_probe = http_probe(config.ui_url)
        checks.append(
            check(
                "ui_root",
                200 <= int(ui_probe["status_code"]) < 500,
                response=ui_probe,
            )
        )

    token = authenticate(api_public, config)
    api = JsonHttpClient(config.api_url, token=token)
    me = api.get("/v1/auth/me")
    checks.append(
        check(
            "auth_me",
            isinstance(me, dict),
            username=me.get("username") if isinstance(me, dict) else None,
        )
    )

    profile_terms = api.get(f"/v1/governance/profiles/{PROFILE_NAME}/terms")
    terms_count = len(profile_terms) if isinstance(profile_terms, list) else 0
    checks.append(check("profile_terms", terms_count >= 16, count=terms_count))

    bindings = api.get(
        f"/v1/governance/elasticsearch/bindings?profile_name={PROFILE_NAME}"
    )
    binding = find_existing_binding(bindings) if isinstance(bindings, list) else None
    binding_id = (
        int(binding["id"]) if binding and binding.get("id") is not None else None
    )
    checks.append(
        check(
            "runtime_binding",
            binding_id is not None,
            binding_id=binding_id,
            binding_name=binding.get("name") if binding else None,
        )
    )

    source_count_response = es.get(f"/{quote_index_name(INDEX_NAME)}/_count")
    source_count = (
        int(source_count_response.get("count", 0))
        if isinstance(source_count_response, dict)
        else 0
    )
    checks.append(
        check("source_index_documents", source_count >= 24, count=source_count)
    )

    try:
        alias_count_response = es.get(f"/{quote_index_name(RUNTIME_ALIAS)}/_count")
        alias_count = (
            int(alias_count_response.get("count", 0))
            if isinstance(alias_count_response, dict)
            else 0
        )
        checks.append(
            check("runtime_alias_documents", alias_count > 0, count=alias_count)
        )
    except DemoSeedError as exc:
        warnings.append(warning("runtime_alias_documents", reason=str(exc)))

    canonical_values: set[str] = set()
    if binding_id is not None:
        query_plan = api.post(
            "/v1/query/plan",
            {"binding_id": binding_id, "query": DEMO_QUERY, "size": 10},
        )
        if isinstance(query_plan, dict):
            canonical_values = {
                str(value) for value in query_plan.get("canonical_values", [])
            }
        checks.append(
            check(
                "playground_query_plan",
                REQUIRED_CANONICAL_VALUES <= canonical_values,
                canonical_values=sorted(canonical_values),
                missing_canonical_values=_sorted_missing(
                    REQUIRED_CANONICAL_VALUES, canonical_values
                ),
            )
        )
    else:
        checks.append(
            check(
                "playground_query_plan",
                False,
                reason="missing runtime binding",
            )
        )

    suggestions = api.get(f"/v1/governance/profiles/{PROFILE_NAME}/suggestions")
    suggestions_list = suggestions if isinstance(suggestions, list) else []
    proposal_summary = find_pending_demo_proposals(suggestions_list)
    checks.append(
        check(
            "ai_inbox_pending_proposals",
            not proposal_summary["missing_aliases"],
            **proposal_summary,
        )
    )

    walkthrough = load_guided_walkthrough()
    walkthrough_info = walkthrough_summary(walkthrough)
    checks.append(
        check(
            "walkthrough_contract",
            walkthrough_info["tabs"] == ["Playground", "AI Inbox", "Schema & Snapshots"]
            and walkthrough_info["demo_proposals"] == 4,
            **walkthrough_info,
        )
    )

    failed = [item for item in checks if item["status"] != "passed"]
    status = "passed" if not failed else "failed"
    return {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "demo": {
            "profile": PROFILE_NAME,
            "binding_name": BINDING_NAME,
            "binding_id": binding_id,
            "index": INDEX_NAME,
            "runtime_alias": RUNTIME_ALIAS,
            "query": DEMO_QUERY,
            "ui_url": config.ui_url,
            "api_url": config.api_url,
            "elasticsearch_url": config.elasticsearch_url,
        },
        "summary": {
            "checks_total": len(checks),
            "checks_passed": len(checks) - len(failed),
            "checks_failed": len(failed),
            "warnings_total": len(warnings),
            "terms_count": terms_count,
            "source_documents": source_count,
            "pending_demo_proposals": len(proposal_summary["pending_aliases"]),
            "canonical_values": sorted(canonical_values),
        },
        "checks": checks,
        "warnings": warnings,
        "walkthrough": {
            "tabs": walkthrough_info["tabs"],
            "steps": walkthrough.get("guided_steps", []),
        },
        "safety": {
            "read_only_smoke": True,
            "database_mutation_enabled": False,
            "elasticsearch_mutation_enabled": False,
            "runtime_mutation_enabled": False,
            "legacy_write_tools_enabled_by_default": False,
            "read_only_smoke_endpoints": list(READ_ONLY_ENDPOINTS),
        },
    }


def print_human_summary(report: dict[str, Any]) -> None:
    """Print a concise operator-facing tour summary."""

    if report["status"] == "planned":
        print("SkeinRank demo product tour plan")
        print(f"  UI: {report['demo']['ui_url']}")
        print(f"  Query: {report['demo']['query']}")
        print("  Tabs: " + ", ".join(report["walkthrough"]["tabs"]))
        print("  Commands:")
        for name, command in report["commands"].items():
            print(f"    {name}: {command}")
        return

    summary = report["summary"]
    print("SkeinRank demo product tour smoke")
    print(f"  Status: {report['status']}")
    print(
        "  Checks: {passed}/{total} passed, warnings={warnings}".format(
            passed=summary["checks_passed"],
            total=summary["checks_total"],
            warnings=summary["warnings_total"],
        )
    )
    print(f"  UI: {report['demo']['ui_url']}")
    print(f"  Query: {report['demo']['query']}")
    print("  Canonical values: " + (", ".join(summary["canonical_values"]) or "-"))
    print(f"  Pending demo proposals: {summary['pending_demo_proposals']}")
    print("  Suggested path:")
    for step in report["walkthrough"]["steps"]:
        print(f"    {step.get('order')}. {step.get('tab')}: {step.get('action')}")

    failed = [item for item in report["checks"] if item["status"] != "passed"]
    if failed:
        print("  Failed checks:")
        for item in failed:
            print(f"    - {item['name']}: {item}")


def write_report(path: Path, report: dict[str, Any]) -> None:
    """Write a stable JSON report file."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def run(config: DemoTourConfig) -> dict[str, Any]:
    """Build a plan or execute the smoke check."""

    if config.plan_only:
        return build_plan(config)
    return run_smoke(config)


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint."""

    try:
        config = parse_args(argv)
        report = run(config)
        if config.write_report is not None:
            write_report(config.write_report, report)
            print(f"Wrote demo tour report: {config.write_report}")
        print_human_summary(report)
        return 0 if report["status"] in {"planned", "passed"} else 1
    except DemoSeedError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
