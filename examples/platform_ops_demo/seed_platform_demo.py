#!/usr/bin/env python3
"""Seed a local SkeinRank Docker stack with platform preview data.

The script is intentionally stdlib-only so users can run it from a clean
checkout after starting the Docker Compose dev stack.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_API_URL = "http://127.0.0.1:8010"
DEFAULT_ELASTICSEARCH_URL = "http://127.0.0.1:19200"
DEFAULT_UI_URL = "http://127.0.0.1:5173"
DEFAULT_USERNAME = "admin"
DEFAULT_PASSWORD = "change-me"
PROFILE_NAME = "platform_ops"
INDEX_NAME = "platform_knowledge_base"
RUNTIME_ALIAS = "platform_knowledge_base_search"
BINDING_NAME = "Production knowledge base"
DEMO_QUERY = "k8s pg timeout during phoenix rollout"
TERMINAL_JOB_STATUSES = {"succeeded", "failed", "cancelled"}
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLE_DIR = Path(__file__).resolve().parent
DICTIONARY_PATH = EXAMPLE_DIR / "platform_ops_dictionary.json"
BULK_PATH = EXAMPLE_DIR / "platform_knowledge_base.ndjson"


class DemoSeedError(RuntimeError):
    """Raised when the demo seed flow cannot continue."""


@dataclass(frozen=True)
class DemoConfig:
    """Runtime configuration for the demo seed script."""

    api_url: str
    elasticsearch_url: str
    ui_url: str
    username: str
    password: str
    wait_timeout_seconds: int
    poll_interval_seconds: float
    reset: bool
    skip_enrichment: bool
    force_non_local: bool
    status_only: bool


class JsonHttpClient:
    """Tiny JSON HTTP helper based on urllib."""

    def __init__(self, base_url: str, token: str | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token

    def get(self, path: str) -> Any:
        return self.request("GET", path)

    def post(self, path: str, payload: Any | None = None) -> Any:
        return self.request("POST", path, payload=payload)

    def put(self, path: str, payload: Any | None = None) -> Any:
        return self.request("PUT", path, payload=payload)

    def delete(self, path: str, *, ignore_404: bool = False) -> Any:
        try:
            return self.request("DELETE", path)
        except DemoSeedError as exc:
            if ignore_404 and "HTTP 404" in str(exc):
                return None
            raise

    def request(self, method: str, path: str, payload: Any | None = None) -> Any:
        url = self._url(path)
        headers = {"Accept": "application/json"}
        data: bytes | None = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(payload).encode("utf-8")
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        request = urllib.request.Request(
            url,
            data=data,
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                body = response.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise DemoSeedError(f"HTTP {exc.code} {method} {url}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise DemoSeedError(f"Cannot reach {url}: {exc.reason}") from exc

        if not body:
            return None
        try:
            return json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            return body.decode("utf-8", errors="replace")

    def bulk(self, path: str, payload_path: Path) -> Any:
        url = self._url(path)
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/x-ndjson",
        }
        data = payload_path.read_bytes()
        request = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                body = response.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise DemoSeedError(f"HTTP {exc.code} POST {url}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise DemoSeedError(f"Cannot reach {url}: {exc.reason}") from exc
        return json.loads(body.decode("utf-8"))

    def _url(self, path: str) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            return path
        if not path.startswith("/"):
            path = f"/{path}"
        return f"{self.base_url}{path}"


def is_local_url(url: str) -> bool:
    """Return True when a URL points at a local development host."""

    parsed = urllib.parse.urlparse(url)
    hostname = parsed.hostname
    return hostname in LOCAL_HOSTS


def quote_index_name(index_name: str) -> str:
    """Quote an Elasticsearch index/alias path segment."""

    return urllib.parse.quote(index_name, safe="")


def load_json_file(path: Path) -> dict[str, Any]:
    """Read a JSON object from disk."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise DemoSeedError(f"Expected JSON object in {path}")
    return payload


def count_bulk_documents(path: Path) -> int:
    """Count documents in a newline-delimited Elasticsearch bulk file."""

    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line]
    if len(lines) % 2 != 0:
        raise DemoSeedError(
            f"Bulk file must contain action/document line pairs: {path}"
        )
    return len(lines) // 2


