"""Operator-facing retrieval comparison reports.

Patch 50C consumes a ``skeinrank.retrieval_eval_report.v1`` payload and turns it
into a compact comparison/diagnostic report that is suitable for benchmark,
pilot, and company-index evaluation workflows. It remains offline: no database,
Elasticsearch, OpenRouter, proposal, or runtime mutation calls are performed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .retrieval_eval import RETRIEVAL_REPORT_VERSION, default_benchmark_dir

RETRIEVAL_COMPARISON_REPORT_VERSION = "skeinrank.retrieval_comparison_report.v1"


class RetrievalComparisonError(RuntimeError):
    """Raised for user-facing retrieval comparison errors."""


def default_retrieval_report_path() -> Path:
    """Return the default platform_ops_v1 retrieval eval report path."""

    return default_benchmark_dir() / "reports" / "platform_ops_v1-retrieval-report.json"


def default_comparison_report_path() -> Path:
    """Return the default platform_ops_v1 retrieval comparison report path."""

    return (
        default_benchmark_dir()
        / "reports"
        / "platform_ops_v1-retrieval-comparison-report.json"
    )


def build_retrieval_comparison_report(
    eval_report: dict[str, Any], *, source_report: str | None = None, limit: int = 10
) -> dict[str, Any]:
    """Build an operator-facing retrieval comparison report from eval output."""

    _validate_eval_report(eval_report)
    per_query = eval_report.get("per_query") or []
    if not isinstance(per_query, list):
        raise RetrievalComparisonError("retrieval report per_query must be a list")

    diagnostics = [_query_diagnostic(row) for row in per_query]
    sorted_improvements = sorted(
        diagnostics,
        key=lambda item: float(item["delta"].get("ndcg@10", 0.0)),
        reverse=True,
    )
    sorted_regressions = sorted(
        diagnostics, key=lambda item: float(item["delta"].get("ndcg@10", 0.0))
    )
    high_leakage = sorted(
        [
            item
            for item in diagnostics
            if item["risk_flags"]["high_hard_negative_leakage"]
        ],
        key=lambda item: (
            -float(item["skeinrank"].get("hard_negative_leakage@10", 0.0)),
            item["query_id"],
        ),
    )
    high_generic_noise = sorted(
        [
            item
            for item in diagnostics
            if item["risk_flags"]["high_generic_token_noise"]
        ],
        key=lambda item: (
            -float(item["skeinrank"].get("generic_token_noise@10", 0.0)),
            item["query_id"],
        ),
    )
    zero_recall = [
        item
        for item in diagnostics
        if float(item["skeinrank"].get("recall@10", 0.0)) == 0.0
    ]
    no_gain_with_expansion = [
        item
        for item in diagnostics
        if item["added_terms"]
        and abs(float(item["delta"].get("ndcg@10", 0.0))) < 0.0001
    ]
    regressions = [
        item
        for item in diagnostics
        if float(item["delta"].get("ndcg@10", 0.0)) < -0.0001
    ]
    improvements = [
        item
        for item in diagnostics
        if float(item["delta"].get("ndcg@10", 0.0)) > 0.0001
    ]

    counts = {
        "queries_total": len(diagnostics),
        "ndcg_improved": len(improvements),
        "ndcg_regressed": len(regressions),
        "ndcg_unchanged": len(diagnostics) - len(improvements) - len(regressions),
        "recall_improved": sum(
            1
            for item in diagnostics
            if float(item["delta"].get("recall@10", 0.0)) > 0.0001
        ),
        "recall_regressed": sum(
            1
            for item in diagnostics
            if float(item["delta"].get("recall@10", 0.0)) < -0.0001
        ),
        "hard_negative_leakage_improved": sum(
            1
            for item in diagnostics
            if float(item["delta"].get("hard_negative_leakage@10", 0.0)) < -0.0001
        ),
        "hard_negative_leakage_worse": sum(
            1
            for item in diagnostics
            if float(item["delta"].get("hard_negative_leakage@10", 0.0)) > 0.0001
        ),
        "generic_token_noise_worse": sum(
            1
            for item in diagnostics
            if float(item["delta"].get("generic_token_noise@10", 0.0)) > 0.0001
        ),
        "zero_recall_skeinrank": len(zero_recall),
        "high_hard_negative_leakage": len(high_leakage),
        "high_generic_token_noise": len(high_generic_noise),
        "no_gain_with_expansion": len(no_gain_with_expansion),
    }

    report = {
        "schema_version": RETRIEVAL_COMPARISON_REPORT_VERSION,
        "status": "passed"
        if str(eval_report.get("status")) == "passed"
        else "needs_review",
        "benchmark_name": eval_report.get("benchmark_name"),
        "source_report": source_report,
        "source_schema_version": eval_report.get("schema_version"),
        "source_status": eval_report.get("status"),
        "documents_total": eval_report.get("documents_total"),
        "queries_total": len(diagnostics),
        "top_k": eval_report.get("top_k", 10),
        "baseline": eval_report.get("baseline", {}),
        "skeinrank": eval_report.get("skeinrank", {}),
        "delta": eval_report.get("delta", {}),
        "query_counts": counts,
        "query_groups": {
            "largest_ndcg_improvements": _briefs(sorted_improvements[:limit]),
            "largest_ndcg_regressions": _briefs(sorted_regressions[:limit]),
            "high_hard_negative_leakage": _briefs(high_leakage[:limit]),
            "high_generic_token_noise": _briefs(high_generic_noise[:limit]),
            "zero_recall_after_expansion": _briefs(zero_recall[:limit]),
            "no_gain_with_expansion": _briefs(no_gain_with_expansion[:limit]),
        },
        "recommendations": _recommendations(counts=counts, diagnostics=diagnostics),
        "query_diagnostics": diagnostics,
        "quality_gates": _quality_gates(
            eval_report=eval_report, diagnostics=diagnostics
        ),
        "safety": {
            "openrouter_calls": False,
            "elasticsearch_calls": False,
            "database_calls": False,
            "runtime_mutation_enabled": False,
        },
    }
    failed = sum(1 for item in report["quality_gates"] if item["status"] != "passed")
    if failed:
        report["status"] = "needs_review"
    return report


def write_retrieval_comparison_report(
    *, input_report: Path, out: Path, limit: int = 10
) -> dict[str, Any]:
    """Load a retrieval eval report, write its comparison report, and return it."""

    eval_report = _read_json(input_report)
    report = build_retrieval_comparison_report(
        eval_report, source_report=str(input_report), limit=limit
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return report


def print_comparison_report(path: Path) -> dict[str, Any]:
    """Load and print an existing retrieval comparison report."""

    if not path.exists():
        raise RetrievalComparisonError(f"Retrieval comparison report not found: {path}")
    payload = _read_json(path)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return payload


def build_arg_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""

    parser = argparse.ArgumentParser(
        description="Build operator-facing retrieval comparison reports."
    )
    parser.add_argument(
        "command", choices=["compare", "report"], help="Command to run."
    )
    parser.add_argument(
        "--input",
        default=str(default_retrieval_report_path()),
        help="Input skeinrank.retrieval_eval_report.v1 JSON file.",
    )
    parser.add_argument(
        "--out",
        default=str(default_comparison_report_path()),
        help="Output retrieval comparison report JSON file.",
    )
    parser.add_argument(
        "--file",
        default=None,
        help="Existing retrieval comparison report path for report command.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum query diagnostics to include in compact query groups.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "compare":
            input_report = Path(args.input).expanduser().resolve()
            out = Path(args.out).expanduser().resolve()
            report = write_retrieval_comparison_report(
                input_report=input_report, out=out, limit=args.limit
            )
            print(
                json.dumps(
                    {
                        "status": report["status"],
                        "report": str(out),
                        "source_report": str(input_report),
                        "queries_total": report["queries_total"],
                        "query_counts": report["query_counts"],
                        "top_delta": report["delta"],
                        "checks_failed": sum(
                            1
                            for item in report["quality_gates"]
                            if item["status"] != "passed"
                        ),
                    },
                    indent=2,
                    ensure_ascii=False,
                )
            )
            return 0
        report_file = (
            Path(args.file).expanduser().resolve()
            if args.file
            else Path(args.out).expanduser().resolve()
        )
        print_comparison_report(report_file)
        return 0
    except RetrievalComparisonError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


def _validate_eval_report(payload: dict[str, Any]) -> None:
    if not isinstance(payload, dict):
        raise RetrievalComparisonError("retrieval report must be a JSON object")
    if payload.get("schema_version") != RETRIEVAL_REPORT_VERSION:
        raise RetrievalComparisonError(
            "retrieval comparison requires "
            f"{RETRIEVAL_REPORT_VERSION}, got {payload.get('schema_version')!r}"
        )
    for key in ("baseline", "skeinrank", "delta", "per_query"):
        if key not in payload:
            raise RetrievalComparisonError(f"retrieval report is missing {key!r}")


def _query_diagnostic(row: dict[str, Any]) -> dict[str, Any]:
    query_id = str(row.get("query_id") or "")
    baseline = dict((row.get("baseline") or {}).get("metrics") or {})
    skeinrank = dict((row.get("skeinrank") or {}).get("metrics") or {})
    delta = dict(row.get("delta") or {})
    baseline_top = list((row.get("baseline") or {}).get("top_documents") or [])
    skeinrank_top = list((row.get("skeinrank") or {}).get("top_documents") or [])
    added_terms = list((row.get("skeinrank") or {}).get("added_terms") or [])
    outcome = _outcome(delta)
    diagnostic = {
        "query_id": query_id,
        "query": row.get("query"),
        "description": row.get("description"),
        "outcome": outcome,
        "expected_expansions": row.get("expected_expansions", []),
        "added_terms": added_terms,
        "baseline": baseline,
        "skeinrank": skeinrank,
        "delta": delta,
        "first_relevant_rank": {
            "baseline": _first_relevant_rank(baseline_top),
            "skeinrank": _first_relevant_rank(skeinrank_top),
        },
        "top10": {
            "baseline_relevant": _relevant_count(baseline_top),
            "skeinrank_relevant": _relevant_count(skeinrank_top),
            "baseline_hard_negatives": _hard_negative_count(baseline_top),
            "skeinrank_hard_negatives": _hard_negative_count(skeinrank_top),
            "baseline_generic_noise": _generic_noise_count(baseline_top),
            "skeinrank_generic_noise": _generic_noise_count(skeinrank_top),
        },
        "risk_flags": {
            "ndcg_regressed": float(delta.get("ndcg@10", 0.0)) < -0.0001,
            "recall_regressed": float(delta.get("recall@10", 0.0)) < -0.0001,
            "hard_negative_leakage_worse": float(
                delta.get("hard_negative_leakage@10", 0.0)
            )
            > 0.0001,
            "high_hard_negative_leakage": float(
                skeinrank.get("hard_negative_leakage@10", 0.0)
            )
            >= 0.5,
            "generic_token_noise_worse": float(delta.get("generic_token_noise@10", 0.0))
            > 0.0001,
            "high_generic_token_noise": float(
                skeinrank.get("generic_token_noise@10", 0.0)
            )
            >= 0.3,
            "zero_recall_after_expansion": float(skeinrank.get("recall@10", 0.0))
            == 0.0,
        },
        "recommended_actions": [],
    }
    diagnostic["recommended_actions"] = _query_recommendations(diagnostic)
    return diagnostic


def _outcome(delta: dict[str, Any]) -> str:
    ndcg = float(delta.get("ndcg@10", 0.0))
    recall = float(delta.get("recall@10", 0.0))
    leakage = float(delta.get("hard_negative_leakage@10", 0.0))
    if ndcg > 0.0001 or recall > 0.0001 or leakage < -0.0001:
        return "improved"
    if ndcg < -0.0001 or recall < -0.0001 or leakage > 0.0001:
        return "regressed"
    return "unchanged"


def _first_relevant_rank(top_documents: list[dict[str, Any]]) -> int | None:
    for item in top_documents:
        if int(item.get("relevance") or 0) > 0:
            return int(item.get("rank") or 0)
    return None


def _relevant_count(top_documents: list[dict[str, Any]]) -> int:
    return sum(1 for item in top_documents if int(item.get("relevance") or 0) > 0)


def _hard_negative_count(top_documents: list[dict[str, Any]]) -> int:
    return sum(1 for item in top_documents if bool(item.get("hard_negative")))


def _generic_noise_count(top_documents: list[dict[str, Any]]) -> int:
    return sum(int(item.get("generic_token_noise") or 0) for item in top_documents)


def _briefs(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "query_id": item["query_id"],
            "query": item.get("query"),
            "outcome": item["outcome"],
            "delta": item["delta"],
            "skeinrank": item["skeinrank"],
            "added_terms": item["added_terms"],
            "recommended_actions": item["recommended_actions"],
        }
        for item in items
    ]


def _query_recommendations(item: dict[str, Any]) -> list[str]:
    flags = item["risk_flags"]
    recommendations: list[str] = []
    if flags["zero_recall_after_expansion"]:
        recommendations.append(
            "review qrels, source text, and alias coverage for this query"
        )
    if flags["ndcg_regressed"]:
        recommendations.append("inspect top documents where expansion lowered NDCG")
    if flags["hard_negative_leakage_worse"] or flags["high_hard_negative_leakage"]:
        recommendations.append(
            "add or tune hard-negative rules for ambiguous matched terms"
        )
    if flags["generic_token_noise_worse"] or flags["high_generic_token_noise"]:
        recommendations.append(
            "downweight generic query terms or require domain-term co-occurrence"
        )
    if item["added_terms"] and item["outcome"] == "unchanged":
        recommendations.append(
            "check whether expansions exist in relevant documents or need synonyms"
        )
    if not recommendations:
        recommendations.append("no immediate action")
    return recommendations


def _recommendations(
    *, counts: dict[str, int], diagnostics: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    recommendations = []
    if counts["zero_recall_skeinrank"]:
        recommendations.append(
            {
                "priority": "high",
                "code": "zero_recall_queries",
                "message": "Some queries still have zero recall after expansion; inspect qrels, source text, and alias coverage.",
            }
        )
    if counts["high_hard_negative_leakage"]:
        recommendations.append(
            {
                "priority": "high",
                "code": "hard_negative_leakage",
                "message": "Some queries have high hard-negative leakage; tune ambiguous term weights and hard-negative rules before scaling to larger corpora.",
            }
        )
    if counts["generic_token_noise_worse"]:
        recommendations.append(
            {
                "priority": "medium",
                "code": "generic_token_noise",
                "message": "Generic-token noise increased for some queries; review service/api/error/job/page style terms.",
            }
        )
    if counts["ndcg_regressed"]:
        recommendations.append(
            {
                "priority": "medium",
                "code": "ndcg_regressions",
                "message": "Some queries regress on NDCG@10; inspect largest_ndcg_regressions before changing gates.",
            }
        )
    if counts["ndcg_improved"] and counts["hard_negative_leakage_improved"]:
        recommendations.append(
            {
                "priority": "info",
                "code": "positive_quality_signal",
                "message": "SkeinRank improves ranking quality while reducing hard-negative leakage for part of the query set.",
            }
        )
    if not recommendations and diagnostics:
        recommendations.append(
            {
                "priority": "info",
                "code": "stable",
                "message": "No major retrieval quality risks were detected in the comparison report.",
            }
        )
    return recommendations


def _quality_gates(
    *, eval_report: dict[str, Any], diagnostics: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    return [
        {
            "name": "retrieval_comparison_source_report_valid",
            "status": "passed"
            if eval_report.get("schema_version") == RETRIEVAL_REPORT_VERSION
            else "failed",
            "message": "Comparison input uses the expected retrieval eval report schema.",
            "details": {"schema_version": eval_report.get("schema_version")},
        },
        {
            "name": "retrieval_comparison_queries_diagnosed",
            "status": "passed" if diagnostics else "failed",
            "message": "Every query from the retrieval report is available for diagnostics.",
            "details": {"queries_total": len(diagnostics)},
        },
        {
            "name": "retrieval_comparison_recommendations_present",
            "status": "passed" if diagnostics else "failed",
            "message": "Operator recommendations can be generated from query-level diagnostics.",
            "details": {"diagnostics_total": len(diagnostics)},
        },
    ]


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise RetrievalComparisonError(f"Retrieval report not found: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RetrievalComparisonError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise RetrievalComparisonError(f"{path} must contain a JSON object")
    return payload


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
