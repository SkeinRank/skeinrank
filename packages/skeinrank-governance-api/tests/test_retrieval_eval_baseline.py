from __future__ import annotations

import json
from pathlib import Path

from skeinrank_governance_api.retrieval_eval import (
    build_retrieval_plan,
    resolve_retrieval_paths,
    run_retrieval_evaluation,
)

REPO_ROOT = Path(__file__).resolve().parents[3]


def _read(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def test_retrieval_fixture_files_exist_and_are_well_formed() -> None:
    fixture_root = REPO_ROOT / "examples/benchmarks/platform_ops_v1"
    queries = fixture_root / "retrieval_queries.jsonl"
    qrels = fixture_root / "qrels.jsonl"

    assert queries.exists()
    assert qrels.exists()

    query_rows = [json.loads(line) for line in queries.read_text().splitlines()]
    qrel_rows = [json.loads(line) for line in qrels.read_text().splitlines()]

    assert len(query_rows) >= 7
    assert len(qrel_rows) >= 25
    assert {"query_id", "query", "expected_expansions"}.issubset(query_rows[0])
    assert {"query_id", "doc_id", "relevance"}.issubset(qrel_rows[0])


def test_retrieval_plan_is_offline_and_counts_fixtures() -> None:
    plan = build_retrieval_plan(paths=resolve_retrieval_paths())

    assert plan["schema_version"] == "skeinrank.retrieval_eval_plan.v1"
    assert plan["documents_total"] == 50
    assert plan["queries_total"] >= 7
    assert plan["qrels_total"] >= 25
    assert plan["runs"] == ["baseline", "skeinrank"]
    assert plan["safety"] == {
        "openrouter_calls": False,
        "elasticsearch_calls": False,
        "database_calls": False,
        "runtime_mutation_enabled": False,
    }


def test_retrieval_eval_reports_positive_skeinrank_delta(tmp_path: Path) -> None:
    report_path = tmp_path / "retrieval-report.json"
    report = run_retrieval_evaluation(paths=resolve_retrieval_paths(), out=report_path)

    assert report_path.exists()
    assert report["schema_version"] == "skeinrank.retrieval_eval_report.v1"
    assert report["status"] == "passed"
    assert report["documents_total"] == 50
    assert report["queries_total"] >= 7
    assert report["delta"]["ndcg@10"] > 0
    assert report["delta"]["recall@10"] > 0
    assert report["skeinrank"]["ndcg@10"] >= report["baseline"]["ndcg@10"]
    assert all(item["status"] == "passed" for item in report["quality_gates"])


def test_retrieval_eval_per_query_exposes_expansions_and_rankings(
    tmp_path: Path,
) -> None:
    report = run_retrieval_evaluation(
        paths=resolve_retrieval_paths(), out=tmp_path / "retrieval-report.json"
    )

    first = report["per_query"][0]
    assert {"query_id", "baseline", "skeinrank", "delta"}.issubset(first)
    assert first["skeinrank"]["added_terms"]
    assert first["baseline"]["top_documents"]
    assert first["skeinrank"]["top_documents"]


def test_makefile_exposes_retrieval_eval_targets() -> None:
    makefile = _read("Makefile")

    for target in [
        "benchmark-retrieval-plan:",
        "benchmark-retrieval-eval:",
        "benchmark-retrieval-report:",
        "benchmark-retrieval-clean:",
    ]:
        assert target in makefile

    assert "skeinrank_governance_api.retrieval_eval" in makefile
    assert "BENCHMARK_RETRIEVAL_REPORT" in makefile


def test_retrieval_eval_docs_are_linked() -> None:
    docs_readme = _read("docs/README.md")
    root_readme = _read("README.md")
    package_readme = _read("packages/skeinrank-governance-api/README.md")
    guide = _read("docs/benchmarks/retrieval-eval-baseline.md")
    pyproject = _read("packages/skeinrank-governance-api/pyproject.toml")

    assert "benchmarks/retrieval-eval-baseline.md" in docs_readme
    assert "benchmark-retrieval-eval" in root_readme
    assert "skeinrank-governance-retrieval-eval" in package_readme
    assert "skeinrank-governance-retrieval-eval" in pyproject
    assert "NDCG@10" in guide
    assert "qrels.jsonl" in guide
    assert "skeinrank.retrieval_eval_report.v1" in guide
