from __future__ import annotations

import json
from pathlib import Path

from skeinrank_governance_api.benchmark_performance import (
    BENCHMARK_PERFORMANCE_PLAN_VERSION,
    BENCHMARK_PERFORMANCE_REPORT_VERSION,
    build_benchmark_performance_plan,
    build_benchmark_performance_report,
    load_benchmark_performance_report,
)
from skeinrank_governance_api.benchmark_performance import (
    main as benchmark_performance_main,
)
from skeinrank_governance_api.synthetic_smoke import generate_synthetic_smoke_corpus

REPO_ROOT = Path(__file__).resolve().parents[3]


def _read(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def _manifest(tmp_path: Path) -> Path:
    manifest_path = tmp_path / "platform_ops_v1-5k-manifest.json"
    generate_synthetic_smoke_corpus(
        corpus_path=tmp_path / "platform_ops_v1-5k-corpus.jsonl",
        manifest_path=manifest_path,
        document_count=5000,
        batch_size=500,
    )
    return manifest_path


def _live_report(tmp_path: Path) -> Path:
    path = tmp_path / "openrouter-live-pilot-report.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "skeinrank.openrouter_live_pilot_cli_summary.v1",
                "status": "passed",
                "summary": {
                    "live_openrouter_calls": 3,
                    "candidates_sent_to_model": 3,
                    "proposals_prepared": 3,
                    "eligible_proposals": 2,
                    "cache_hits": 1,
                    "idempotent_existing_aliases": 1,
                    "errors": 0,
                    "estimated_cost_usd": 0.00070635,
                    "total_tokens": 4567,
                },
            }
        ),
        encoding="utf-8",
    )
    return path


def test_benchmark_performance_plan_is_offline_and_reads_synthetic_manifest(
    tmp_path: Path,
) -> None:
    manifest_path = _manifest(tmp_path)

    plan = build_benchmark_performance_plan(
        synthetic_manifest_path=manifest_path,
        elapsed_seconds=250,
        projection_documents=100_000,
    )

    assert plan["schema_version"] == BENCHMARK_PERFORMANCE_PLAN_VERSION
    assert plan["status"] == "planned"
    assert plan["workload"]["documents_total"] == 5000
    assert plan["workload"]["batches_total"] == 10
    assert plan["inputs"]["elapsed_seconds"] == 250.0
    assert plan["reports"] == [
        "cost",
        "latency",
        "throughput",
        "savings",
        "projection",
    ]
    assert plan["safety"] == {
        "openrouter_calls": False,
        "elasticsearch_calls": False,
        "database_calls": False,
        "runtime_mutation_enabled": False,
        "generated_report_committed_by_default": False,
    }


def test_benchmark_performance_report_calculates_cost_latency_and_throughput(
    tmp_path: Path,
) -> None:
    manifest_path = _manifest(tmp_path)
    live_report_path = _live_report(tmp_path)
    out = tmp_path / "performance-report.json"

    report = build_benchmark_performance_report(
        synthetic_manifest_path=manifest_path,
        live_report_path=live_report_path,
        elapsed_seconds=250,
        projection_documents=100_000,
        out=out,
        failed_documents=2,
        retried_documents=1,
    )

    assert out.exists()
    assert report == load_benchmark_performance_report(out)
    assert report["schema_version"] == BENCHMARK_PERFORMANCE_REPORT_VERSION
    assert report["status"] == "reported"
    assert report["measurement_mode"] == "offline_estimate"
    assert report["workload"]["documents_total"] == 5000
    assert report["workload"]["processed_documents"] == 4750
    assert report["workload"]["failed_documents"] == 2
    assert report["workload"]["retried_documents"] == 1
    assert report["latency"]["elapsed_seconds"] == 250.0
    assert report["latency"]["documents_per_minute"] == 1200.0
    assert report["latency"]["average_batch_latency_seconds"] == 25.0
    assert report["usage"]["llm_calls"] == 3
    assert report["usage"]["total_tokens"] == 4567
    assert report["usage"]["estimated_cost_usd"] == 0.00070635
    assert report["unit_costs"]["tokens_per_llm_call"] == 1522.333333
    assert report["unit_costs"]["cost_per_1k_documents_usd"] == 0.000141
    assert report["savings"]["skipped_unchanged_documents"] == 250
    assert report["savings"]["cache_hits"] == 1
    assert report["savings"]["idempotent_existing_aliases"] == 1
    assert report["savings"]["skip_rate"] == 0.05
    assert report["projection"]["projection_documents"] == 100000
    assert report["projection"]["estimated_elapsed_minutes"] == 83.333333
    assert report["projection"]["estimated_cost_usd"] == 0.014127
    assert report["safety"]["openrouter_calls"] is False
    assert any("real worker timings" in item for item in report["recommendations"])


