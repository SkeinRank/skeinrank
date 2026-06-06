from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

RUNTIME_DOCS = (
    REPO_ROOT / "docs" / "concepts" / "headless-runtime-contracts.md",
    REPO_ROOT / "docs" / "concepts" / "profiles-bindings-snapshots.md",
    REPO_ROOT / "docs" / "adr" / "0001-headless-runtime-contracts.md",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _markdown_links(content: str) -> list[str]:
    pattern = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
    return [match.group(1) for match in pattern.finditer(content)]


def test_runtime_concepts_are_product_documentation() -> None:
    forbidden_patterns = (
        r"\b[Pp]atch\b",
        r"\bfuture patches\b",
        r"\bevery few patches\b",
        r"\b\d{2}[A-Z](?:\.\d+)?\b",
        r"\badds a\b",
        r"\badds an\b",
        r"\bintroduced\b",
    )

    for path in RUNTIME_DOCS:
        content = _read(path)
        for pattern in forbidden_patterns:
            assert re.search(pattern, content) is None, f"{path}: {pattern}"


def test_runtime_concepts_preserve_public_contracts() -> None:
    combined = "\n".join(_read(path) for path in RUNTIME_DOCS)

    required_fragments = (
        "Profile   = terminology meaning and governance scope",
        "Binding   = production runtime search context",
        "Snapshot  = immutable terminology version safe for runtime",
        "A runtime artifact is the immutable read model",
        "Agents are proposal sources, not sources of truth",
        "agent output -> proposal -> validation -> review/policy -> snapshot -> runtime",
        "The UI should remain thin and audit-oriented",
        "/v1/console/dictionary/*",
        "/v1/headless/dictionaries/*",
        "/v1/text/canonicalize",
        "/v1/query/plan",
        "/v1/query/route-plan",
        "/v1/search",
        "/v1/search/multi",
        "/v1/snapshots/summary",
        "/readyz",
        "/metrics",
        "RuntimeSnapshotArtifactCache",
        "skeinrank-migrate snapshot-inspect",
        "skeinrank-mcp --print-tool-manifest",
        "skeinrank-mcp --print-env-template",
        "skeinrank-mcp --smoke-test",
        "skeinrank.mcp_smoke_report.v1",
        "policy_decisions",
        "candidate_binding_ids",
        "route_plan_only",
    )
    for fragment in required_fragments:
        assert fragment in combined


def test_runtime_concept_links_resolve() -> None:
    for path in RUNTIME_DOCS:
        content = _read(path)
        for link in _markdown_links(content):
            if link.startswith(("http://", "https://", "mailto:", "#")):
                continue
            target = link.split("#", 1)[0]
            if not target:
                continue
            assert (path.parent / target).resolve().exists(), f"{path}: {link}"