def dictionary_summary(payload: dict[str, Any]) -> dict[str, int]:
    """Return simple dictionary counters used in CLI output and tests."""

    terms = payload.get("terms") or []
    aliases_total = sum(len(term.get("aliases") or []) for term in terms)
    return {
        "terms": len(terms),
        "aliases": aliases_total,
        "profile_stop_list": len(payload.get("profile_stop_list") or []),
        "global_stop_list": len(payload.get("global_stop_list") or []),
    }


def build_index_mapping() -> dict[str, Any]:
    """Return the demo Elasticsearch index settings and mappings."""

    return {
        "settings": {
            "number_of_shards": 1,
            "number_of_replicas": 0,
        },
        "mappings": {
            "properties": {
                "title": {"type": "text"},
                "body": {"type": "text"},
                "team": {"type": "keyword"},
                "doc_type": {"type": "keyword"},
                "service": {"type": "keyword"},
                "environment": {"type": "keyword"},
                "updated_at": {"type": "date"},
            }
        },
    }


def build_binding_payload() -> dict[str, Any]:
    """Return the demo governance binding payload."""

    return {
        "name": BINDING_NAME,
        "profile_name": PROFILE_NAME,
        "description": (
            "Demo binding from the platform_ops terminology profile to the "
            "platform_knowledge_base Elasticsearch index."
        ),
        "index_name": INDEX_NAME,
        "text_fields": ["title", "body"],
        "target_field": "skeinrank",
        "filter_field": "team",
        "filter_value": "platform",
        "timestamp_field": "updated_at",
        "time_window_days": 3650,
        "mode": "write",
        "write_strategy": "reindex_alias_swap",
        "is_enabled": True,
    }


