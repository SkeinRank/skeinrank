"""Offline cost, latency, and throughput report for benchmark smoke runs.

The performance reporter stays provider-independent. It combines generated
synthetic-smoke manifests with optional live-pilot usage reports and explicit
elapsed-time inputs. It does not call OpenRouter, Elasticsearch, the database,
or runtime mutation APIs.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

BENCHMARK_PERFORMANCE_PLAN_VERSION = "skeinrank.benchmark_performance_plan.v1"
BENCHMARK_PERFORMANCE_REPORT_VERSION = "skeinrank.benchmark_performance_report.v1"
DEFAULT_BENCHMARK_NAME = "platform_ops_v1"
DEFAULT_ELAPSED_SECONDS = 300.0
DEFAULT_DOCUMENT_PROJECTION = 100_000


class BenchmarkPerformanceError(RuntimeError):
    """Raised for user-facing benchmark performance report errors."""


@dataclass(frozen=True)
class BenchmarkPerformancePaths:
    """Resolved benchmark performance fixture/report paths."""

    root: Path
    synthetic_manifest: Path
    default_report: Path


def default_benchmark_dir() -> Path:
    """Return the default repository benchmark fixture directory."""

    return (
        Path(__file__).resolve().parents[3]
        / "examples"
        / "benchmarks"
        / "platform_ops_v1"
    )


def resolve_benchmark_performance_paths(
    path: str | Path | None = None,
) -> BenchmarkPerformancePaths:
    """Resolve default benchmark performance input/output paths."""

    root = Path(path or default_benchmark_dir()).expanduser().resolve()
    return BenchmarkPerformancePaths(
        root=root,
        synthetic_manifest=root
        / "reports"
        / "synthetic"
        / "platform_ops_v1-5k-manifest.json",
        default_report=root
        / "reports"
        / "platform_ops_v1-cost-latency-throughput-report.json",
    )


def build_benchmark_performance_plan(
    *,
    synthetic_manifest_path: str | Path,
    elapsed_seconds: float = DEFAULT_ELAPSED_SECONDS,
    live_report_path: str | Path | None = None,
    projection_documents: int = DEFAULT_DOCUMENT_PROJECTION,
) -> dict[str, Any]:
    """Return a dry plan for a cost/latency/throughput report."""

    manifest = _load_json(synthetic_manifest_path, label="synthetic smoke manifest")
    _validate_elapsed_seconds(elapsed_seconds)
    _validate_projection_documents(projection_documents)
    live_report_exists = bool(live_report_path and Path(live_report_path).exists())
    return {
        "schema_version": BENCHMARK_PERFORMANCE_PLAN_VERSION,
        "benchmark_name": str(manifest.get("benchmark_name") or DEFAULT_BENCHMARK_NAME),
        "status": "planned",
        "inputs": {
            "synthetic_manifest": str(
                Path(synthetic_manifest_path).expanduser().resolve()
            ),
            "live_report": str(Path(live_report_path).expanduser().resolve())
            if live_report_path
            else None,
            "live_report_exists": live_report_exists,
            "elapsed_seconds": float(elapsed_seconds),
            "projection_documents": int(projection_documents),
        },
        "workload": _workload_from_manifest(manifest),
        "reports": ["cost", "latency", "throughput", "savings", "projection"],
        "safety": _offline_safety(),
    }


def build_benchmark_performance_report(
    *,
    synthetic_manifest_path: str | Path,
    elapsed_seconds: float,
    out: str | Path | None = None,
    live_report_path: str | Path | None = None,
    projection_documents: int = DEFAULT_DOCUMENT_PROJECTION,
    llm_calls: int | None = None,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    total_tokens: int | None = None,
    estimated_cost_usd: float | None = None,
    skipped_unchanged: int | None = None,
    failed_documents: int = 0,
    retried_documents: int = 0,
    cache_hits: int | None = None,
    idempotent_existing_aliases: int | None = None,
) -> dict[str, Any]:
    """Build and optionally persist a benchmark performance report."""

    _validate_elapsed_seconds(elapsed_seconds)
    _validate_projection_documents(projection_documents)
    _validate_non_negative_int(failed_documents, "failed_documents")
    _validate_non_negative_int(retried_documents, "retried_documents")

    manifest = _load_json(synthetic_manifest_path, label="synthetic smoke manifest")
    live_report = (
        _load_json(live_report_path, label="OpenRouter live pilot report")
        if live_report_path
        else None
    )
    workload = _workload_from_manifest(manifest)
    live_usage = _usage_from_live_report(live_report) if live_report else {}
    usage = _merge_usage(
        live_usage=live_usage,
        llm_calls=llm_calls,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        estimated_cost_usd=estimated_cost_usd,
        cache_hits=cache_hits,
        idempotent_existing_aliases=idempotent_existing_aliases,
    )
    documents_total = int(workload["documents_total"])
    batches_total = int(workload["batches_total"])
    unchanged_skip_candidates = int(workload["unchanged_skip_candidates"])
    if skipped_unchanged is not None:
        _validate_non_negative_int(skipped_unchanged, "skipped_unchanged")
        unchanged_skip_candidates = int(skipped_unchanged)

    processed_documents = max(documents_total - unchanged_skip_candidates, 0)
    latency = _latency_report(
        elapsed_seconds=elapsed_seconds,
        documents_total=documents_total,
        processed_documents=processed_documents,
        batches_total=batches_total,
    )
    unit_costs = _unit_costs(
        documents_total=documents_total,
        processed_documents=processed_documents,
        usage=usage,
    )
    savings = _savings_report(
        documents_total=documents_total,
        skipped_unchanged=unchanged_skip_candidates,
        cache_hits=int(usage["cache_hits"]),
        idempotent_existing_aliases=int(usage["idempotent_existing_aliases"]),
        llm_calls=int(usage["llm_calls"]),
        unit_costs=unit_costs,
    )
    projection = _projection_report(
        projection_documents=projection_documents,
        documents_total=documents_total,
        elapsed_seconds=elapsed_seconds,
        estimated_cost_usd=float(usage["estimated_cost_usd"] or 0.0),
        total_tokens=int(usage["total_tokens"]),
        llm_calls=int(usage["llm_calls"]),
        skip_rate=float(savings["skip_rate"]),
    )
    report = {
        "schema_version": BENCHMARK_PERFORMANCE_REPORT_VERSION,
        "benchmark_name": str(manifest.get("benchmark_name") or DEFAULT_BENCHMARK_NAME),
        "status": "reported",
        "measurement_mode": "offline_estimate",
        "inputs": {
            "synthetic_manifest": str(
                Path(synthetic_manifest_path).expanduser().resolve()
            ),
            "live_report": str(Path(live_report_path).expanduser().resolve())
            if live_report_path
            else None,
            "elapsed_seconds": round(float(elapsed_seconds), 6),
            "projection_documents": int(projection_documents),
        },
        "workload": {
            **workload,
            "processed_documents": processed_documents,
            "failed_documents": int(failed_documents),
            "retried_documents": int(retried_documents),
        },
        "latency": latency,
        "usage": usage,
        "unit_costs": unit_costs,
        "savings": savings,
        "projection": projection,
        "recommendations": _recommendations(
            workload={**workload, "processed_documents": processed_documents},
            latency=latency,
            usage=usage,
            savings=savings,
            failed_documents=failed_documents,
            retried_documents=retried_documents,
        ),
        "safety": _offline_safety(),
    }
    if out:
        output_path = Path(out).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    return report


def load_benchmark_performance_report(path: str | Path) -> dict[str, Any]:
    """Load an existing benchmark performance report."""

    payload = _load_json(path, label="benchmark performance report")
    if payload.get("schema_version") != BENCHMARK_PERFORMANCE_REPORT_VERSION:
        raise BenchmarkPerformanceError(
            "Unexpected benchmark performance report schema: "
            f"{payload.get('schema_version')}"
        )
    return payload


def build_arg_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""

    parser = argparse.ArgumentParser(
        description="Build an offline benchmark cost/latency/throughput report."
    )
    parser.add_argument(
        "command", choices=["plan", "report", "show"], help="Command to run."
    )
    parser.add_argument(
        "--benchmark-dir",
        default=None,
        help="Benchmark fixture directory. Defaults to platform_ops_v1.",
    )
    parser.add_argument(
        "--synthetic-manifest",
        default=None,
        help="Synthetic smoke manifest path. Defaults to reports/synthetic manifest.",
    )
    parser.add_argument(
        "--live-report",
        default=None,
        help="Optional OpenRouter live/validated pilot report used for token/cost hints.",
    )
    parser.add_argument(
        "--elapsed-seconds",
        type=float,
        default=DEFAULT_ELAPSED_SECONDS,
        help="Observed or assumed elapsed seconds for the run window.",
    )
    parser.add_argument(
        "--projection-documents",
        type=int,
        default=DEFAULT_DOCUMENT_PROJECTION,
        help="Document count for simple scale projection.",
    )
    parser.add_argument(
        "--out", default=None, help="Output report path for report command."
    )
    parser.add_argument("--file", default=None, help="Report path for show command.")
    parser.add_argument("--llm-calls", type=int, default=None)
    parser.add_argument("--prompt-tokens", type=int, default=None)
    parser.add_argument("--completion-tokens", type=int, default=None)
    parser.add_argument("--total-tokens", type=int, default=None)
    parser.add_argument("--estimated-cost-usd", type=float, default=None)
    parser.add_argument("--skipped-unchanged", type=int, default=None)
    parser.add_argument("--failed-documents", type=int, default=0)
    parser.add_argument("--retried-documents", type=int, default=0)
    parser.add_argument("--cache-hits", type=int, default=None)
    parser.add_argument("--idempotent-existing-aliases", type=int, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the benchmark performance CLI."""

    parser = build_arg_parser()
    args = parser.parse_args(argv)
    try:
        paths = resolve_benchmark_performance_paths(args.benchmark_dir)
        manifest_path = (
            Path(args.synthetic_manifest).expanduser().resolve()
            if args.synthetic_manifest
            else paths.synthetic_manifest
        )
        if args.command == "plan":
            payload = build_benchmark_performance_plan(
                synthetic_manifest_path=manifest_path,
                live_report_path=args.live_report,
                elapsed_seconds=args.elapsed_seconds,
                projection_documents=args.projection_documents,
            )
        elif args.command == "report":
            payload = build_benchmark_performance_report(
                synthetic_manifest_path=manifest_path,
                live_report_path=args.live_report,
                elapsed_seconds=args.elapsed_seconds,
                projection_documents=args.projection_documents,
                out=args.out or paths.default_report,
                llm_calls=args.llm_calls,
                prompt_tokens=args.prompt_tokens,
                completion_tokens=args.completion_tokens,
                total_tokens=args.total_tokens,
                estimated_cost_usd=args.estimated_cost_usd,
                skipped_unchanged=args.skipped_unchanged,
                failed_documents=args.failed_documents,
                retried_documents=args.retried_documents,
                cache_hits=args.cache_hits,
                idempotent_existing_aliases=args.idempotent_existing_aliases,
            )
        else:
            report_path = Path(args.file or paths.default_report).expanduser().resolve()
            payload = load_benchmark_performance_report(report_path)
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0
    except BenchmarkPerformanceError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


