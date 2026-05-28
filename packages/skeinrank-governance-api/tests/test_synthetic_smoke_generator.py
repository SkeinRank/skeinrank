from __future__ import annotations

import json
from pathlib import Path

from skeinrank_governance_api.synthetic_smoke import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_DOCUMENT_COUNT,
    SYNTHETIC_SMOKE_DOCUMENT_VERSION,
    SYNTHETIC_SMOKE_MANIFEST_VERSION,
    SYNTHETIC_SMOKE_PLAN_VERSION,
    build_synthetic_smoke_plan,
    generate_synthetic_smoke_corpus,
    load_synthetic_smoke_manifest,
)
from skeinrank_governance_api.synthetic_smoke import (
    main as synthetic_smoke_main,
)

REPO_ROOT = Path(__file__).resolve().parents[3]


def _read(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def test_synthetic_smoke_plan_is_offline_and_counts_5k() -> None:
    plan = build_synthetic_smoke_plan()

    assert plan["schema_version"] == SYNTHETIC_SMOKE_PLAN_VERSION
    assert plan["status"] == "planned"
    assert plan["document_count"] == DEFAULT_DOCUMENT_COUNT
    assert plan["batch_size"] == DEFAULT_BATCH_SIZE
    assert plan["batches_total"] == 10
    assert plan["roles"] == {
        "golden_relevant": 1000,
        "hard_negative": 1000,
        "near_duplicate": 1000,
        "semantic_noise": 1000,
        "weak_platform_adjacent": 1000,
    }
    assert plan["safety"] == {
        "openrouter_calls": False,
        "elasticsearch_calls": False,
        "database_calls": False,
        "runtime_mutation_enabled": False,
        "generated_corpus_committed_by_default": False,
    }


def test_synthetic_smoke_generator_writes_deterministic_5k_manifest(
    tmp_path: Path,
) -> None:
    corpus_path = tmp_path / "platform_ops_v1-5k-corpus.jsonl"
    manifest_path = tmp_path / "platform_ops_v1-5k-manifest.json"

    manifest = generate_synthetic_smoke_corpus(
        corpus_path=corpus_path,
        manifest_path=manifest_path,
    )

    assert corpus_path.exists()
    assert manifest_path.exists()
    assert manifest["schema_version"] == SYNTHETIC_SMOKE_MANIFEST_VERSION
    assert manifest["status"] == "generated"
    assert manifest["document_count"] == 5000
    assert manifest["batch_size"] == 500
    assert manifest["batches_total"] == 10
    assert manifest["first_source_id"] == "synthetic-5k-00001"
    assert manifest["last_source_id"] == "synthetic-5k-05000"
    assert manifest["role_counts"] == {
        "golden_relevant": 1000,
        "hard_negative": 1000,
        "near_duplicate": 1000,
        "semantic_noise": 1000,
        "weak_platform_adjacent": 1000,
    }
    assert manifest["unchanged_skip_candidates"] > 0
    assert len(manifest["corpus_sha256"]) == 64
    assert all(item["documents_total"] == 500 for item in manifest["batches"])

    lines = corpus_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 5000
    first = json.loads(lines[0])
    last = json.loads(lines[-1])
    assert first["schema_version"] == SYNTHETIC_SMOKE_DOCUMENT_VERSION
    assert first["source_id"] == "synthetic-5k-00001"
    assert first["synthetic_role"] == "semantic_noise"
    assert first["batch_id"] == 0
    assert last["source_id"] == "synthetic-5k-05000"
    assert last["batch_id"] == 9
    assert {"source_id", "source_type", "title", "body", "aliases"}.issubset(first)

    second_manifest = generate_synthetic_smoke_corpus(
        corpus_path=tmp_path / "again.jsonl",
        manifest_path=tmp_path / "again-manifest.json",
    )
    assert second_manifest["corpus_sha256"] == manifest["corpus_sha256"]


def test_synthetic_smoke_generator_supports_smaller_custom_batches(
    tmp_path: Path,
) -> None:
    manifest = generate_synthetic_smoke_corpus(
        corpus_path=tmp_path / "custom.jsonl",
        manifest_path=tmp_path / "custom-manifest.json",
        document_count=37,
        batch_size=10,
    )

    assert manifest["document_count"] == 37
    assert manifest["batch_size"] == 10
    assert manifest["batches_total"] == 4
    assert manifest["batches"][-1]["documents_total"] == 7
    assert sum(manifest["role_counts"].values()) == 37
    assert load_synthetic_smoke_manifest(tmp_path / "custom-manifest.json") == manifest


def test_synthetic_smoke_cli_plan_generate_and_report(tmp_path: Path, capsys) -> None:
    corpus_path = tmp_path / "cli-corpus.jsonl"
    manifest_path = tmp_path / "cli-manifest.json"

    assert (
        synthetic_smoke_main(["plan", "--documents", "25", "--batch-size", "10"]) == 0
    )
    plan_stdout = capsys.readouterr().out
    assert '"schema_version": "skeinrank.synthetic_smoke_plan.v1"' in plan_stdout
    assert '"batches_total": 3' in plan_stdout

    assert (
        synthetic_smoke_main(
            [
                "generate",
                "--documents",
                "25",
                "--batch-size",
                "10",
                "--out",
                str(corpus_path),
                "--manifest",
                str(manifest_path),
            ]
        )
        == 0
    )
    generate_stdout = capsys.readouterr().out
    assert '"documents_total": 25' in generate_stdout
    assert corpus_path.exists()
    assert manifest_path.exists()

    assert synthetic_smoke_main(["report", "--manifest", str(manifest_path)]) == 0
    report_stdout = capsys.readouterr().out
    assert '"schema_version": "skeinrank.synthetic_smoke_manifest.v1"' in report_stdout
    assert '"document_count": 25' in report_stdout


def test_synthetic_smoke_docs_and_makefile_targets_are_linked() -> None:
    makefile = _read("Makefile")
    docs_readme = _read("docs/README.md")
    root_readme = _read("README.md")
    package_readme = _read("packages/skeinrank-governance-api/README.md")
    guide = _read("docs/benchmarks/synthetic-smoke-generator.md")
    pyproject = _read("packages/skeinrank-governance-api/pyproject.toml")
    gitignore = _read(".gitignore")

    for target in [
        "benchmark-smoke-plan:",
        "benchmark-smoke-generate:",
        "benchmark-smoke-report:",
        "benchmark-smoke-clean:",
    ]:
        assert target in makefile

    assert "skeinrank_governance_api.synthetic_smoke" in makefile
    assert "BENCHMARK_SYNTHETIC_SMOKE_CORPUS" in makefile
    assert "benchmarks/synthetic-smoke-generator.md" in docs_readme
    assert "benchmark-smoke-generate" in root_readme
    assert "skeinrank-governance-synthetic-smoke" in package_readme
    assert "skeinrank-governance-synthetic-smoke" in pyproject
    assert "skeinrank.synthetic_smoke_manifest.v1" in guide
    assert "OpenRouter calls: false" in guide
    assert "examples/benchmarks/platform_ops_v1/reports/" in gitignore