def find_existing_binding(bindings: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Find the demo binding in a binding list response."""

    for binding in bindings:
        if (
            binding.get("name") == BINDING_NAME
            and binding.get("profile_name") == PROFILE_NAME
            and binding.get("index_name") == INDEX_NAME
        ):
            return binding
    return None


def find_existing_suggestion(
    suggestions: list[dict[str, Any]],
    *,
    canonical_value: str,
    alias_value: str,
) -> dict[str, Any] | None:
    """Find a pending demo suggestion to avoid duplicate seed records."""

    normalized_alias = alias_value.strip().lower()
    normalized_canonical = canonical_value.strip().lower()
    for suggestion in suggestions:
        if suggestion.get("status") != "pending":
            continue
        if (suggestion.get("alias_value") or "").strip().lower() != normalized_alias:
            continue
        if (
            suggestion.get("canonical_value") or ""
        ).strip().lower() == normalized_canonical:
            return suggestion
    return None


def parse_args(argv: list[str] | None = None) -> DemoConfig:
    """Parse CLI arguments into a DemoConfig."""

    parser = argparse.ArgumentParser(
        description="Seed the local SkeinRank platform preview with demo data.",
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
        help=f"UI URL used in final output. Default: {DEFAULT_UI_URL}",
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
        "--wait-timeout",
        type=int,
        default=int(os.getenv("SKEINRANK_DEMO_WAIT_TIMEOUT", "120")),
        help="Seconds to wait for an enrichment job to finish.",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=float(os.getenv("SKEINRANK_DEMO_POLL_INTERVAL", "2")),
        help="Seconds between enrichment job polls.",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete existing demo Elasticsearch indices before seeding.",
    )
    parser.add_argument(
        "--skip-enrichment",
        action="store_true",
        help="Seed profile/binding data but do not start the enrichment job.",
    )
    parser.add_argument(
        "--force-non-local",
        action="store_true",
        help="Allow non-local API/Elasticsearch URLs. Use with care.",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Only print current demo status. Does not write data.",
    )
    args = parser.parse_args(argv)
    return DemoConfig(
        api_url=args.api_url,
        elasticsearch_url=args.elasticsearch_url,
        ui_url=args.ui_url,
        username=args.username,
        password=args.password,
        wait_timeout_seconds=args.wait_timeout,
        poll_interval_seconds=args.poll_interval,
        reset=args.reset,
        skip_enrichment=args.skip_enrichment,
        force_non_local=args.force_non_local,
        status_only=args.status,
    )


def ensure_safe_urls(config: DemoConfig) -> None:
    """Prevent accidental seeding of non-local services by default."""

    if config.force_non_local:
        return
    unsafe = [
        url
        for url in (config.api_url, config.elasticsearch_url)
        if not is_local_url(url)
    ]
    if unsafe:
        raise DemoSeedError(
            "Refusing to seed non-local services by default: "
            f"{', '.join(unsafe)}. Pass --force-non-local to override."
        )


def print_step(message: str) -> None:
    """Print one high-level progress step."""

    print(f"==> {message}")


def authenticate(api: JsonHttpClient, config: DemoConfig) -> str:
    """Login and return a bearer token."""

    response = api.post(
        "/v1/auth/login",
        {"username": config.username, "password": config.password},
    )
    token = response.get("access_token") if isinstance(response, dict) else None
    if not token:
        raise DemoSeedError("Login did not return access_token.")
    return str(token)


def reset_demo_indices(es: JsonHttpClient) -> None:
    """Delete existing demo indices before rebuilding the preview state."""

    print_step("Resetting demo Elasticsearch indices")
    indices = es.get(f"/_cat/indices/{INDEX_NAME}*?format=json")
    if not isinstance(indices, list):
        return
    for item in indices:
        index_name = item.get("index") if isinstance(item, dict) else None
        if not index_name:
            continue
        es.delete(f"/{quote_index_name(str(index_name))}", ignore_404=True)
        print(f"  deleted {index_name}")


def create_demo_index(es: JsonHttpClient) -> None:
    """Create a fresh source index and load demo documents."""

    print_step(f"Creating Elasticsearch index {INDEX_NAME}")
    es.delete(f"/{quote_index_name(INDEX_NAME)}", ignore_404=True)
    es.put(f"/{quote_index_name(INDEX_NAME)}", build_index_mapping())

    print_step("Loading platform knowledge-base documents")
    result = es.bulk("/_bulk?refresh=true", BULK_PATH)
    errors = result.get("errors") if isinstance(result, dict) else True
    items = result.get("items", []) if isinstance(result, dict) else []
    if errors:
        raise DemoSeedError(f"Elasticsearch bulk load failed: {result}")
    print(f"  loaded {len(items)} bulk actions")


def import_dictionary(api: JsonHttpClient) -> dict[str, Any]:
    """Import the demo platform_ops dictionary into the governance API."""

    payload = load_json_file(DICTIONARY_PATH)
    summary = dictionary_summary(payload)
    print_step(
        "Importing platform_ops dictionary "
        f"({summary['terms']} terms, {summary['aliases']} aliases)"
    )
    response = api.post("/v1/console/dictionary/import", payload)
    if not isinstance(response, dict):
        raise DemoSeedError("Dictionary import did not return JSON object.")
    return response


def ensure_binding(api: JsonHttpClient) -> dict[str, Any]:
    """Create or reuse the demo Elasticsearch binding."""

    print_step("Ensuring demo Elasticsearch binding")
    bindings = api.get(
        f"/v1/governance/elasticsearch/bindings?profile_name={PROFILE_NAME}"
    )
    if isinstance(bindings, list):
        existing = find_existing_binding(bindings)
        if existing is not None:
            print(f"  reusing binding #{existing['id']}: {BINDING_NAME}")
            return existing
    binding = api.post("/v1/governance/elasticsearch/bindings", build_binding_payload())
    if not isinstance(binding, dict):
        raise DemoSeedError("Binding create did not return JSON object.")
    print(f"  created binding #{binding['id']}: {BINDING_NAME}")
    return binding


def run_demo_checks(api: JsonHttpClient, binding_id: int) -> None:
    """Run dry-run, evidence, query-plan, and canonicalization smoke checks."""

    print_step("Running demo dry-run and evidence checks")
    dry_run = api.post(
        f"/v1/governance/elasticsearch/bindings/{binding_id}/dry-run",
        {"limit": 5},
    )
    documents = dry_run.get("documents", []) if isinstance(dry_run, dict) else []
    print(f"  dry-run documents: {len(documents)}")

    for query, canonical in (
        ("k8s", "kubernetes"),
        ("pg", "postgresql"),
        ("phoenix", "project phoenix"),
    ):
        evidence = api.post(
            f"/v1/governance/elasticsearch/bindings/{binding_id}/evidence",
            {
                "query": query,
                "canonical_value": canonical,
                "max_documents": 5,
                "context_chars": 120,
            },
        )
        docs = evidence.get("documents", []) if isinstance(evidence, dict) else []
        print(f"  evidence {query!r} -> {canonical!r}: {len(docs)} snippets")

    query_plan = api.post(
        "/v1/query/plan",
        {"binding_id": binding_id, "query": DEMO_QUERY, "size": 10},
    )
    canonical_values = (
        query_plan.get("canonical_values", []) if isinstance(query_plan, dict) else []
    )
    print(f"  query plan canonical values: {', '.join(canonical_values) or '-'}")

    canonicalized = api.post(
        "/v1/text/canonicalize",
        {
            "binding_id": binding_id,
            "text": "k8s ingress timeout caused pg pool exhaustion during phoenix canary",
            "mode": "replace",
            "include_evidence": True,
        },
    )
    text = (
        canonicalized.get("canonical_text") if isinstance(canonicalized, dict) else None
    )
    if text:
        print(f"  canonicalized text: {text}")


def ensure_suggestion(
    api: JsonHttpClient,
    existing_suggestions: list[dict[str, Any]],
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Create or reuse a pending suggestion."""

    alias_value = str(payload.get("alias_value") or "")
    canonical_value = str(payload.get("canonical_value") or "")
    existing = find_existing_suggestion(
        existing_suggestions,
        canonical_value=canonical_value,
        alias_value=alias_value,
    )
    if existing is not None:
        print(f"  reusing suggestion #{existing['id']}: {alias_value}")
        return existing
    suggestion = api.post(
        f"/v1/governance/profiles/{PROFILE_NAME}/suggestions", payload
    )
    if not isinstance(suggestion, dict):
        raise DemoSeedError("Suggestion create did not return JSON object.")
    print(f"  created suggestion #{suggestion['id']}: {alias_value}")
    return suggestion


def ensure_demo_suggestions(
    api: JsonHttpClient, binding_id: int
) -> list[dict[str, Any]]:
    """Create demo suggestions and save evidence snapshots."""

    print_step("Creating pending suggestions with evidence snapshots")
    suggestions = api.get(f"/v1/governance/profiles/{PROFILE_NAME}/suggestions")
    existing = suggestions if isinstance(suggestions, list) else []
    payloads = [
        {
            "suggestion_type": "alias",
            "canonical_value": "kubernetes",
            "alias_value": "EKS",
            "slot": "technology",
            "description": "Cloud platform engineers often write EKS in incident notes.",
            "confidence": 0.82,
            "source": "discovery",
            "context": "Found in ticket-005 and cloud platform incident notes.",
        },
        {
            "suggestion_type": "alias",
            "canonical_value": "elasticsearch",
            "alias_value": "OpenSearch",
            "slot": "search_backend",
            "description": (
                "Potential alias from search platform notes; needs evidence "
                "before approval."
            ),
            "confidence": 0.68,
            "source": "discovery",
            "context": "Reviewer requested evidence before accepting OpenSearch as an alias.",
        },
    ]

    created: list[dict[str, Any]] = []
    for payload in payloads:
        suggestion = ensure_suggestion(api, existing, payload)
        created.append(suggestion)
        query = str(payload.get("alias_value") or payload.get("canonical_value"))
        refreshed = api.post(
            f"/v1/governance/profiles/{PROFILE_NAME}/suggestions/{suggestion['id']}"
            "/evidence/refresh",
            {
                "binding_id": binding_id,
                "query": query,
                "max_documents": 5,
                "context_chars": 120,
            },
        )
        evidence = (
            refreshed.get("evidence_snapshot", {})
            if isinstance(refreshed, dict)
            else {}
        )
        docs = evidence.get("documents", []) if isinstance(evidence, dict) else []
        print(f"  evidence for {query!r}: {len(docs)} snippets")
    return created


def start_enrichment_job(api: JsonHttpClient, binding_id: int) -> dict[str, Any]:
    """Start and return an enrichment job."""

    print_step("Starting Elasticsearch enrichment job")
    job = api.post(
        f"/v1/governance/elasticsearch/bindings/{binding_id}/jobs",
        {"alias_name": RUNTIME_ALIAS, "max_documents": 50, "chunk_size": 10},
    )
    if not isinstance(job, dict):
        raise DemoSeedError("Enrichment job start did not return JSON object.")
    print(f"  started job #{job['id']} with alias {RUNTIME_ALIAS}")
    return job


def wait_for_job(
    api: JsonHttpClient, job_id: int, config: DemoConfig
) -> dict[str, Any]:
    """Poll an enrichment job until it reaches a terminal status."""

    deadline = time.monotonic() + config.wait_timeout_seconds
    latest: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        response = api.get(f"/v1/governance/elasticsearch/jobs/{job_id}")
        if not isinstance(response, dict):
            raise DemoSeedError("Job status did not return JSON object.")
        latest = response
        status = str(response.get("status"))
        print(
            "  job #{job_id}: {status} "
            "seen={seen} enriched={enriched} failed={failed}".format(
                job_id=job_id,
                status=status,
                seen=response.get("documents_seen"),
                enriched=response.get("documents_enriched"),
                failed=response.get("documents_failed"),
            )
        )
        if status in TERMINAL_JOB_STATUSES:
            if status != "succeeded":
                raise DemoSeedError(
                    f"Enrichment job #{job_id} ended with status {status}: "
                    f"{response.get('error_message')}"
                )
            return response
        time.sleep(config.poll_interval_seconds)
    raise DemoSeedError(f"Timed out waiting for enrichment job #{job_id}: {latest}")


def print_current_status(api: JsonHttpClient, es: JsonHttpClient) -> None:
    """Print a read-only status summary for an already seeded demo stack."""

    print_step("Current platform preview status")
    try:
        profile_terms = api.get(f"/v1/governance/profiles/{PROFILE_NAME}/terms")
        terms_count = len(profile_terms) if isinstance(profile_terms, list) else 0
    except DemoSeedError:
        terms_count = 0
    try:
        bindings = api.get(
            f"/v1/governance/elasticsearch/bindings?profile_name={PROFILE_NAME}"
        )
        binding = (
            find_existing_binding(bindings) if isinstance(bindings, list) else None
        )
    except DemoSeedError:
        binding = None
    try:
        count = es.get(f"/{quote_index_name(INDEX_NAME)}/_count")
        documents_count = count.get("count", 0) if isinstance(count, dict) else 0
    except DemoSeedError:
        documents_count = 0
    print(f"  profile: {PROFILE_NAME} ({terms_count} terms)")
    print(f"  source index: {INDEX_NAME} ({documents_count} docs)")
    print(f"  binding: #{binding['id']} {BINDING_NAME}" if binding else "  binding: -")


def print_final_summary(
    *,
    config: DemoConfig,
    binding: dict[str, Any],
    job: dict[str, Any] | None,
) -> None:
    """Print a concise success summary for humans."""

    print("\nSkeinRank platform preview seeded successfully.")
    print(f"  UI: {config.ui_url}")
    print(f"  Login: {config.username} / {config.password}")
    print(f"  Profile: {PROFILE_NAME}")
    print(f"  Binding: #{binding['id']} {BINDING_NAME}")
    print(f"  Runtime alias: {RUNTIME_ALIAS}")
    if job is not None:
        print(
            "  Enrichment job: #{id} {status} " "({enriched}/{seen} enriched)".format(
                id=job.get("id"),
                status=job.get("status"),
                enriched=job.get("documents_enriched"),
                seen=job.get("documents_seen"),
            )
        )
    print(f"  Search Playground query: {DEMO_QUERY}")


def run(config: DemoConfig) -> None:
    """Run the full seed flow."""

    ensure_safe_urls(config)
    api_public = JsonHttpClient(config.api_url)
    es = JsonHttpClient(config.elasticsearch_url)

    print_step("Checking local services")
    api_public.get("/livez")
    api_public.get("/readyz")
    es.get("/")

    token = authenticate(api_public, config)
    api = JsonHttpClient(config.api_url, token=token)
    api.get("/v1/auth/me")

    if config.status_only:
        print_current_status(api, es)
        return

    if config.reset:
        reset_demo_indices(es)

    create_demo_index(es)
    import_dictionary(api)
    binding = ensure_binding(api)
    binding_id = int(binding["id"])
    run_demo_checks(api, binding_id)
    ensure_demo_suggestions(api, binding_id)

    finished_job = None
    if not config.skip_enrichment:
        job = start_enrichment_job(api, binding_id)
        finished_job = wait_for_job(api, int(job["id"]), config)

    print_final_summary(config=config, binding=binding, job=finished_job)


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint."""

    try:
        run(parse_args(argv))
    except DemoSeedError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