def _workload_from_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    _validate_manifest(manifest)
    document_count = int(
        manifest.get("document_count") or manifest.get("documents_total") or 0
    )
    batch_size = int(manifest.get("batch_size") or 0)
    batches_total = int(manifest.get("batches_total") or 0)
    unchanged_skip_candidates = int(manifest.get("unchanged_skip_candidates") or 0)
    return {
        "documents_total": document_count,
        "batch_size": batch_size,
        "batches_total": batches_total,
        "role_counts": dict(manifest.get("role_counts") or {}),
        "source_type_counts": dict(manifest.get("source_type_counts") or {}),
        "unchanged_skip_candidates": unchanged_skip_candidates,
        "first_source_id": manifest.get("first_source_id"),
        "last_source_id": manifest.get("last_source_id"),
        "corpus_sha256": manifest.get("corpus_sha256"),
    }


def _validate_manifest(manifest: dict[str, Any]) -> None:
    schema_version = manifest.get("schema_version")
    if schema_version != "skeinrank.synthetic_smoke_manifest.v1":
        raise BenchmarkPerformanceError(
            "Expected synthetic smoke manifest schema "
            f"skeinrank.synthetic_smoke_manifest.v1, got {schema_version!r}"
        )
    documents = int(manifest.get("document_count") or 0)
    batches = int(manifest.get("batches_total") or 0)
    if documents <= 0:
        raise BenchmarkPerformanceError(
            "Synthetic manifest document_count must be positive"
        )
    if batches <= 0:
        raise BenchmarkPerformanceError(
            "Synthetic manifest batches_total must be positive"
        )


