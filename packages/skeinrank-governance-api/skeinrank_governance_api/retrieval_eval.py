"""Deterministic retrieval evaluation baseline for benchmark corpora.

The 50A evaluator is intentionally offline. It does not call Elasticsearch or
OpenRouter; it uses the synthetic benchmark corpus, qrels, and SkeinRank alias
maps to compare a literal lexical baseline against a SkeinRank-expanded lexical
run. The goal is to prove the evaluation harness and metric reporting before
scaling the corpus or wiring company-specific search providers.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

RETRIEVAL_REPORT_VERSION = "skeinrank.retrieval_eval_report.v1"
DEFAULT_BENCHMARK_NAME = "platform_ops_v1"


class RetrievalEvalError(RuntimeError):
    """Raised for user-facing retrieval evaluator errors."""


@dataclass(frozen=True)
class RetrievalPaths:
    """Resolved retrieval evaluation fixture paths."""

    root: Path
    corpus: Path
    seed_dictionary: Path
    expected_aliases: Path
    retrieval_queries: Path
    qrels: Path
    default_report: Path


def default_benchmark_dir() -> Path:
    """Return the default repository benchmark fixture directory."""

    return (
        Path(__file__).resolve().parents[3]
        / "examples"
        / "benchmarks"
        / "platform_ops_v1"
    )


def resolve_retrieval_paths(path: str | Path | None = None) -> RetrievalPaths:
    """Resolve and validate retrieval evaluation fixture paths."""

    root = Path(path or default_benchmark_dir()).expanduser().resolve()
    paths = RetrievalPaths(
        root=root,
        corpus=root / "corpus.jsonl",
        seed_dictionary=root / "seed_dictionary.json",
        expected_aliases=root / "expected_aliases.json",
        retrieval_queries=root / "retrieval_queries.jsonl",
        qrels=root / "qrels.jsonl",
        default_report=root / "reports" / "platform_ops_v1-retrieval-report.json",
    )
    missing = [
        str(candidate)
        for candidate in (
            paths.corpus,
            paths.seed_dictionary,
            paths.expected_aliases,
            paths.retrieval_queries,
            paths.qrels,
        )
        if not candidate.exists()
    ]
    if missing:
        raise RetrievalEvalError(
            "Missing retrieval evaluation fixture files: " + ", ".join(missing)
        )
    return paths


def build_retrieval_plan(*, paths: RetrievalPaths | None = None) -> dict[str, Any]:
    """Return a dry plan for the retrieval evaluation run."""

    paths = paths or resolve_retrieval_paths()
    corpus = _read_jsonl(paths.corpus)
    queries = _read_jsonl(paths.retrieval_queries)
    qrels = _load_qrels(paths.qrels)
    alias_map = _build_alias_map(
        seed_dictionary=_read_json(paths.seed_dictionary),
        expected_aliases=_read_json(paths.expected_aliases),
    )
    return {
        "schema_version": "skeinrank.retrieval_eval_plan.v1",
        "benchmark_name": DEFAULT_BENCHMARK_NAME,
        "status": "planned",
        "documents_total": len(corpus),
        "queries_total": len(queries),
        "qrels_total": sum(len(values) for values in qrels.values()),
        "alias_terms_total": len(alias_map),
        "runs": ["baseline", "skeinrank"],
        "metrics": ["ndcg@10", "mrr@10", "recall@10", "precision@10"],
        "safety": {
            "openrouter_calls": False,
            "elasticsearch_calls": False,
            "database_calls": False,
            "runtime_mutation_enabled": False,
        },
        "fixtures": {
            "corpus": str(paths.corpus),
            "retrieval_queries": str(paths.retrieval_queries),
            "qrels": str(paths.qrels),
        },
    }


def run_retrieval_evaluation(
    *,
    paths: RetrievalPaths | None = None,
    top_k: int = 10,
    out: Path | None = None,
) -> dict[str, Any]:
    """Run baseline vs SkeinRank retrieval evaluation and optionally persist it."""

    paths = paths or resolve_retrieval_paths()
    corpus = _read_jsonl(paths.corpus)
    queries = _read_jsonl(paths.retrieval_queries)
    qrels = _load_qrels(paths.qrels)
    expected_aliases = _read_json(paths.expected_aliases)
    alias_map = _build_alias_map(
        seed_dictionary=_read_json(paths.seed_dictionary),
        expected_aliases=expected_aliases,
    )
    documents = [_document_from_payload(payload) for payload in corpus]

    baseline_results = []
    skeinrank_results = []
    per_query = []
    for query in queries:
        query_id = str(query["query_id"])
        text = str(query["query"])
        relevant = qrels.get(query_id, {})
        baseline_terms = _baseline_terms(text)
        expanded = _skeinrank_terms(text, alias_map=alias_map)
        baseline_ranking = _rank_documents(documents, baseline_terms)
        skeinrank_ranking = _rank_documents(documents, expanded)
        baseline_metrics = _metrics_for_query(
            ranking=baseline_ranking, qrels=relevant, top_k=top_k
        )
        skeinrank_metrics = _metrics_for_query(
            ranking=skeinrank_ranking, qrels=relevant, top_k=top_k
        )
        baseline_results.append(baseline_metrics)
        skeinrank_results.append(skeinrank_metrics)
        per_query.append(
            {
                "query_id": query_id,
                "query": text,
                "description": query.get("description"),
                "expected_expansions": query.get("expected_expansions", []),
                "relevant_documents": [
                    {"source_id": doc_id, "relevance": relevance}
                    for doc_id, relevance in sorted(
                        relevant.items(), key=lambda item: (-item[1], item[0])
                    )
                ],
                "baseline": {
                    "terms": baseline_terms,
                    "metrics": baseline_metrics,
                    "top_documents": _compact_ranking(
                        baseline_ranking, relevant, top_k
                    ),
                },
                "skeinrank": {
                    "terms": expanded,
                    "added_terms": [
                        term for term in expanded if term not in baseline_terms
                    ],
                    "metrics": skeinrank_metrics,
                    "top_documents": _compact_ranking(
                        skeinrank_ranking, relevant, top_k
                    ),
                },
                "delta": _metric_delta(skeinrank_metrics, baseline_metrics),
            }
        )

    baseline_summary = _aggregate_metrics(baseline_results)
    skeinrank_summary = _aggregate_metrics(skeinrank_results)
    delta = _metric_delta(skeinrank_summary, baseline_summary)
    thresholds = _retrieval_thresholds(expected_aliases)
    quality_gates = _quality_gates(
        delta=delta, skeinrank=skeinrank_summary, thresholds=thresholds
    )
    checks_failed = sum(1 for item in quality_gates if item["status"] != "passed")
    report = {
        "schema_version": RETRIEVAL_REPORT_VERSION,
        "benchmark_name": DEFAULT_BENCHMARK_NAME,
        "status": "passed" if checks_failed == 0 else "failed",
        "documents_total": len(documents),
        "queries_total": len(queries),
        "qrels_total": sum(len(values) for values in qrels.values()),
        "top_k": top_k,
        "baseline": baseline_summary,
        "skeinrank": skeinrank_summary,
        "delta": delta,
        "quality_thresholds": thresholds,
        "quality_gates": quality_gates,
        "per_query": per_query,
        "safety": {
            "openrouter_calls": False,
            "elasticsearch_calls": False,
            "database_calls": False,
            "runtime_mutation_enabled": False,
        },
    }
    output_path = out or paths.default_report
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return report


def print_retrieval_report(path: Path) -> dict[str, Any]:
    """Load and print an existing retrieval report."""

    if not path.exists():
        raise RetrievalEvalError(f"Retrieval report not found: {path}")
    payload = _read_json(path)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return payload


def build_arg_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""

    parser = argparse.ArgumentParser(
        description="Run deterministic retrieval evaluation for SkeinRank benchmarks."
    )
    parser.add_argument(
        "command", choices=["plan", "eval", "report"], help="Command to run."
    )
    parser.add_argument(
        "--benchmark-dir",
        default=None,
        help="Benchmark fixture directory. Defaults to platform_ops_v1.",
    )
    parser.add_argument("--out", default=None, help="Output report path for eval.")
    parser.add_argument("--file", default=None, help="Existing report path for report.")
    parser.add_argument("--top-k", type=int, default=10, help="Evaluation cutoff.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    try:
        paths = resolve_retrieval_paths(args.benchmark_dir)
        if args.command == "plan":
            print(
                json.dumps(
                    build_retrieval_plan(paths=paths), indent=2, ensure_ascii=False
                )
            )
            return 0
        if args.command == "eval":
            out = (
                Path(args.out).expanduser().resolve()
                if args.out
                else paths.default_report
            )
            report = run_retrieval_evaluation(paths=paths, top_k=args.top_k, out=out)
            print(
                json.dumps(
                    {
                        "status": report["status"],
                        "report": str(out),
                        "baseline": report["baseline"],
                        "skeinrank": report["skeinrank"],
                        "delta": report["delta"],
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
            return 0 if report["status"] == "passed" else 1
        report_file = (
            Path(args.file).expanduser().resolve()
            if args.file
            else paths.default_report
        )
        print_retrieval_report(report_file)
        return 0
    except RetrievalEvalError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


def _document_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    source_id = str(payload.get("source_id") or "")
    if not source_id:
        raise RetrievalEvalError("corpus document is missing source_id")
    title = str(payload.get("title") or "")
    body = str(payload.get("body") or "")
    return {
        "source_id": source_id,
        "source_type": str(payload.get("source_type") or "unknown"),
        "title": title,
        "body": body,
        "text": f"{title} {body}".strip(),
    }


def _baseline_terms(query: str) -> list[str]:
    return _dedupe(_tokens(query))


def _skeinrank_terms(query: str, *, alias_map: dict[str, set[str]]) -> list[str]:
    terms = _baseline_terms(query)
    normalized_query = _normalize_text(query)
    for phrase, expansions in alias_map.items():
        if _phrase_present(phrase, normalized_query):
            for expansion in sorted(expansions):
                terms.extend(_tokens(expansion))
                if " " in expansion:
                    terms.append(_normalize_text(expansion))
    return _dedupe(terms)


def _rank_documents(
    documents: list[dict[str, Any]], terms: list[str]
) -> list[dict[str, Any]]:
    ranking = []
    term_weights = Counter(terms)
    for document in documents:
        normalized_text = _normalize_text(document["text"])
        tokens = Counter(_tokens(document["text"]))
        score = 0.0
        matched_terms = []
        for term, weight in term_weights.items():
            if " " in term:
                if _phrase_present(term, normalized_text):
                    score += 3.0 * weight
                    matched_terms.append(term)
                continue
            count = tokens.get(term, 0)
            if count:
                score += float(count) * weight
                matched_terms.append(term)
        if score > 0:
            ranking.append(
                {
                    "source_id": document["source_id"],
                    "source_type": document["source_type"],
                    "title": document["title"],
                    "score": round(score, 4),
                    "matched_terms": sorted(set(matched_terms)),
                }
            )
    return sorted(ranking, key=lambda item: (-float(item["score"]), item["source_id"]))


def _compact_ranking(
    ranking: list[dict[str, Any]], qrels: dict[str, int], top_k: int
) -> list[dict[str, Any]]:
    compact = []
    for rank, item in enumerate(ranking[:top_k], 1):
        compact.append(
            {
                "rank": rank,
                "source_id": item["source_id"],
                "title": item["title"],
                "score": item["score"],
                "relevance": qrels.get(str(item["source_id"]), 0),
                "matched_terms": item["matched_terms"],
            }
        )
    return compact


def _metrics_for_query(
    *, ranking: list[dict[str, Any]], qrels: dict[str, int], top_k: int
) -> dict[str, float]:
    ranked_ids = [str(item["source_id"]) for item in ranking[:top_k]]
    relevant_ids = {doc_id for doc_id, relevance in qrels.items() if relevance > 0}
    hits = [doc_id for doc_id in ranked_ids if doc_id in relevant_ids]
    precision = _ratio(len(hits), top_k)
    recall = _ratio(len(hits), len(relevant_ids))
    reciprocal = 0.0
    for rank, doc_id in enumerate(ranked_ids, 1):
        if doc_id in relevant_ids:
            reciprocal = round(1.0 / rank, 4)
            break
    dcg = _dcg([qrels.get(doc_id, 0) for doc_id in ranked_ids])
    ideal = _dcg(sorted(qrels.values(), reverse=True)[:top_k])
    ndcg = _ratio(dcg, ideal)
    return {
        f"ndcg@{top_k}": ndcg,
        f"mrr@{top_k}": reciprocal,
        f"recall@{top_k}": recall,
        f"precision@{top_k}": precision,
    }


def _dcg(relevances: list[int]) -> float:
    score = 0.0
    for idx, relevance in enumerate(relevances, 1):
        if relevance <= 0:
            continue
        score += (2**relevance - 1) / math.log2(idx + 1)
    return score


def _aggregate_metrics(items: list[dict[str, float]]) -> dict[str, float]:
    if not items:
        return {}
    keys = sorted(items[0])
    return {
        key: round(sum(item[key] for item in items) / len(items), 4) for key in keys
    }


def _metric_delta(
    skeinrank: dict[str, float], baseline: dict[str, float]
) -> dict[str, float]:
    return {
        key: round(float(skeinrank.get(key, 0.0)) - float(baseline.get(key, 0.0)), 4)
        for key in sorted(set(skeinrank) | set(baseline))
    }


def _quality_gates(
    *, delta: dict[str, float], skeinrank: dict[str, float], thresholds: dict[str, Any]
) -> list[dict[str, Any]]:
    return [
        _threshold_check(
            name="retrieval_ndcg_delta_positive",
            actual=delta.get("ndcg@10", 0.0),
            expected=float(thresholds.get("min_ndcg_at_10_delta", 0.0)),
            op=">=",
            message="SkeinRank-expanded retrieval should improve NDCG@10.",
        ),
        _threshold_check(
            name="retrieval_mrr_delta_non_negative",
            actual=delta.get("mrr@10", 0.0),
            expected=float(thresholds.get("min_mrr_at_10_delta", 0.0)),
            op=">=",
            message="SkeinRank-expanded retrieval should not regress MRR@10.",
        ),
        _threshold_check(
            name="retrieval_recall_delta_positive",
            actual=delta.get("recall@10", 0.0),
            expected=float(thresholds.get("min_recall_at_10_delta", 0.0)),
            op=">=",
            message="SkeinRank-expanded retrieval should improve Recall@10.",
        ),
        _threshold_check(
            name="retrieval_skeinrank_ndcg_floor",
            actual=skeinrank.get("ndcg@10", 0.0),
            expected=float(thresholds.get("min_skeinrank_ndcg_at_10", 0.0)),
            op=">=",
            message="SkeinRank NDCG@10 should meet the benchmark floor.",
        ),
    ]


def _threshold_check(
    *, name: str, actual: float, expected: float, op: str, message: str
) -> dict[str, Any]:
    if op == ">=":
        passed = actual >= expected
    elif op == "<=":
        passed = actual <= expected
    else:  # pragma: no cover - developer error guard
        raise RetrievalEvalError(f"Unsupported threshold operator: {op}")
    return {
        "name": name,
        "status": "passed" if passed else "failed",
        "message": message,
        "details": {"actual": actual, "expected": expected, "operator": op},
    }


def _retrieval_thresholds(expected_aliases: dict[str, Any]) -> dict[str, Any]:
    thresholds = dict(expected_aliases.get("retrieval_quality_thresholds") or {})
    thresholds.setdefault("min_ndcg_at_10_delta", 0.01)
    thresholds.setdefault("min_mrr_at_10_delta", 0.0)
    thresholds.setdefault("min_recall_at_10_delta", 0.01)
    thresholds.setdefault("min_skeinrank_ndcg_at_10", 0.65)
    return thresholds


def _build_alias_map(
    *, seed_dictionary: dict[str, Any], expected_aliases: dict[str, Any]
) -> dict[str, set[str]]:
    by_canonical: dict[str, set[str]] = defaultdict(set)
    for term in seed_dictionary.get("terms") or []:
        if not isinstance(term, dict):
            continue
        canonical = str(term.get("canonical_value") or "").strip()
        if not canonical:
            continue
        by_canonical[_normalize_text(canonical)].add(canonical)
        for alias in term.get("aliases") or []:
            by_canonical[_normalize_text(canonical)].add(str(alias))
    for section in ("expected_new_aliases", "expected_idempotent_aliases"):
        for item in expected_aliases.get(section) or []:
            if isinstance(item, dict):
                alias = str(item.get("alias") or "").strip()
                canonical = str(item.get("canonical") or "").strip()
            else:
                alias = str(item).strip()
                canonical = ""
            if alias and canonical:
                by_canonical[_normalize_text(canonical)].update({alias, canonical})
    alias_map: dict[str, set[str]] = defaultdict(set)
    for canonical, values in by_canonical.items():
        values.add(canonical)
        for value in values:
            normalized_value = _normalize_text(value)
            alias_map[normalized_value].update(values)
    return {key: set(value) for key, value in alias_map.items()}


def _load_qrels(path: Path) -> dict[str, dict[str, int]]:
    qrels: dict[str, dict[str, int]] = defaultdict(dict)
    for item in _read_jsonl(path):
        query_id = str(item.get("query_id") or "")
        doc_id = str(item.get("doc_id") or item.get("source_id") or "")
        if not query_id or not doc_id:
            raise RetrievalEvalError(
                f"qrels row must include query_id and doc_id: {path}"
            )
        qrels[query_id][doc_id] = int(item.get("relevance", 0))
    return dict(qrels)


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)?", text.lower())


def _normalize_text(text: str) -> str:
    return " ".join(_tokens(text))


def _phrase_present(phrase: str, normalized_text: str) -> bool:
    normalized_phrase = _normalize_text(phrase)
    if not normalized_phrase:
        return False
    return f" {normalized_phrase} " in f" {normalized_text} "


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result = []
    for value in values:
        normalized = _normalize_text(value)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def _ratio(numerator: int | float, denominator: int | float) -> float:
    if denominator == 0:
        return 1.0
    return round(float(numerator) / float(denominator), 4)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RetrievalEvalError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise RetrievalEvalError(f"{path} must contain a JSON object")
    return payload


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), 1
    ):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise RetrievalEvalError(
                f"Invalid JSONL in {path}:{line_number}: {exc}"
            ) from exc
        if not isinstance(payload, dict):
            raise RetrievalEvalError(f"{path}:{line_number} must contain a JSON object")
        items.append(payload)
    return items


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
