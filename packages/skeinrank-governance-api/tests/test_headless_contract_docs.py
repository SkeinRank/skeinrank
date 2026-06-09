from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def test_headless_runtime_contract_docs_are_linked() -> None:
    docs_readme = _read("docs/README.md")
    overview = _read("docs/overview.md")
    root_readme = _read("README.md")

    assert "Headless runtime" in root_readme
    assert "docs/deployment/headless-quickstart.md" in root_readme

    assert "concepts/headless-runtime-contracts.md" in docs_readme
    assert "adr/0001-headless-runtime-contracts.md" in docs_readme
    assert "Headless runtime contracts" in overview


def test_headless_runtime_contract_map_defines_safe_boundaries() -> None:
    concept = _read("docs/concepts/headless-runtime-contracts.md")
    adr = _read("docs/adr/0001-headless-runtime-contracts.md")

    contract_terms = (
        "Profile",
        "Binding",
        "Snapshot",
        "Artifact",
        "Proposal",
        "Runtime",
    )
    for term in contract_terms:
        assert term in concept
        assert term in adr

    expected_fragments = (
        "PostgreSQL is the source of truth for changing state",
        "A runtime artifact is the immutable read model",
        "Agents are proposal sources, not sources of truth",
        "agent output -> proposal -> validation -> review/policy -> snapshot -> runtime",
        "The UI should remain thin and audit-oriented",
    )
    for fragment in expected_fragments:
        assert fragment in concept or fragment in adr


def test_headless_docs_preserve_existing_runtime_surfaces() -> None:
    concept = _read("docs/concepts/headless-runtime-contracts.md")
    adr = _read("docs/adr/0001-headless-runtime-contracts.md")
    combined = f"{concept}\n{adr}"

    for route in (
        "/v1/console/dictionary/*",
        "/v1/text/canonicalize",
        "/v1/query/plan",
        "/v1/search",
        "/v1/search/multi",
        "/v1/snapshots/summary",
        "/readyz",
        "/metrics",
    ):
        assert route in combined

    assert "binding_id" in combined
    assert "profile_name" in combined
