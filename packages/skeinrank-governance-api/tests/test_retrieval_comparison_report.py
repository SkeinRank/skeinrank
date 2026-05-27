from __future__ import annotations

import json
from pathlib import Path

from skeinrank_governance_api.retrieval_compare import (
    RETRIEVAL_COMPARISON_REPORT_VERSION,
    build_retrieval_comparison_report,
    write_retrieval_comparison_report,
)
from skeinrank_governance_api.retrieval_eval import (
    resolve_retrieval_paths,
    run_retrieval_evaluation,
)

REPO_ROOT = Path(__file__).resolve().parents[3]


def _read(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def _eval_report(tmp_path: Path) -> dict[str, object]:
    return run_retrieval_evaluation(
        paths=resolve_retrieval_paths(), out=tmp_path / "retrieval-report.json"
    )


def test_retrieval_comparison_report_summarizes_query_outcomes(tmp_path: Path) -> None:
    source = _eval_report(tmp_path)
    report = build_retrieval_comparison_report(source, source_report="memory")

    assert report["schema_version"] == RETRIEVAL_COMPARISON_REPORT_VERSION
    assert report["source_schema_version"] == "skeinrank.retrieval_eval_report.v1"
    assert report["status"] == "passed"
    assert report["queries_total"] == source["queries_total"]
    assert report["query_counts"]["ndcg_improved"] > 0
    assert report["query_counts"]["high_hard_negative_leakage"] > 0
    assert report["query_groups"]["largest_ndcg_improvements"]
    assert report["query_groups"]["high_hard_negative_leakage"]
    assert report["recommendations"]
    assert report["safety"] == {
        "openrouter_calls": False,
        "elasticsearch_calls": False,
        "database_calls": False,
        "runtime_mutation_enabled": False,
    }
    assert all(item["status"] == "passed" for item in report["quality_gates"])


def test_retrieval_comparison_query_diagnostics_are_operator_facing(
    tmp_path: Path,
) -> None:
    report = build_retrieval_comparison_report(_eval_report(tmp_path))

    diagnostics = report["query_diagnostics"]
    assert diagnostics
    first = diagnostics[0]
    assert {
        "query_id",
        "query",
        "outcome",
        "added_terms",
        "first_relevant_rank",
        "top10",
        "risk_flags",
        "recommended_actions",
    }.issubset(first)
    assert any(item["added_terms"] for item in diagnostics)
    assert any(
        "hard-negative" in " ".join(item["recommended_actions"])
        or "hard-negative" in json.dumps(item["recommended_actions"])
        for item in diagnostics
    )


def test_write_retrieval_comparison_report_reads_and_writes_files(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "retrieval-report.json"
    run_retrieval_evaluation(paths=resolve_retrieval_paths(), out=source_path)
    comparison_path = tmp_path / "retrieval-comparison-report.json"

    report = write_retrieval_comparison_report(
        input_report=source_path, out=comparison_path, limit=3
    )

    assert comparison_path.exists()
    payload = json.loads(comparison_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == RETRIEVAL_COMPARISON_REPORT_VERSION
    assert payload["source_report"] == str(source_path)
    assert len(payload["query_groups"]["largest_ndcg_improvements"]) <= 3
    assert report["schema_version"] == payload["schema_version"]


def test_makefile_exposes_retrieval_comparison_targets() -> None:
    makefile = _read("Makefile")

    for target in [
        "benchmark-retrieval-compare:",
        "benchmark-retrieval-compare-report:",
        "benchmark-retrieval-run:",
    ]:
        assert target in makefile

    assert "skeinrank_governance_api.retrieval_compare" in makefile
    assert "BENCHMARK_RETRIEVAL_COMPARISON_REPORT" in makefile


def test_retrieval_comparison_docs_are_linked() -> None:
    docs_readme = _read("docs/README.md")
    root_readme = _read("README.md")
    package_readme = _read("packages/skeinrank-governance-api/README.md")
    guide = _read("docs/benchmarks/retrieval-eval-baseline.md")
    pyproject = _read("packages/skeinrank-governance-api/pyproject.toml")

    assert "benchmark-retrieval-compare" in root_readme
    assert "skeinrank-governance-retrieval-compare" in package_readme
    assert "skeinrank-governance-retrieval-compare" in pyproject
    assert "retrieval comparison report" in guide
    assert "skeinrank.retrieval_comparison_report.v1" in guide
    assert "benchmark-retrieval-compare" in docs_readme