def _usage_from_live_report(report: dict[str, Any]) -> dict[str, Any]:
    summary = dict(report.get("summary") or {})
    llm_report = dict(report.get("llm_review_report") or {})
    budget_summary = dict(llm_report.get("budget_cache_summary") or {})
    budget_usage = dict(budget_summary.get("usage") or {})
    llm_summary = dict(llm_report.get("llm_review_summary") or {})
    prompt_tokens = _first_int(summary, budget_usage, keys=("prompt_tokens",))
    completion_tokens = _first_int(summary, budget_usage, keys=("completion_tokens",))
    total_tokens = _first_int(summary, budget_usage, keys=("total_tokens", "tokens"))
    if total_tokens == 0:
        total_tokens = prompt_tokens + completion_tokens
    return {
        "llm_calls": _first_int(
            summary,
            llm_summary,
            keys=("live_openrouter_calls", "openrouter_calls", "llm_calls"),
        ),
        "candidates_sent_to_model": _first_int(
            summary, llm_summary, keys=("candidates_sent_to_model",)
        ),
        "proposals_prepared": _first_int(
            summary, llm_summary, keys=("proposals_prepared",)
        ),
        "eligible_proposals": int(summary.get("eligible_proposals") or 0),
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "estimated_cost_usd": _first_float(
            summary, budget_usage, keys=("estimated_cost_usd", "cost")
        ),
        "cache_hits": _first_int(
            summary, llm_summary, budget_summary, keys=("cache_hits",)
        ),
        "skipped_due_to_budget": _first_int(
            summary, budget_summary, keys=("skipped_due_to_budget",)
        ),
        "idempotent_existing_aliases": int(
            summary.get("idempotent_existing_aliases") or 0
        ),
        "errors": int(summary.get("errors") or 0),
    }


