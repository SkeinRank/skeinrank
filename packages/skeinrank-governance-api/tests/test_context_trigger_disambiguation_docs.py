from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_context_trigger_docs_reference_existing_runtime_surfaces() -> None:
    guide = _read("docs/guides/context-trigger-disambiguation.md")

    assert "context_triggers" in guide
    assert "POST /v1/text/canonicalize" in guide
    assert "POST /v1/query/plan" in guide
    assert "POST /v1/search" in guide
    assert "POST /v1/search/multi" in guide
    assert "alias_context_trigger" in guide
    assert "No new endpoint is introduced" in guide


def test_context_trigger_examples_are_spec_v1_and_secret_free() -> None:
    dictionary = _read("examples/runtime-routing-api/context-trigger-dictionary.yaml")
    request = _read(
        "examples/runtime-routing-api/context-trigger-canonicalize.request.json"
    )

    assert "schema_version: skeinrank.dictionary.v1" in dictionary
    assert "context_triggers:" in dictionary
    assert "timeout" in dictionary
    assert "replica" in dictionary
    assert "migration" in dictionary
    assert '"binding_name"' in request
    assert "SKEINRANK_GOVERNANCE_API_TOKEN" not in dictionary + request
    assert "sk_" not in dictionary + request


def test_docs_index_links_context_trigger_guide() -> None:
    docs_index = _read("docs/README.md")
    root_readme = _read("README.md")
    api_readme = _read("packages/skeinrank-governance-api/README.md")

    assert "guides/context-trigger-disambiguation.md" in docs_index
    assert "context-trigger-disambiguation.md" in root_readme
    assert "context-trigger-disambiguation.md" in api_readme
