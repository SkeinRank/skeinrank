from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parents[3]
BENCHMARK_DOCS = [
    ROOT / "docs/benchmarks/headless-agent-workflow.md",
    ROOT / "docs/benchmarks/openrouter-live-pilot.md",
    ROOT / "docs/benchmarks/containerized-benchmark-integration.md",
    ROOT / "docs/benchmarks/retrieval-eval-baseline.md",
    ROOT / "docs/benchmarks/synthetic-smoke-generator.md",
    ROOT / "docs/benchmarks/cost-latency-throughput-report.md",
]
DEV_LOG_PATTERNS = [
    re.compile(r"\b[Pp]atch\b"),
    re.compile(r"\b[0-9]{2}[A-Z](?:\.\d+)?\b"),
    re.compile(r"\badds?\b.*\bbenchmark\b", re.IGNORECASE),
]
MARKDOWN_LINK_RE = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_benchmark_docs_do_not_read_like_development_log() -> None:
    for path in BENCHMARK_DOCS:
        content = _read(path)
        for pattern in DEV_LOG_PATTERNS:
            assert not pattern.search(content), f"{path} still has dev-log wording"


def test_benchmark_docs_keep_product_surfaces_discoverable() -> None:
    combined = "\n".join(_read(path) for path in BENCHMARK_DOCS)

    for fragment in [
        "examples/benchmarks/platform_ops_v1",
        "make benchmark-eval",
        "make benchmark-retrieval-eval",
        "make benchmark-stack-run",
        "make benchmark-smoke-generate",
        "make benchmark-performance-report",
        "make benchmark-agent-live-validated-pilot-report",
        "skeinrank.benchmark_report.v1",
        "skeinrank.benchmark_stack_report.v1",
        "skeinrank.retrieval_eval_report.v1",
        "skeinrank.retrieval_comparison_report.v1",
        "skeinrank.synthetic_smoke_manifest.v1",
        "skeinrank.benchmark_performance_report.v1",
        "skeinrank.openrouter_live_pilot_report.v1",
        "proposal_quality",
        "agent_decision_diagnostics",
        "hard_negative_leakage@10",
        "generic_token_noise@10",
        "OpenRouter calls: false",
        "does not approve/apply",
    ]:
        assert fragment in combined


def test_benchmark_docs_markdown_links_resolve() -> None:
    for path in BENCHMARK_DOCS:
        content = _read(path)
        for match in MARKDOWN_LINK_RE.finditer(content):
            target = match.group(1).strip()
            if not target or target.startswith("#"):
                continue
            parsed = urlparse(target)
            if parsed.scheme or parsed.netloc:
                continue
            relative = unquote(parsed.path)
            if not relative:
                continue
            resolved = (path.parent / relative).resolve()
            assert resolved.exists(), f"{path} links to missing file: {target}"
