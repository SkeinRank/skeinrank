from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DOCS = ROOT / "docs"
EXAMPLES = ROOT / "examples" / "runtime-routing-api"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_runtime_routing_guide_documents_existing_runtime_endpoints() -> None:
    guide = _read(DOCS / "guides" / "runtime-routing-api.md")

    assert "POST /v1/text/canonicalize" in guide
    assert "POST /v1/query/plan" in guide
    assert "POST /v1/query/route-plan" in guide
    assert "POST /v1/search" in guide
    assert "/v1/search/router" not in guide
    assert "binding_id" in guide
    assert "binding_name" in guide
    assert "application_scope" in guide
    assert "runtime_context" in guide
    assert "profile_preview" in guide
    assert "binding_runtime" in guide
    assert "binding_latest_profile" in guide


def test_runtime_routing_examples_are_valid_json_payloads() -> None:
    expected_files = {
        "canonicalize-binding-id.request.json",
        "canonicalize-binding-name.request.json",
        "query-plan-binding-name.request.json",
        "route-plan.request.json",
        "search-binding-id.request.json",
    }
    assert expected_files <= {path.name for path in EXAMPLES.glob("*.json")}

    for path in EXAMPLES.glob("*.json"):
        payload = json.loads(_read(path))
        assert isinstance(payload, dict)
        assert "skn_" not in _read(path)
        if "canonicalize" in path.name:
            assert "text" in payload
        if (
            "query-plan" in path.name
            or "search" in path.name
            or "route-plan" in path.name
        ):
            assert "query" in payload
        assert (
            "binding_id" in payload
            or "binding_name" in payload
            or "candidate_binding_ids" in payload
        )


def test_runtime_routing_docs_are_discoverable() -> None:
    docs_index = _read(DOCS / "README.md")
    root_readme = _read(ROOT / "README.md")
    api_docs = _read(DOCS / "api" / "governance-api.md")
    package_readme = _read(ROOT / "packages" / "skeinrank-governance-api" / "README.md")

    for content in (root_readme, api_docs):
        assert "POST /v1/text/canonicalize" in content
        assert "POST /v1/query/route-plan" in content
        assert "binding-aware" in content.lower()

    assert "binding-aware" in package_readme.lower()
    assert "runtime-routing-api.md" in package_readme
    assert "guides/runtime-routing-api.md" in docs_index
    assert "runtime-routing-api.md" in root_readme
    assert "examples/runtime-routing-api" in root_readme
    assert "Patch 63" not in root_readme
