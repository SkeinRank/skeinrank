"""Containerized benchmark integration harness for platform ops fixtures.

The deterministic 48A benchmark proves the governed agent workflow in-process.
This 48C harness adds full-stack integration checks for the Docker Compose dev
stack: PostgreSQL, Governance API, and Elasticsearch/OpenSearch.

No OpenRouter calls are made here. The harness seeds benchmark state into the
containerized database, indexes benchmark documents into Elasticsearch, exercises
read-only HTTP evidence/query-plan endpoints, and writes a JSON stack report.
"""

from __future__ import annotations

import argparse
import http.client
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from sqlalchemy.exc import OperationalError

from .benchmark import (
    DEFAULT_BENCHMARK_NAME,
    DEFAULT_PROFILE_NAME,
    BenchmarkError,
    _read_json,
    _read_jsonl,
    _run_with_session,
    reset_benchmark_state,
    resolve_benchmark_paths,
    run_benchmark_evaluation,
    seed_benchmark_state,
    write_report,
)

STACK_REPORT_FORMAT_VERSION = "skeinrank.benchmark_stack_report.v1"
DEFAULT_API_URL = "http://127.0.0.1:8010"
DEFAULT_ELASTICSEARCH_URL = "http://127.0.0.1:19200"
DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_PASSWORD = "change-me"
DEFAULT_STACK_REPORT_NAME = "platform_ops_v1-stack-report.json"


class BenchmarkStackError(RuntimeError):
    """Raised for user-facing full-stack benchmark errors."""


def wait_for_stack(
    *,
    api_url: str = DEFAULT_API_URL,
    elasticsearch_url: str = DEFAULT_ELASTICSEARCH_URL,
    timeout_seconds: int = 120,
    poll_interval_seconds: float = 2.0,
) -> dict[str, Any]:
    """Wait until Governance API and Elasticsearch are reachable."""

    deadline = time.monotonic() + timeout_seconds
    last_error = ""
    while time.monotonic() < deadline:
        try:
            health = _http_json("GET", f"{api_url.rstrip('/')}/healthz")
            es_root = _http_json("GET", elasticsearch_url.rstrip("/"))
            if health.get("status") == "ok" and isinstance(es_root, dict):
                return {
                    "format_version": "skeinrank.benchmark_stack_wait.v1",
                    "status": "ready",
                    "api_url": api_url,
                    "elasticsearch_url": elasticsearch_url,
                    "healthz": health,
                    "elasticsearch": {
                        "cluster_name": es_root.get("cluster_name"),
                        "version": (es_root.get("version") or {}).get("number"),
                    },
                }
        except BenchmarkStackError as exc:
            last_error = str(exc)
        time.sleep(poll_interval_seconds)
    raise BenchmarkStackError(
        "Timed out waiting for benchmark stack. "
        f"api_url={api_url} elasticsearch_url={elasticsearch_url} last_error={last_error}"
    )


