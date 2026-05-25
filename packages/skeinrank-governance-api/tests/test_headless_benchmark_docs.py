from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_makefile_exposes_headless_benchmark_targets() -> None:
    makefile = _read("Makefile")

    for target in [
        "benchmark-reset",
        "benchmark-seed",
        "benchmark-eval",
        "benchmark-report",
        "benchmark-clean",
    ]:
        assert f"{target}:" in makefile
    assert "skeinrank_governance_api.benchmark" in makefile


def test_benchmark_docs_and_fixtures_are_discoverable() -> None:
    docs = _read("docs/benchmarks/headless-agent-workflow.md")
    root_readme = _read("README.md")
    package_readme = _read("packages/skeinrank-governance-api/README.md")
    pyproject = _read("packages/skeinrank-governance-api/pyproject.toml")

    assert "48A" in docs
    assert "49A" in docs
    assert "make benchmark-eval" in docs
    assert "proposal_precision_like" in docs
    assert "OpenRouter" in docs
    assert "examples/benchmarks/platform_ops_v1" in docs
    assert "Headless benchmark" in root_readme
    assert "skeinrank-governance-benchmark" in package_readme
    assert "skeinrank-governance-benchmark" in pyproject


def test_benchmark_fixture_files_exist() -> None:
    fixture_root = ROOT / "examples/benchmarks/platform_ops_v1"
    for relative in [
        "README.md",
        "seed_dictionary.json",
        "corpus.jsonl",
        "expected_aliases.json",
        "golden_queries.jsonl",
    ]:
        assert (fixture_root / relative).exists()