def _merge_usage(
    *,
    live_usage: dict[str, Any],
    llm_calls: int | None,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    total_tokens: int | None,
    estimated_cost_usd: float | None,
    cache_hits: int | None,
    idempotent_existing_aliases: int | None,
) -> dict[str, Any]:
    usage = {
        "llm_calls": int(live_usage.get("llm_calls") or 0),
        "candidates_sent_to_model": int(
            live_usage.get("candidates_sent_to_model") or 0
        ),
        "proposals_prepared": int(live_usage.get("proposals_prepared") or 0),
        "eligible_proposals": int(live_usage.get("eligible_proposals") or 0),
        "prompt_tokens": int(live_usage.get("prompt_tokens") or 0),
        "completion_tokens": int(live_usage.get("completion_tokens") or 0),
        "total_tokens": int(live_usage.get("total_tokens") or 0),
        "estimated_cost_usd": round(
            float(live_usage.get("estimated_cost_usd") or 0.0), 10
        ),
        "cache_hits": int(live_usage.get("cache_hits") or 0),
        "skipped_due_to_budget": int(live_usage.get("skipped_due_to_budget") or 0),
        "idempotent_existing_aliases": int(
            live_usage.get("idempotent_existing_aliases") or 0
        ),
        "errors": int(live_usage.get("errors") or 0),
    }
    overrides = {
        "llm_calls": llm_calls,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "cache_hits": cache_hits,
        "idempotent_existing_aliases": idempotent_existing_aliases,
    }
    for key, value in overrides.items():
        if value is not None:
            _validate_non_negative_int(value, key)
            usage[key] = int(value)
    if estimated_cost_usd is not None:
        if estimated_cost_usd < 0:
            raise BenchmarkPerformanceError("estimated_cost_usd must be non-negative")
        usage["estimated_cost_usd"] = round(float(estimated_cost_usd), 10)
    if usage["total_tokens"] == 0:
        usage["total_tokens"] = usage["prompt_tokens"] + usage["completion_tokens"]
    return usage