def reset_stack_benchmark(
    *,
    database_url: str | None,
    elasticsearch_url: str = DEFAULT_ELASTICSEARCH_URL,
    benchmark_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Delete benchmark DB state and remove the benchmark Elasticsearch index."""

    paths = resolve_benchmark_paths(benchmark_dir)
    seed_payload = _read_json(paths.seed_dictionary)
    binding_payload = _require_mapping(seed_payload.get("binding"), "binding")
    index_name = str(binding_payload["index_name"])
    db_payload = _run_stack_with_session(
        database_url,
        lambda session: reset_benchmark_state(
            session, profile_name=DEFAULT_PROFILE_NAME
        ),
    )
    es_payload = _delete_elasticsearch_index(
        elasticsearch_url=elasticsearch_url,
        index_name=index_name,
    )
    return {
        "format_version": "skeinrank.benchmark_stack_reset.v1",
        "status": "reset",
        "database": db_payload,
        "elasticsearch": es_payload,
    }


def seed_stack_benchmark(
    *,
    database_url: str | None,
    elasticsearch_url: str = DEFAULT_ELASTICSEARCH_URL,
    benchmark_dir: str | Path | None = None,
    reset_first: bool = False,
) -> dict[str, Any]:
    """Seed governance DB fixtures and index benchmark documents in Elasticsearch."""

    paths = resolve_benchmark_paths(benchmark_dir)
    db_payload = _run_stack_with_session(
        database_url,
        lambda session: seed_benchmark_state(
            session, paths=paths, reset_first=reset_first
        ),
    )
    es_payload = index_benchmark_documents(
        elasticsearch_url=elasticsearch_url,
        benchmark_dir=paths.root,
    )
    return {
        "format_version": "skeinrank.benchmark_stack_seed.v1",
        "status": "seeded",
        "database": db_payload,
        "elasticsearch": es_payload,
    }


def index_benchmark_documents(
    *,
    elasticsearch_url: str = DEFAULT_ELASTICSEARCH_URL,
    benchmark_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Create a benchmark Elasticsearch index and load corpus documents."""

    paths = resolve_benchmark_paths(benchmark_dir)
    seed_payload = _read_json(paths.seed_dictionary)
    binding_payload = _require_mapping(seed_payload.get("binding"), "binding")
    index_name = str(binding_payload["index_name"])
    corpus = _read_jsonl(paths.corpus)

    _delete_elasticsearch_index(
        elasticsearch_url=elasticsearch_url, index_name=index_name
    )
    _http_json(
        "PUT",
        _join_url(elasticsearch_url, index_name),
        {
            "mappings": {
                "properties": {
                    "benchmark": {"type": "keyword"},
                    "source_id": {"type": "keyword"},
                    "source_type": {"type": "keyword"},
                    "title": {"type": "text"},
                    "body": {"type": "text"},
                    "created_at": {"type": "date"},
                }
            }
        },
    )
    indexed = 0
    for document in corpus:
        source_id = str(document["source_id"])
        payload = {
            "benchmark": DEFAULT_BENCHMARK_NAME,
            "source_id": source_id,
            "source_type": str(document.get("source_type") or "document"),
            "title": str(document.get("title") or ""),
            "body": str(document.get("body") or ""),
            "created_at": "2026-05-25T00:00:00Z",
        }
        path = f"{index_name}/_doc/{urllib.parse.quote(source_id, safe='')}"
        _http_json("PUT", _join_url(elasticsearch_url, path), payload)
        indexed += 1
    _http_json("POST", _join_url(elasticsearch_url, f"{index_name}/_refresh"))
    return {
        "status": "indexed",
        "index_name": index_name,
        "documents_indexed": indexed,
    }


def run_stack_evaluation(
    *,
    database_url: str | None,
    api_url: str = DEFAULT_API_URL,
    elasticsearch_url: str = DEFAULT_ELASTICSEARCH_URL,
    benchmark_dir: str | Path | None = None,
    out: str | Path | None = None,
    username: str = DEFAULT_ADMIN_USERNAME,
    password: str = DEFAULT_ADMIN_PASSWORD,
) -> dict[str, Any]:
    """Run deterministic benchmark and stack HTTP/Elasticsearch checks."""

    paths = resolve_benchmark_paths(benchmark_dir)
    base_report = _run_stack_with_session(
        database_url,
        lambda session: run_benchmark_evaluation(session, paths=paths),
    )
    token = _login(api_url=api_url, username=username, password=password)
    api_checks = _run_api_checks(api_url=api_url, token=token)
    evidence_checks = _run_evidence_checks(
        api_url=api_url,
        token=token,
        binding_id=int(base_report["binding_id"]),
        expected_payload=_read_json(paths.expected_aliases),
    )
    runtime_checks = _run_http_runtime_checks(
        api_url=api_url,
        token=token,
        binding_id=int(base_report["binding_id"]),
        golden_queries=_read_jsonl(paths.golden_queries),
    )
    es_checks = _run_elasticsearch_index_checks(
        elasticsearch_url=elasticsearch_url,
        benchmark_dir=paths.root,
    )
    checks = [*api_checks, *evidence_checks, *runtime_checks, *es_checks]
    status = (
        "passed"
        if base_report.get("status") == "passed"
        and all(item.get("status") == "passed" for item in checks)
        else "failed"
    )
    report = {
        "format_version": STACK_REPORT_FORMAT_VERSION,
        "benchmark_name": DEFAULT_BENCHMARK_NAME,
        "status": status,
        "api_url": api_url,
        "elasticsearch_url": elasticsearch_url,
        "base_benchmark": {
            "status": base_report.get("status"),
            "scores": base_report.get("scores"),
            "counts": base_report.get("counts"),
            "quality": base_report.get("quality"),
            "proposal_quality": base_report.get("proposal_quality"),
            "snapshot": base_report.get("snapshot"),
        },
        "checks": checks,
        "evidence_checks": evidence_checks,
        "runtime_checks": runtime_checks,
    }
    output_path = (
        Path(out).expanduser().resolve() if out else _default_stack_report(paths)
    )
    write_report(report, output_path)
    return report | {"report": str(output_path)}


def _run_stack_with_session(database_url: str | None, callback: Any) -> Any:
    try:
        return _run_with_session(database_url, callback)
    except ModuleNotFoundError as exc:
        if exc.name == "psycopg":
            raise BenchmarkStackError(
                "PostgreSQL benchmark stack requires the local psycopg driver. "
                "Run `cd packages/skeinrank-governance-api && poetry install` "
                "after applying this patch, then retry the benchmark-stack command."
            ) from exc
        raise
    except OperationalError as exc:
        message = str(exc)
        if "password authentication failed" in message:
            raise BenchmarkStackError(
                "PostgreSQL benchmark stack authentication failed. This usually means "
                "a stale Docker volume was created with different POSTGRES_* values. "
                "Run `make benchmark-stack-prune-containers` and then "
                "`make benchmark-stack-up` to recreate the isolated benchmark stack."
            ) from exc
        raise BenchmarkStackError(
            "PostgreSQL benchmark stack database connection failed: " + message
        ) from exc


def _run_api_checks(*, api_url: str, token: str) -> list[dict[str, Any]]:
    health = _http_json("GET", f"{api_url.rstrip('/')}/healthz")
    schema = _http_json("GET", f"{api_url.rstrip('/')}/schema/health")
    metrics = _http_text("GET", f"{api_url.rstrip('/')}/metrics")
    return [
        _check_item(
            "api_healthz_ok",
            health.get("status") == "ok",
            "Governance API /healthz is ok.",
            {"status": health.get("status")},
        ),
        _check_item(
            "api_schema_health_ok",
            bool(schema.get("ok")) and bool(schema.get("current_matches_head")),
            "Governance API schema health matches Alembic head.",
            {
                "ok": schema.get("ok"),
                "current_revision": schema.get("current_revision"),
                "head_revision": schema.get("head_revision"),
                "current_matches_head": schema.get("current_matches_head"),
            },
        ),
        _check_item(
            "api_metrics_available",
            "skeinrank_database_up" in metrics,
            "Governance API /metrics exposes operational metrics.",
            {"contains_skeinrank_database_up": "skeinrank_database_up" in metrics},
        ),
    ]


def _run_evidence_checks(
    *,
    api_url: str,
    token: str,
    binding_id: int,
    expected_payload: dict[str, Any],
) -> list[dict[str, Any]]:
    expected = _require_list(
        expected_payload.get("expected_new_aliases"), "expected_new_aliases"
    )
    checks: list[dict[str, Any]] = []
    for item in expected:
        item = _require_mapping(item, "expected_new_aliases[]")
        alias = str(item["alias"])
        canonical = str(item["canonical"])
        response = _http_json(
            "POST",
            f"{api_url.rstrip('/')}/v1/governance/elasticsearch/bindings/{binding_id}/evidence",
            {
                "query": alias,
                "canonical_value": canonical,
                "max_documents": 3,
                "context_chars": 80,
            },
            token=token,
        )
        documents = response.get("documents") if isinstance(response, dict) else None
        checks.append(
            _check_item(
                f"evidence_found_for_{alias}",
                isinstance(documents, list) and len(documents) > 0,
                f"Elasticsearch evidence endpoint returned documents for alias {alias}.",
                {
                    "alias": alias,
                    "canonical": canonical,
                    "documents": len(documents or []),
                    "warnings": response.get("warnings", []),
                },
            )
        )
    return checks


def _run_http_runtime_checks(
    *,
    api_url: str,
    token: str,
    binding_id: int,
    golden_queries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for item in golden_queries:
        query = str(item["query"])
        expected = sorted(str(value) for value in item.get("expected_canonicals") or [])
        response = _http_json(
            "POST",
            f"{api_url.rstrip('/')}/v1/query/plan",
            {"binding_id": binding_id, "query": query, "include_evidence": True},
            token=token,
        )
        found = sorted(str(value) for value in response.get("canonical_values") or [])
        missing = sorted(set(expected) - set(found))
        checks.append(
            _check_item(
                f"query_plan_matches_{_safe_check_name(query)}",
                not missing,
                f"HTTP query plan matched expected canonicals for {query!r}.",
                {
                    "query": query,
                    "expected": expected,
                    "found": found,
                    "missing": missing,
                },
            )
        )
    return checks


def _run_elasticsearch_index_checks(
    *,
    elasticsearch_url: str,
    benchmark_dir: str | Path | None,
) -> list[dict[str, Any]]:
    paths = resolve_benchmark_paths(benchmark_dir)
    seed_payload = _read_json(paths.seed_dictionary)
    binding_payload = _require_mapping(seed_payload.get("binding"), "binding")
    index_name = str(binding_payload["index_name"])
    response = _http_json(
        "POST",
        _join_url(elasticsearch_url, f"{index_name}/_count"),
        {"query": {"term": {"benchmark": DEFAULT_BENCHMARK_NAME}}},
    )
    expected_count = len(_read_jsonl(paths.corpus))
    actual_count = int(response.get("count", 0))
    return [
        _check_item(
            "elasticsearch_corpus_indexed",
            actual_count == expected_count,
            "Benchmark corpus is indexed in Elasticsearch.",
            {
                "index_name": index_name,
                "expected": expected_count,
                "actual": actual_count,
            },
        )
    ]


def _login(*, api_url: str, username: str, password: str) -> str:
    payload = _http_json(
        "POST",
        f"{api_url.rstrip('/')}/v1/auth/login",
        {"username": username, "password": password},
    )
    token = payload.get("access_token") if isinstance(payload, dict) else None
    if not isinstance(token, str) or not token:
        raise BenchmarkStackError("Login succeeded but no access_token was returned.")
    return token


def _delete_elasticsearch_index(
    *, elasticsearch_url: str, index_name: str
) -> dict[str, Any]:
    try:
        _http_json("DELETE", _join_url(elasticsearch_url, index_name))
        deleted = True
    except BenchmarkStackError as exc:
        if "HTTP 404" not in str(exc):
            raise
        deleted = False
    return {"status": "deleted" if deleted else "not_found", "index_name": index_name}


def _default_stack_report(paths: Any) -> Path:
    return Path(paths.root) / "reports" / DEFAULT_STACK_REPORT_NAME


def _http_json(
    method: str,
    url: str,
    payload: dict[str, Any] | None = None,
    *,
    token: str | None = None,
    timeout: int = 20,
) -> dict[str, Any]:
    text = _http_text(method, url, payload, token=token, timeout=timeout)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise BenchmarkStackError(f"Invalid JSON response from {url}: {exc}") from exc
    if not isinstance(parsed, dict):
        raise BenchmarkStackError(f"Expected JSON object from {url}")
    return parsed


def _http_text(
    method: str,
    url: str,
    payload: dict[str, Any] | None = None,
    *,
    token: str | None = None,
    timeout: int = 20,
) -> str:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise BenchmarkStackError(f"HTTP {exc.code} from {url}: {body}") from exc
    except urllib.error.URLError as exc:
        raise BenchmarkStackError(f"Could not reach {url}: {exc}") from exc
    except http.client.RemoteDisconnected as exc:
        raise BenchmarkStackError(
            f"Could not reach {url}: remote end closed connection without response"
        ) from exc


def _join_url(base_url: str, path: str) -> str:
    return base_url.rstrip("/") + "/" + path.lstrip("/")


def _safe_check_name(value: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in value.lower()).strip("_")[:60]


def _check_item(
    name: str,
    passed: bool,
    message: str,
    details: dict[str, Any],
) -> dict[str, Any]:
    return {
        "name": name,
        "status": "passed" if passed else "failed",
        "message": message,
        "details": details,
    }


def _require_mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise BenchmarkStackError(f"{name} must be a JSON object")
    return value


def _require_list(value: Any, name: str) -> list[Any]:
    if not isinstance(value, list):
        raise BenchmarkStackError(f"{name} must be a JSON array")
    return value


def _print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def build_arg_parser() -> argparse.ArgumentParser:
    """Build the stack benchmark CLI parser."""

    parser = argparse.ArgumentParser(
        prog="skeinrank-governance-benchmark-stack",
        description="Run containerized SkeinRank benchmark integration checks.",
    )
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--benchmark-dir", default=None)
    parser.add_argument("--api-url", default=DEFAULT_API_URL)
    parser.add_argument("--elasticsearch-url", default=DEFAULT_ELASTICSEARCH_URL)
    parser.add_argument("--admin-username", default=DEFAULT_ADMIN_USERNAME)
    parser.add_argument("--admin-password", default=DEFAULT_ADMIN_PASSWORD)
    subparsers = parser.add_subparsers(dest="command", required=True)
    wait_parser = subparsers.add_parser("wait", help="Wait for API and ES readiness.")
    wait_parser.add_argument("--timeout-seconds", type=int, default=120)
    wait_parser.add_argument("--poll-interval-seconds", type=float, default=2.0)
    subparsers.add_parser("reset", help="Reset DB benchmark state and ES index.")
    seed_parser = subparsers.add_parser(
        "seed", help="Seed DB benchmark state and ES docs."
    )
    seed_parser.add_argument("--reset", action="store_true")
    index_parser = subparsers.add_parser(
        "index", help="Index benchmark corpus into ES only."
    )
    index_parser.add_argument("--reset", action="store_true")
    eval_parser = subparsers.add_parser(
        "eval", help="Run full stack benchmark evaluation."
    )
    eval_parser.add_argument("--out", default=None)
    report_parser = subparsers.add_parser(
        "report", help="Print stack benchmark report."
    )
    report_parser.add_argument("--file", default=None)
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        paths = resolve_benchmark_paths(args.benchmark_dir)
        if args.command == "wait":
            _print_json(
                wait_for_stack(
                    api_url=args.api_url,
                    elasticsearch_url=args.elasticsearch_url,
                    timeout_seconds=args.timeout_seconds,
                    poll_interval_seconds=args.poll_interval_seconds,
                )
            )
            return 0
        if args.command == "reset":
            _print_json(
                reset_stack_benchmark(
                    database_url=args.database_url,
                    elasticsearch_url=args.elasticsearch_url,
                    benchmark_dir=paths.root,
                )
            )
            return 0
        if args.command == "seed":
            _print_json(
                seed_stack_benchmark(
                    database_url=args.database_url,
                    elasticsearch_url=args.elasticsearch_url,
                    benchmark_dir=paths.root,
                    reset_first=args.reset,
                )
            )
            return 0
        if args.command == "index":
            if args.reset:
                seed_payload = _read_json(paths.seed_dictionary)
                binding_payload = _require_mapping(
                    seed_payload.get("binding"), "binding"
                )
                _delete_elasticsearch_index(
                    elasticsearch_url=args.elasticsearch_url,
                    index_name=str(binding_payload["index_name"]),
                )
            _print_json(
                index_benchmark_documents(
                    elasticsearch_url=args.elasticsearch_url,
                    benchmark_dir=paths.root,
                )
            )
            return 0
        if args.command == "eval":
            report = run_stack_evaluation(
                database_url=args.database_url,
                api_url=args.api_url,
                elasticsearch_url=args.elasticsearch_url,
                benchmark_dir=paths.root,
                out=args.out,
                username=args.admin_username,
                password=args.admin_password,
            )
            _print_json(
                {
                    "status": report["status"],
                    "report": report["report"],
                    "checks_total": len(report["checks"]),
                    "checks_failed": sum(
                        1 for item in report["checks"] if item["status"] != "passed"
                    ),
                    "base_scores": report["base_benchmark"]["scores"],
                }
            )
            return 0 if report["status"] == "passed" else 1
        if args.command == "report":
            report_path = (
                Path(args.file).expanduser().resolve()
                if args.file
                else _default_stack_report(paths)
            )
            if not report_path.exists():
                raise BenchmarkStackError(
                    f"Stack benchmark report not found: {report_path}"
                )
            print(report_path.read_text(encoding="utf-8"), end="")
            return 0
        parser.error(f"Unsupported command: {args.command}")
        return 2
    except (BenchmarkError, BenchmarkStackError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
