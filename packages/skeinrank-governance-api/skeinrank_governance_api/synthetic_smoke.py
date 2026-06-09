"""Deterministic 5k synthetic smoke corpus generator.

The generated corpus supports offline scale smoke checks such as batching,
skip/unchanged accounting, hard-negative pressure, and report plumbing. It is
not a hand-labeled quality benchmark and it does not call OpenRouter,
Elasticsearch, the database, or runtime mutation APIs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SYNTHETIC_SMOKE_PLAN_VERSION = "skeinrank.synthetic_smoke_plan.v1"
SYNTHETIC_SMOKE_DOCUMENT_VERSION = "skeinrank.synthetic_smoke_document.v1"
SYNTHETIC_SMOKE_MANIFEST_VERSION = "skeinrank.synthetic_smoke_manifest.v1"
DEFAULT_BENCHMARK_NAME = "platform_ops_v1"
DEFAULT_DOCUMENT_COUNT = 5000
DEFAULT_BATCH_SIZE = 500
DEFAULT_SEED = 5302

ROLE_SEQUENCE = (
    "semantic_noise",
    "near_duplicate",
    "hard_negative",
    "weak_platform_adjacent",
    "golden_relevant",
)
SOURCE_TYPES = (
    "incident",
    "runbook",
    "support_ticket",
    "log_excerpt",
    "docs_page",
)
DOMAIN_PATTERNS = (
    {
        "alias": "pg",
        "canonical": "postgresql",
        "slot": "database",
        "good": "PostgreSQL replica lag caused connection pool saturation during failover.",
        "hard": "Page generation used the pg abbreviation in a frontend design note.",
        "near": "pg timeout after failover in production cluster with replica health checks.",
    },
    {
        "alias": "k8s",
        "canonical": "kubernetes",
        "slot": "technology",
        "good": "Kubernetes rollout stalled because the namespace service selector changed.",
        "hard": "Customer success prepared a rollout memo for a mobile app launch.",
        "near": "k8s rollout warning after service namespace drift and controller retries.",
    },
    {
        "alias": "rmq",
        "canonical": "rabbitmq",
        "slot": "queue",
        "good": "RabbitMQ queue depth increased after publisher confirms slowed down.",
        "hard": "Risk management quarterly notes used RMQ as a reporting label.",
        "near": "rmq queue backlog on consumer group after deploy window.",
    },
    {
        "alias": "otel",
        "canonical": "opentelemetry",
        "slot": "observability",
        "good": "OpenTelemetry traces lost spans after collector restart.",
        "hard": "Office telemetry dashboard tracked desk occupancy and meeting rooms.",
        "near": "otel trace regression after collector config reload.",
    },
    {
        "alias": "es",
        "canonical": "elasticsearch",
        "slot": "search_engine",
        "good": "Elasticsearch search timeout increased after shard relocation.",
        "hard": "Employee survey export was abbreviated as ES in the HR backlog.",
        "near": "es indexing lag and search timeout on platform docs.",
    },
    {
        "alias": "prom",
        "canonical": "prometheus",
        "slot": "observability",
        "good": "Prometheus scrape target went stale during service discovery churn.",
        "hard": "Promotion calendar shortened to prom in a marketing spreadsheet.",
        "near": "prom alert fired after scrape timeout and target relabeling.",
    },
    {
        "alias": "lk",
        "canonical": "loki",
        "slot": "observability",
        "good": "Loki query latency increased after log label cardinality spike.",
        "hard": "Location key LK appeared in a facilities export.",
        "near": "lk logs missing for namespace after prom alert correlation.",
    },
    {
        "alias": "svc",
        "canonical": "service",
        "slot": "kubernetes_object",
        "good": "Service endpoint routing failed after selector drift.",
        "hard": "Support voice channel was abbreviated SVC in the contact-center report.",
        "near": "svc selector mismatch in namespace after k8s rollout.",
    },
    {
        "alias": "ns",
        "canonical": "namespace",
        "slot": "kubernetes_object",
        "good": "Namespace quota blocked a deployment rollout.",
        "hard": "Nameserver migration used ns in DNS planning notes.",
        "near": "ns quota denied pods while svc routing stayed healthy.",
    },
    {
        "alias": "slo",
        "canonical": "service level objective",
        "slot": "reliability",
        "good": "Service level objective burn rate exceeded the paging threshold.",
        "hard": "Sales lead owner abbreviated a CRM column as SLO.",
        "near": "slo burn rate warning after api latency regression.",
    },
)


class SyntheticSmokeError(RuntimeError):
    """Raised for user-facing synthetic smoke generator errors."""


@dataclass(frozen=True)
class SyntheticSmokePaths:
    """Resolved default output paths for the synthetic smoke corpus."""

    root: Path
    corpus: Path
    manifest: Path


def default_benchmark_dir() -> Path:
    """Return the default repository benchmark fixture directory."""

    return (
        Path(__file__).resolve().parents[3]
        / "examples"
        / "benchmarks"
        / "platform_ops_v1"
    )


def resolve_synthetic_smoke_paths(
    path: str | Path | None = None,
) -> SyntheticSmokePaths:
    """Resolve default synthetic smoke output paths."""

    root = Path(path or default_benchmark_dir()).expanduser().resolve()
    output_dir = root / "reports" / "synthetic"
    return SyntheticSmokePaths(
        root=root,
        corpus=output_dir / "platform_ops_v1-5k-corpus.jsonl",
        manifest=output_dir / "platform_ops_v1-5k-manifest.json",
    )


def build_synthetic_smoke_plan(
    *,
    document_count: int = DEFAULT_DOCUMENT_COUNT,
    batch_size: int = DEFAULT_BATCH_SIZE,
    seed: int = DEFAULT_SEED,
    paths: SyntheticSmokePaths | None = None,
) -> dict[str, Any]:
    """Return a dry plan for a 5k synthetic smoke corpus run."""

    _validate_limits(document_count=document_count, batch_size=batch_size)
    paths = paths or resolve_synthetic_smoke_paths()
    role_counts = _planned_role_counts(document_count)
    return {
        "schema_version": SYNTHETIC_SMOKE_PLAN_VERSION,
        "benchmark_name": DEFAULT_BENCHMARK_NAME,
        "status": "planned",
        "document_count": document_count,
        "batch_size": batch_size,
        "batches_total": _ceil_div(document_count, batch_size),
        "seed": seed,
        "roles": role_counts,
        "source_types": list(SOURCE_TYPES),
        "domain_patterns_total": len(DOMAIN_PATTERNS),
        "outputs": {
            "corpus": str(paths.corpus),
            "manifest": str(paths.manifest),
        },
        "scale_smoke_focus": [
            "batch planning",
            "near-duplicate pressure",
            "hard-negative pressure",
            "unchanged-document skip candidates",
            "provider-independent report plumbing",
        ],
        "safety": _offline_safety(),
    }


def generate_synthetic_smoke_corpus(
    *,
    corpus_path: Path,
    manifest_path: Path,
    document_count: int = DEFAULT_DOCUMENT_COUNT,
    batch_size: int = DEFAULT_BATCH_SIZE,
    seed: int = DEFAULT_SEED,
) -> dict[str, Any]:
    """Generate a deterministic synthetic smoke corpus and manifest."""

    _validate_limits(document_count=document_count, batch_size=batch_size)
    corpus_path = corpus_path.expanduser().resolve()
    manifest_path = manifest_path.expanduser().resolve()
    corpus_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    role_counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()
    alias_counts: Counter[str] = Counter()
    skip_candidates = 0
    batch_counts: dict[int, Counter[str]] = {}
    first_source_id: str | None = None
    last_source_id: str | None = None
    digest = hashlib.sha256()

    with corpus_path.open("w", encoding="utf-8") as handle:
        for index in range(document_count):
            document = _synthetic_document(index, batch_size=batch_size, seed=seed)
            line = json.dumps(document, ensure_ascii=False, sort_keys=True)
            handle.write(line + "\n")
            digest.update(line.encode("utf-8"))
            digest.update(b"\n")

            role = str(document["synthetic_role"])
            source_type = str(document["source_type"])
            role_counts[role] += 1
            source_counts[source_type] += 1
            batch_counts.setdefault(int(document["batch_id"]), Counter())[role] += 1
            if document.get("should_skip_unchanged"):
                skip_candidates += 1
            for alias in document.get("aliases", []):
                alias_counts[str(alias)] += 1
            first_source_id = first_source_id or str(document["source_id"])
            last_source_id = str(document["source_id"])

    batches = _batch_manifest(batch_counts=batch_counts, batch_size=batch_size)
    manifest = {
        "schema_version": SYNTHETIC_SMOKE_MANIFEST_VERSION,
        "benchmark_name": DEFAULT_BENCHMARK_NAME,
        "status": "generated",
        "document_count": document_count,
        "batch_size": batch_size,
        "batches_total": len(batches),
        "seed": seed,
        "role_counts": dict(sorted(role_counts.items())),
        "source_type_counts": dict(sorted(source_counts.items())),
        "top_aliases": [
            {"alias": alias, "count": count}
            for alias, count in alias_counts.most_common(10)
        ],
        "unchanged_skip_candidates": skip_candidates,
        "first_source_id": first_source_id,
        "last_source_id": last_source_id,
        "corpus_sha256": digest.hexdigest(),
        "corpus_path": str(corpus_path),
        "batches": batches,
        "safety": _offline_safety(),
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return manifest


def load_synthetic_smoke_manifest(path: str | Path) -> dict[str, Any]:
    """Load an existing synthetic smoke manifest."""

    manifest_path = Path(path).expanduser().resolve()
    if not manifest_path.exists():
        raise SyntheticSmokeError(
            f"Synthetic smoke manifest not found: {manifest_path}"
        )
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != SYNTHETIC_SMOKE_MANIFEST_VERSION:
        raise SyntheticSmokeError(
            "Unexpected synthetic smoke manifest schema: "
            f"{payload.get('schema_version')}"
        )
    return payload


def build_arg_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""

    parser = argparse.ArgumentParser(
        description="Generate a deterministic 5k synthetic smoke corpus."
    )
    parser.add_argument(
        "command", choices=["plan", "generate", "report"], help="Command to run."
    )
    parser.add_argument(
        "--benchmark-dir",
        default=None,
        help="Benchmark fixture directory. Defaults to platform_ops_v1.",
    )
    parser.add_argument(
        "--documents",
        type=int,
        default=DEFAULT_DOCUMENT_COUNT,
        help="Number of synthetic documents to plan or generate.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help="Synthetic batch size for smoke planning.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_SEED,
        help="Deterministic seed recorded in the manifest.",
    )
    parser.add_argument("--out", default=None, help="Output JSONL corpus path.")
    parser.add_argument("--manifest", default=None, help="Output/read manifest path.")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the synthetic smoke CLI."""

    parser = build_arg_parser()
    args = parser.parse_args(argv)
    try:
        paths = resolve_synthetic_smoke_paths(args.benchmark_dir)
        corpus_path = (
            Path(args.out).expanduser().resolve() if args.out else paths.corpus
        )
        manifest_path = (
            Path(args.manifest).expanduser().resolve()
            if args.manifest
            else paths.manifest
        )
        if args.command == "plan":
            print(
                json.dumps(
                    build_synthetic_smoke_plan(
                        document_count=args.documents,
                        batch_size=args.batch_size,
                        seed=args.seed,
                        paths=paths,
                    ),
                    indent=2,
                    ensure_ascii=False,
                )
            )
            return 0
        if args.command == "generate":
            manifest = generate_synthetic_smoke_corpus(
                corpus_path=corpus_path,
                manifest_path=manifest_path,
                document_count=args.documents,
                batch_size=args.batch_size,
                seed=args.seed,
            )
            print(
                json.dumps(
                    {
                        "status": manifest["status"],
                        "schema_version": manifest["schema_version"],
                        "documents_total": manifest["document_count"],
                        "batches_total": manifest["batches_total"],
                        "corpus": str(corpus_path),
                        "manifest": str(manifest_path),
                        "corpus_sha256": manifest["corpus_sha256"],
                        "safety": manifest["safety"],
                    },
                    indent=2,
                    ensure_ascii=False,
                )
            )
            return 0
        print(
            json.dumps(
                load_synthetic_smoke_manifest(manifest_path),
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0
    except SyntheticSmokeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


def _synthetic_document(index: int, *, batch_size: int, seed: int) -> dict[str, Any]:
    role = ROLE_SEQUENCE[index % len(ROLE_SEQUENCE)]
    source_type = SOURCE_TYPES[(index + seed) % len(SOURCE_TYPES)]
    pattern = DOMAIN_PATTERNS[(index + seed) % len(DOMAIN_PATTERNS)]
    doc_number = index + 1
    batch_id = index // batch_size
    alias = str(pattern["alias"])
    canonical = str(pattern["canonical"])
    title = _title_for_role(role=role, pattern=pattern, doc_number=doc_number)
    body = _body_for_role(
        role=role, pattern=pattern, doc_number=doc_number, batch_id=batch_id
    )
    should_skip = role == "near_duplicate" and doc_number % 4 == 0
    return {
        "schema_version": SYNTHETIC_SMOKE_DOCUMENT_VERSION,
        "source_id": f"synthetic-5k-{doc_number:05d}",
        "source_type": source_type,
        "title": title,
        "body": body,
        "synthetic_role": role,
        "batch_id": batch_id,
        "aliases": [alias],
        "canonical_values": [canonical]
        if role in {"golden_relevant", "near_duplicate"}
        else [],
        "slot": pattern["slot"],
        "expected_relevance": 2
        if role == "golden_relevant"
        else 1
        if role == "near_duplicate"
        else 0,
        "hard_negative": role == "hard_negative",
        "should_skip_unchanged": should_skip,
        "metadata": {
            "generator": "skeinrank.synthetic_smoke.v1",
            "ordinal": doc_number,
            "seed": seed,
            "scale_smoke_only": True,
        },
    }


def _title_for_role(*, role: str, pattern: dict[str, str], doc_number: int) -> str:
    label = str(pattern["canonical"]).title()
    if role == "golden_relevant":
        return f"{label} operational note {doc_number:05d}"
    if role == "hard_negative":
        return f"Hard negative for {pattern['alias']} {doc_number:05d}"
    if role == "near_duplicate":
        return f"Near duplicate {pattern['alias']} incident {doc_number:05d}"
    if role == "weak_platform_adjacent":
        return f"Weak adjacent platform note {doc_number:05d}"
    return f"Semantic noise document {doc_number:05d}"


def _body_for_role(
    *, role: str, pattern: dict[str, str], doc_number: int, batch_id: int
) -> str:
    if role == "golden_relevant":
        return (
            f"{pattern['good']} Batch {batch_id} validates that {pattern['alias']} "
            f"can safely point to {pattern['canonical']} for platform operations."
        )
    if role == "hard_negative":
        return (
            f"{pattern['hard']} This row intentionally shares the surface form "
            f"{pattern['alias']} but should not become a governed alias proposal."
        )
    if role == "near_duplicate":
        return (
            f"{pattern['near']} Repeated smoke row {doc_number % 25:02d} keeps "
            "near-duplicate pressure stable for unchanged-skip testing."
        )
    if role == "weak_platform_adjacent":
        return (
            "A platform-adjacent note mentions deploy, alert, incident, service, "
            f"and timeout terms without enough evidence for {pattern['canonical']}."
        )
    return (
        "General business note about planning, calendar updates, team process, "
        f"and documentation hygiene. It includes no reliable {pattern['slot']} evidence."
    )


def _planned_role_counts(document_count: int) -> dict[str, int]:
    counts = Counter(
        ROLE_SEQUENCE[index % len(ROLE_SEQUENCE)] for index in range(document_count)
    )
    return dict(sorted(counts.items()))


def _batch_manifest(
    *, batch_counts: dict[int, Counter[str]], batch_size: int
) -> list[dict[str, Any]]:
    batches: list[dict[str, Any]] = []
    for batch_id in sorted(batch_counts):
        role_counts = batch_counts[batch_id]
        count = sum(role_counts.values())
        start = batch_id * batch_size + 1
        end = start + count - 1
        batches.append(
            {
                "batch_id": batch_id,
                "start_source_id": f"synthetic-5k-{start:05d}",
                "end_source_id": f"synthetic-5k-{end:05d}",
                "documents_total": count,
                "role_counts": dict(sorted(role_counts.items())),
            }
        )
    return batches


def _validate_limits(*, document_count: int, batch_size: int) -> None:
    if document_count <= 0:
        raise SyntheticSmokeError("--documents must be greater than zero")
    if batch_size <= 0:
        raise SyntheticSmokeError("--batch-size must be greater than zero")
    if document_count > 100_000:
        raise SyntheticSmokeError(
            "--documents is capped at 100000 for local smoke runs"
        )


def _ceil_div(value: int, divisor: int) -> int:
    return (value + divisor - 1) // divisor


def _offline_safety() -> dict[str, bool]:
    return {
        "openrouter_calls": False,
        "elasticsearch_calls": False,
        "database_calls": False,
        "runtime_mutation_enabled": False,
        "generated_corpus_committed_by_default": False,
    }


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
