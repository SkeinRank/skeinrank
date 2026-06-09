from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

PRODUCT_EXAMPLE_READMES = (
    REPO_ROOT / "examples" / "platform_ops_demo" / "README.md",
    REPO_ROOT / "examples" / "enrichment-pause-resume" / "README.md",
    REPO_ROOT / "examples" / "benchmarks" / "platform_ops_v1" / "README.md",
    REPO_ROOT / "examples" / "runtime-routing-api" / "README.md",
    REPO_ROOT / "examples" / "mcp-agent-docs" / "README.md",
    REPO_ROOT
    / "examples"
    / "agents"
    / "openrouter_alias_scout"
    / "real_es_validation"
    / "README.md",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_example_readmes_are_product_facing() -> None:
    forbidden_patterns = (
        r"\b[Pp]atch\b",
        r"\b\d{2}[A-Z](?:\.\d+)?\b",
        r"\bdev[- ]?journal\b",
        r"\bdevelopment diary\b",
        r"\badds a\b",
        r"\badds an\b",
    )

    for path in PRODUCT_EXAMPLE_READMES:
        content = _read(path)
        for pattern in forbidden_patterns:
            assert re.search(pattern, content) is None, f"{path}: {pattern}"


def test_example_readmes_keep_real_commands_and_existing_surfaces() -> None:
    combined = "\n".join(_read(path) for path in PRODUCT_EXAMPLE_READMES)

    required_fragments = (
        "make demo-reset",
        "make demo-tour",
        "make benchmark-reset",
        "make benchmark-retrieval-eval",
        "make benchmark-smoke-generate",
        "make benchmark-performance-report",
        "/v1/governance/elasticsearch/jobs/123/pause",
        "/v1/governance/elasticsearch/jobs/123/resume",
        "POST /v1/text/canonicalize",
        "POST /v1/query/route-plan",
        "skeinrank_list_bindings",
        "skeinrank_submit_alias_proposal",
        "documents.jsonl",
        "expected_outcomes.jsonl",
    )

    for fragment in required_fragments:
        assert fragment in combined


def test_example_readmes_preserve_safety_boundaries() -> None:
    platform_demo = _read(REPO_ROOT / "examples" / "platform_ops_demo" / "README.md")
    mcp_docs = _read(REPO_ROOT / "examples" / "mcp-agent-docs" / "README.md")
    real_es = _read(
        REPO_ROOT
        / "examples"
        / "agents"
        / "openrouter_alias_scout"
        / "real_es_validation"
        / "README.md"
    )

    assert "operator-controlled search delivery" in platform_demo
    assert "proposal-first" in mcp_docs
    assert "should not directly publish snapshots" in real_es
