from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def _json(path: str) -> object:
    return json.loads(_read(path))


def test_coverage_framework_docs_are_linked() -> None:
    root_readme = _read("README.md")
    docs_readme = _read("docs/README.md")
    api_docs = _read("docs/api/governance-api.md")
    headless_docs = _read("docs/concepts/headless-runtime-contracts.md")

    discoverable_links = (
        "concepts/coverage-framework.md",
        "guides/coverage-framework.md",
    )
    for path in discoverable_links:
        assert path in docs_readme

    assert (REPO_ROOT / "examples/coverage-framework").exists()

    expected_paths = (
        "docs/concepts/coverage-framework.md",
        "docs/guides/coverage-framework.md",
        "examples/coverage-framework",
    )
    for path in expected_paths:
        assert (
            path in root_readme
            or path in api_docs
            or path in headless_docs
            or (REPO_ROOT / path).exists()
        )


def test_coverage_framework_concept_defines_runtime_boundaries() -> None:
    concept = _read("docs/concepts/coverage-framework.md")

    expected_fragments = (
        "more aliases are not automatically better coverage",
        "slot",
        "tag",
        "candidate",
        "BindingPolicy",
        "snapshot",
        "discover -> validate -> review -> snapshot -> bind -> serve -> evaluate",
        "Ambiguous aliases are governance records",
        "policy_decisions",
        "Safe default",
    )
    for fragment in expected_fragments:
        assert fragment in concept


def test_coverage_framework_guide_references_existing_routes() -> None:
    guide = _read("docs/guides/coverage-framework.md")

    for route in (
        "/v1/headless/dictionaries/apply",
        "/v1/governance/conflicts",
        "/v1/governance/profiles/coverage_ops/ambiguous-aliases",
        "/v1/governance/elasticsearch/bindings/1/policy",
        "/v1/query/plan",
    ):
        assert route in guide

    for file_path in (
        "examples/coverage-framework/coverage_dictionary.example.json",
        "examples/coverage-framework/ambiguous_alias_pg.example.json",
        "examples/coverage-framework/binding_policy_infra.example.json",
        "examples/coverage-framework/evaluation_queries.jsonl",
    ):
        assert file_path in guide


def test_coverage_framework_json_examples_are_valid() -> None:
    dictionary = _json("examples/coverage-framework/coverage_dictionary.example.json")
    ambiguous = _json("examples/coverage-framework/ambiguous_alias_pg.example.json")
    infra_policy = _json(
        "examples/coverage-framework/binding_policy_infra.example.json"
    )
    docs_policy = _json("examples/coverage-framework/binding_policy_docs.example.json")

    assert dictionary["schema_version"] == "skeinrank.dictionary.v1"
    assert dictionary["profile_name"] == "coverage_ops"
    assert any("tags" in term for term in dictionary["terms"])

    assert ambiguous["surface_value"] == "pg"
    assert {item["canonical_value"] for item in ambiguous["candidates"]} == {
        "postgresql",
        "page",
    }

    assert infra_policy["context_rules"][0]["prefer"] == "postgresql"
    assert "document_component" in infra_policy["deny_slots"]
    assert docs_policy["context_rules"][0]["prefer"] == "page"
    assert "database" in docs_policy["deny_slots"]


def test_coverage_framework_jsonl_queries_are_valid() -> None:
    path = REPO_ROOT / "examples/coverage-framework/evaluation_queries.jsonl"
    rows = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]

    assert len(rows) >= 3
    assert {"id", "query"}.issubset(rows[0])
    assert any("pg" in row["query"] for row in rows)
