from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
RUNBOOK = REPO_ROOT / "docs" / "pilots" / "first-company-pilot-runbook.md"
CHECKLIST = REPO_ROOT / "examples" / "pilots" / "first_company_pilot_checklist.md"


def _read(path: Path | str) -> str:
    p = Path(path)
    if not p.is_absolute():
        p = REPO_ROOT / p
    return p.read_text(encoding="utf-8")


def test_first_company_pilot_runbook_exists_and_documents_safety_boundaries() -> None:
    runbook = _read(RUNBOOK)

    assert "This runbook turns the benchmark and pilot pieces" in runbook
    assert "skeinrank.pilot.integration_report.v1" in runbook
    assert "Patch" not in runbook
    for fragment in [
        "OpenRouter calls: false",
        "proposal submission: false",
        "approve/apply: false",
        "snapshot publishing: false",
        "Elasticsearch writes: false",
        "runtime mutation after seed: false",
    ]:
        assert fragment in runbook


def test_first_company_pilot_runbook_references_existing_make_targets() -> None:
    runbook = _read(RUNBOOK)
    makefile = _read("Makefile")

    targets = [
        "benchmark-retrieval-eval",
        "benchmark-retrieval-report",
        "benchmark-smoke-generate",
        "benchmark-performance-report",
        "benchmark-performance-show",
        "benchmark-stack-run",
        "pilot-stack-run",
        "pilot-plan",
        "pilot-preflight",
        "pilot-seed",
        "pilot-eval",
        "pilot-report",
        "pilot-run",
        "benchmark-agent-live-validated-pilot-report",
    ]
    for target in targets:
        assert f"make {target}" in runbook
        assert f"{target}:" in makefile


def test_first_company_pilot_runbook_uses_existing_config_and_docs() -> None:
    runbook = _read(RUNBOOK)

    for relative in [
        "examples/pilots/elasticsearch_pilot.example.json",
        "docs/pilots/elasticsearch-pilot-integration.md",
        "docs/benchmarks/containerized-benchmark-integration.md",
        "docs/benchmarks/retrieval-eval-baseline.md",
        "docs/benchmarks/synthetic-smoke-generator.md",
        "docs/benchmarks/cost-latency-throughput-report.md",
        "docs/benchmarks/openrouter-live-pilot.md",
    ]:
        assert relative in runbook
        assert (REPO_ROOT / relative).exists()

    assert "PILOT_CONFIG=/tmp/skeinrank-company-pilot.json" in runbook
    assert "mode" in runbook and "dry_run" in runbook
    assert "filter_field" in runbook
    assert "filter_value" in runbook


def test_first_company_pilot_checklist_is_present_and_private_by_default() -> None:
    checklist = _read(CHECKLIST)

    assert "docs/pilots/first-company-pilot-runbook.md" in checklist
    assert "Keep completed company copies out of public commits." in checklist
    assert (
        "make pilot-preflight PILOT_CONFIG=/tmp/skeinrank-company-pilot.json"
        in checklist
    )
    assert "OpenRouter calls were disabled" in checklist
    assert "Pilot status: passed / needs tuning / blocked" in checklist


def test_first_company_pilot_runbook_is_linked_from_readmes() -> None:
    docs_readme = _read("docs/README.md")
    root_readme = _read("README.md")
    package_readme = _read("packages/skeinrank-governance-api/README.md")

    assert "pilots/first-company-pilot-runbook.md" in docs_readme
    assert "docs/pilots/first-company-pilot-runbook.md" in root_readme
    assert "first_company_pilot_checklist.md" in root_readme
    assert "first-company-pilot-runbook.md" in package_readme