def test_benchmark_performance_report_supports_explicit_usage_without_live_report(
    tmp_path: Path,
) -> None:
    manifest_path = _manifest(tmp_path)

    report = build_benchmark_performance_report(
        synthetic_manifest_path=manifest_path,
        elapsed_seconds=500,
        llm_calls=10,
        prompt_tokens=1000,
        completion_tokens=250,
        estimated_cost_usd=0.02,
        skipped_unchanged=100,
        cache_hits=2,
        idempotent_existing_aliases=3,
    )

    assert report["usage"]["total_tokens"] == 1250
    assert report["usage"]["llm_calls"] == 10
    assert report["usage"]["cache_hits"] == 2
    assert report["workload"]["processed_documents"] == 4900
    assert report["savings"]["saved_work_items_estimate"] == 105
    assert report["unit_costs"]["cost_per_llm_call_usd"] == 0.002


def test_benchmark_performance_cli_plan_report_and_show(tmp_path: Path, capsys) -> None:
    manifest_path = _manifest(tmp_path)
    live_report_path = _live_report(tmp_path)
    out = tmp_path / "cli-performance-report.json"

    assert (
        benchmark_performance_main(
            [
                "plan",
                "--synthetic-manifest",
                str(manifest_path),
                "--elapsed-seconds",
                "250",
            ]
        )
        == 0
    )
    plan_stdout = capsys.readouterr().out
    assert '"schema_version": "skeinrank.benchmark_performance_plan.v1"' in plan_stdout
    assert '"documents_total": 5000' in plan_stdout

    assert (
        benchmark_performance_main(
            [
                "report",
                "--synthetic-manifest",
                str(manifest_path),
                "--live-report",
                str(live_report_path),
                "--elapsed-seconds",
                "250",
                "--out",
                str(out),
            ]
        )
        == 0
    )
    report_stdout = capsys.readouterr().out
    assert (
        '"schema_version": "skeinrank.benchmark_performance_report.v1"' in report_stdout
    )
    assert out.exists()

    assert benchmark_performance_main(["show", "--file", str(out)]) == 0
    show_stdout = capsys.readouterr().out
    assert '"documents_per_minute": 1200.0' in show_stdout


def test_benchmark_performance_docs_makefile_and_scripts_are_linked() -> None:
    makefile = _read("Makefile")
    docs_readme = _read("docs/README.md")
    root_readme = _read("README.md")
    package_readme = _read("packages/skeinrank-governance-api/README.md")
    guide = _read("docs/benchmarks/cost-latency-throughput-report.md")
    pyproject = _read("packages/skeinrank-governance-api/pyproject.toml")
    benchmark_readme = _read("examples/benchmarks/platform_ops_v1/README.md")

    for target in [
        "benchmark-performance-plan:",
        "benchmark-performance-report:",
        "benchmark-performance-show:",
        "benchmark-performance-clean:",
    ]:
        assert target in makefile

    assert "skeinrank_governance_api.benchmark_performance" in makefile
    assert "BENCHMARK_PERFORMANCE_ELAPSED_SECONDS" in makefile
    assert "benchmarks/cost-latency-throughput-report.md" in docs_readme
    assert "benchmark-performance-report" in root_readme
    assert "skeinrank-governance-benchmark-performance" in package_readme
    assert "skeinrank-governance-benchmark-performance" in pyproject
    assert "skeinrank.benchmark_performance_report.v1" in guide
    assert "OpenRouter calls: false" in guide
    assert "benchmark-performance-report" in benchmark_readme
