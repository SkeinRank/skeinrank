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
    hard_negatives: Path
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
        hard_negatives=root / "hard_negatives.jsonl",
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
            paths.hard_negatives,
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
    hard_negatives = _load_hard_negatives(paths.hard_negatives)
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
        "hard_negatives_total": sum(len(values) for values in hard_negatives.values()),
        "alias_terms_total": len(alias_map),
        "runs": ["baseline", "skeinrank"],
        "metrics": [
            "ndcg@10",
            "mrr@10",
            "recall@10",
            "precision@10",
            "hard_negative_leakage@10",
        ],
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
            "hard_negatives": str(paths.hard_negatives),
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
    hard_negatives = _load_hard_negatives(paths.hard_negatives)
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
        query_hard_negatives = hard_negatives.get(query_id, set())
        baseline_terms = _baseline_terms(text)
        expanded = _skeinrank_terms(text, alias_map=alias_map)
        baseline_ranking = _rank_documents(documents, baseline_terms)
        skeinrank_ranking = _rank_documents(documents, expanded)
        baseline_metrics = _metrics_for_query(
            ranking=baseline_ranking,
            qrels=relevant,
            hard_negatives=query_hard_negatives,
            top_k=top_k,
        )
        skeinrank_metrics = _metrics_for_query(
            ranking=skeinrank_ranking,
            qrels=relevant,
            hard_negatives=query_hard_negatives,
            top_k=top_k,
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
                "hard_negative_documents": sorted(query_hard_negatives),
                "baseline": {
                    "terms": baseline_terms,
                    "metrics": baseline_metrics,
                    "top_documents": _compact_ranking(
                        baseline_ranking, relevant, query_hard_negatives, top_k
                    ),
                },
                "skeinrank": {
                    "terms": expanded,
                    "added_terms": [
                        term for term in expanded if term not in baseline_terms
                    ],
                    "metrics": skeinrank_metrics,
                    "top_documents": _compact_ranking(
                        skeinrank_ranking, relevant, query_hard_negatives, top_k
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
        "hard_negatives_total": sum(len(values) for values in hard_negatives.values()),
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
    term_counts = Counter(terms)
    for document in documents:
        normalized_text = _normalize_text(document["text"])
        tokens = Counter(_tokens(document["text"]))
        score = 0.0
        matched_terms = []
        weighted_matches: dict[str, float] = {}
        for term, count_weight in term_counts.items():
            term_weight = _retrieval_term_weight(term) * float(count_weight)
            if " " in term:
                if _phrase_present(term, normalized_text):
                    contribution = 3.0 * term_weight
                    score += contribution
                    matched_terms.append(term)
                    weighted_matches[term] = round(contribution, 4)
                continue
            count = tokens.get(term, 0)
            if count:
                contribution = float(count) * term_weight
                score += contribution
                matched_terms.append(term)
                weighted_matches[term] = round(contribution, 4)
        noise_penalty = _retrieval_noise_penalty(
            tokens=tokens, matched_terms=matched_terms
        )
        score = max(0.0, score - noise_penalty)
        if score > 0:
            ranking.append(
                {
                    "source_id": document["source_id"],
                    "source_type": document["source_type"],
                    "title": document["title"],
                    "score": round(score, 4),
                    "matched_terms": sorted(set(matched_terms)),
                    "noise_penalty": round(noise_penalty, 4),
                    "weighted_matches": weighted_matches,
                }
            )
    return sorted(ranking, key=lambda item: (-float(item["score"]), item["source_id"]))


def _compact_ranking(
    ranking: list[dict[str, Any]],
    qrels: dict[str, int],
    hard_negatives: set[str],
    top_k: int,
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
                "hard_negative": _is_hard_negative_result(item, hard_negatives),
                "matched_terms": item["matched_terms"],
                "generic_token_noise": _generic_token_noise(item["matched_terms"]),
                "noise_penalty": item.get("noise_penalty", 0.0),
            }
        )
    return compact


def _metrics_for_query(
    *,
    ranking: list[dict[str, Any]],
    qrels: dict[str, int],
    hard_negatives: set[str],
    top_k: int,
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
    ranked_items = ranking[:top_k]
    hard_negative_hits = [
        str(item["source_id"])
        for item in ranked_items
        if _is_hard_negative_result(item, hard_negatives)
    ]
    hard_negative_leakage = _ratio(len(hard_negative_hits), top_k)
    generic_noise = _ratio(
        sum(
            _generic_token_noise(item.get("matched_terms", [])) for item in ranked_items
        ),
        top_k,
    )
    return {
        f"ndcg@{top_k}": ndcg,
        f"mrr@{top_k}": reciprocal,
        f"recall@{top_k}": recall,
        f"precision@{top_k}": precision,
        f"hard_negative_leakage@{top_k}": hard_negative_leakage,
        f"generic_token_noise@{top_k}": generic_noise,
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
    hard_negative_delta_key = "hard_negative_leakage@10"
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
        _threshold_check(
            name="retrieval_hard_negative_leakage_ceiling",
            actual=skeinrank.get("hard_negative_leakage@10", 0.0),
            expected=float(
                thresholds.get("max_skeinrank_hard_negative_leakage_at_10", 1.0)
            ),
            op="<=",
            message=(
                "SkeinRank top-10 should keep hard-negative leakage "
                "below the ceiling."
            ),
        ),
        _threshold_check(
            name="retrieval_hard_negative_leakage_delta_ceiling",
            actual=delta.get(hard_negative_delta_key, 0.0),
            expected=float(
                thresholds.get("max_hard_negative_leakage_at_10_delta", 1.0)
            ),
            op="<=",
            message=(
                "SkeinRank expansion should not materially increase "
                "hard-negative leakage."
            ),
        ),
        _threshold_check(
            name="retrieval_generic_token_noise_delta_ceiling",
            actual=delta.get("generic_token_noise@10", 0.0),
            expected=float(thresholds.get("max_generic_token_noise_at_10_delta", 1.0)),
            op="<=",
            message="SkeinRank expansion should not amplify generic-token noise.",
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
    thresholds.setdefault("max_skeinrank_hard_negative_leakage_at_10", 0.25)
    thresholds.setdefault("max_hard_negative_leakage_at_10_delta", 0.05)
    thresholds.setdefault("max_generic_token_noise_at_10_delta", 0.05)
    return thresholds


def _build_alias_map(
    *, seed_dictionary: dict[str, Any], expected_aliases: dict[str, Any]
) -> dict[str, set[str]]:
    # The retrieval evaluator intentionally expands from observed aliases to
    # canonical values, not from canonical values back to every alias. Expanding
    # canonical terms such as "service" -> "svc" or "namespace" -> "ns" makes
    # hard negatives unrealistically strong and hides query hygiene issues.
    alias_map: dict[str, set[str]] = defaultdict(set)

    def register(alias: str, canonical: str) -> None:
        normalized_alias = _normalize_text(alias)
        normalized_canonical = _normalize_text(canonical)
        if not normalized_alias or not normalized_canonical:
            return
        if normalized_alias == normalized_canonical:
            return
        alias_map[normalized_alias].add(canonical)

    for term in seed_dictionary.get("terms") or []:
        if not isinstance(term, dict):
            continue
        canonical = str(term.get("canonical_value") or "").strip()
        if not canonical:
            continue
        for alias in term.get("aliases") or []:
            register(str(alias), canonical)

    for section in ("expected_new_aliases", "expected_idempotent_aliases"):
        for item in expected_aliases.get(section) or []:
            if not isinstance(item, dict):
                continue
            register(str(item.get("alias") or ""), str(item.get("canonical") or ""))

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


def _load_hard_negatives(path: Path) -> dict[str, set[str]]:
    hard_negatives: dict[str, set[str]] = defaultdict(set)
    for item in _read_jsonl(path):
        query_id = str(item.get("query_id") or "")
        doc_id = str(item.get("doc_id") or item.get("source_id") or "")
        if not query_id or not doc_id:
            raise RetrievalEvalError(
                f"hard negatives row must include query_id and doc_id: {path}"
            )
        hard_negatives[query_id].add(doc_id)
    return {key: set(values) for key, values in hard_negatives.items()}


_RETRIEVAL_STOPWORDS = {
    "a",
    "an",
    "and",
    "after",
    "before",
    "for",
    "from",
    "in",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
}

_TOKEN_NORMALIZATION = {
    "alerts": "alert",
    "clusters": "cluster",
    "documents": "document",
    "errors": "error",
    "jobs": "job",
    "logs": "log",
    "metrics": "metric",
    "namespaces": "namespace",
    "queries": "query",
    "requests": "request",
    "retries": "retry",
    "rollouts": "rollout",
    "runbooks": "runbook",
    "services": "service",
    "spans": "span",
    "timeouts": "timeout",
    "traces": "trace",
}

_HIGH_VALUE_TERMS = {
    "k8s",
    "kube",
    "kubernetes",
    "rmq",
    "rabbitmq",
    "otel",
    "opentelemetry",
    "prom",
    "prometheus",
    "lk",
    "loki",
    "pg",
    "postgres",
    "postgresql",
    "redis-sentinel",
    "redis-cluster",
    "redis sentinel",
    "redis cluster",
    "slo",
    "service level objective",
    "elastic",
    "elasticsearch",
}

_MEDIUM_VALUE_TERMS = {
    "namespace",
    "ns",
    "svc",
    "selector",
    "rollout",
    "trace",
    "log",
    "metric",
    "alert",
    "queue",
    "failover",
    "reshard",
    "indexing",
    "latency",
    "timeout",
    "drain",
}

_GENERIC_RETRIEVAL_TERMS = {
    "api",
    "app",
    "error",
    "export",
    "group",
    "job",
    "page",
    "service",
    "state",
}

_NOISE_CONTEXT_TOKENS = {
    "business",
    "center",
    "customer",
    "desk",
    "employee",
    "facilities",
    "facility",
    "marketing",
    "office",
    "partner",
    "posting",
    "product",
    "survey",
    "typo",
    "unrelated",
}


def _tokens(text: str) -> list[str]:
    tokens = []
    for raw_token in re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)?", text.lower()):
        token = _TOKEN_NORMALIZATION.get(raw_token, raw_token)
        if token not in _RETRIEVAL_STOPWORDS:
            tokens.append(token)
    return tokens


def _retrieval_term_weight(term: str) -> float:
    if term in _HIGH_VALUE_TERMS:
        return 3.0
    if term in _MEDIUM_VALUE_TERMS:
        return 1.8
    if term in _GENERIC_RETRIEVAL_TERMS:
        return 0.25
    if " " in term:
        return 2.0
    return 1.0


def _retrieval_noise_penalty(
    *, tokens: Counter[str], matched_terms: list[str]
) -> float:
    if not matched_terms:
        return 0.0
    matched_generic = {
        term for term in matched_terms if term in _GENERIC_RETRIEVAL_TERMS
    }
    if not matched_generic:
        return 0.0
    noise_hits = sum(tokens.get(token, 0) for token in _NOISE_CONTEXT_TOKENS)
    return min(3.0, 0.75 * float(noise_hits))


def _is_hard_negative_result(item: dict[str, Any], hard_negatives: set[str]) -> bool:
    return (
        str(item["source_id"]) in hard_negatives
        or item.get("source_type") == "hard_negative"
    )


def _generic_token_noise(matched_terms: list[str]) -> int:
    return sum(1 for term in set(matched_terms) if term in _GENERIC_RETRIEVAL_TERMS)


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