def _latency_report(
    *,
    elapsed_seconds: float,
    documents_total: int,
    processed_documents: int,
    batches_total: int,
) -> dict[str, Any]:
    return {
        "elapsed_seconds": round(float(elapsed_seconds), 6),
        "documents_per_second": _round(documents_total / elapsed_seconds),
        "documents_per_minute": _round(documents_total * 60.0 / elapsed_seconds),
        "processed_documents_per_minute": _round(
            processed_documents * 60.0 / elapsed_seconds
        ),
        "seconds_per_document": _round(elapsed_seconds / documents_total),
        "seconds_per_processed_document": _round(
            elapsed_seconds / processed_documents if processed_documents else 0.0
        ),
        "batches_per_minute": _round(batches_total * 60.0 / elapsed_seconds),
        "average_batch_latency_seconds": _round(elapsed_seconds / batches_total),
    }


def _unit_costs(
    *, documents_total: int, processed_documents: int, usage: dict[str, Any]
) -> dict[str, Any]:
    total_tokens = int(usage["total_tokens"])
    llm_calls = int(usage["llm_calls"])
    cost = float(usage["estimated_cost_usd"] or 0.0)
    return {
        "tokens_per_document": _round(total_tokens / documents_total),
        "tokens_per_processed_document": _round(
            total_tokens / processed_documents if processed_documents else 0.0
        ),
        "tokens_per_llm_call": _round(total_tokens / llm_calls if llm_calls else 0.0),
        "cost_per_document_usd": _round(cost / documents_total),
        "cost_per_processed_document_usd": _round(
            cost / processed_documents if processed_documents else 0.0
        ),
        "cost_per_1k_documents_usd": _round(cost * 1000.0 / documents_total),
        "cost_per_llm_call_usd": _round(cost / llm_calls if llm_calls else 0.0),
    }


def _savings_report(
    *,
    documents_total: int,
    skipped_unchanged: int,
    cache_hits: int,
    idempotent_existing_aliases: int,
    llm_calls: int,
    unit_costs: dict[str, Any],
) -> dict[str, Any]:
    skip_rate = skipped_unchanged / documents_total if documents_total else 0.0
    saved_items = skipped_unchanged + cache_hits + idempotent_existing_aliases
    estimated_saved_cost = skipped_unchanged * float(
        unit_costs["cost_per_document_usd"]
    ) + cache_hits * float(unit_costs["cost_per_llm_call_usd"])
    return {
        "skipped_unchanged_documents": skipped_unchanged,
        "cache_hits": cache_hits,
        "idempotent_existing_aliases": idempotent_existing_aliases,
        "saved_work_items_estimate": saved_items,
        "skip_rate": _round(skip_rate),
        "llm_cache_hit_rate": _round(
            cache_hits / (cache_hits + llm_calls) if cache_hits + llm_calls else 0.0
        ),
        "estimated_saved_cost_usd": _round(estimated_saved_cost),
    }


def _projection_report(
    *,
    projection_documents: int,
    documents_total: int,
    elapsed_seconds: float,
    estimated_cost_usd: float,
    total_tokens: int,
    llm_calls: int,
    skip_rate: float,
) -> dict[str, Any]:
    scale = projection_documents / documents_total
    return {
        "projection_documents": int(projection_documents),
        "estimated_elapsed_seconds": _round(elapsed_seconds * scale),
        "estimated_elapsed_minutes": _round(elapsed_seconds * scale / 60.0),
        "estimated_total_tokens": int(round(total_tokens * scale)),
        "estimated_llm_calls": int(round(llm_calls * scale)),
        "estimated_cost_usd": _round(estimated_cost_usd * scale),
        "estimated_skipped_unchanged_documents": int(
            round(projection_documents * skip_rate)
        ),
        "projection_basis": "linear_scale_from_current_report",
    }


def _recommendations(
    *,
    workload: dict[str, Any],
    latency: dict[str, Any],
    usage: dict[str, Any],
    savings: dict[str, Any],
    failed_documents: int,
    retried_documents: int,
) -> list[str]:
    recommendations: list[str] = []
    if int(usage["llm_calls"]) == 0:
        recommendations.append(
            "No LLM usage was provided; pass --live-report or explicit token/cost flags for cost estimates."
        )
    if float(savings["skip_rate"]) >= 0.05:
        recommendations.append(
            "Skip/unchanged accounting is visible; preserve source_id/content-hash stability before larger smoke runs."
        )
    if float(latency["documents_per_minute"]) < 500:
        recommendations.append(
            "Throughput is below 500 docs/min in this estimate; use smaller batches or profile worker/provider latency before 100k-doc runs."
        )
    else:
        recommendations.append(
            "Throughput is acceptable for 5k smoke planning; next validate with real worker timings."
        )
    if failed_documents or retried_documents:
        recommendations.append(
            "Failures/retries are present; inspect resume-plan/report diagnostics before scaling the run."
        )
    if int(workload.get("processed_documents") or 0) == 0:
        recommendations.append(
            "All documents were skipped; verify the corpus hash/source tracking inputs."
        )
    return recommendations


def _load_json(path: str | Path, *, label: str) -> dict[str, Any]:
    candidate = Path(path).expanduser().resolve()
    if not candidate.exists():
        raise BenchmarkPerformanceError(f"{label} not found: {candidate}")
    try:
        payload = json.loads(candidate.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise BenchmarkPerformanceError(
            f"Invalid JSON in {label}: {candidate}"
        ) from exc
    if not isinstance(payload, dict):
        raise BenchmarkPerformanceError(
            f"{label} must contain a JSON object: {candidate}"
        )
    return payload


def _first_int(*payloads: dict[str, Any], keys: tuple[str, ...]) -> int:
    for payload in payloads:
        for key in keys:
            value = payload.get(key)
            if value is not None:
                try:
                    return int(value)
                except (TypeError, ValueError):
                    return 0
    return 0


def _first_float(*payloads: dict[str, Any], keys: tuple[str, ...]) -> float:
    for payload in payloads:
        for key in keys:
            value = payload.get(key)
            if value is not None:
                try:
                    return float(value)
                except (TypeError, ValueError):
                    return 0.0
    return 0.0


def _validate_elapsed_seconds(value: float) -> None:
    if value <= 0:
        raise BenchmarkPerformanceError("elapsed_seconds must be greater than zero")


def _validate_projection_documents(value: int) -> None:
    if value <= 0:
        raise BenchmarkPerformanceError(
            "projection_documents must be greater than zero"
        )


def _validate_non_negative_int(value: int, label: str) -> None:
    if int(value) < 0:
        raise BenchmarkPerformanceError(f"{label} must be non-negative")


def _round(value: float) -> float:
    return round(float(value), 6)


def _offline_safety() -> dict[str, bool]:
    return {
        "openrouter_calls": False,
        "elasticsearch_calls": False,
        "database_calls": False,
        "runtime_mutation_enabled": False,
        "generated_report_committed_by_default": False,
    }


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
