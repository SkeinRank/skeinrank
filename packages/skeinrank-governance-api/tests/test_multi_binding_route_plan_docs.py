from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DOCS = ROOT / "docs"
EXAMPLES = ROOT / "examples" / "runtime-routing-api"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_route_plan_docs_describe_read_only_multi_binding_api() -> None:
    guide = _read(DOCS / "guides" / "runtime-routing-api.md")
    api_docs = _read(DOCS / "api" / "governance-api.md")

    for content in (guide, api_docs):
        assert "POST /v1/query/route-plan" in content
        assert "route_plan_only" in content
        assert "candidate_binding_ids" in content
        assert "selected_bindings" in content
        assert "rejected_bindings" in content
        assert "failed_bindings" in content
        assert "/v1/search/router" not in content

    assert "does not execute Elasticsearch search" in guide
    assert "read-only" in guide.lower()


def test_route_plan_example_is_safe_json_payload() -> None:
    path = EXAMPLES / "route-plan.request.json"
    payload = json.loads(_read(path))

    assert payload["candidate_binding_ids"] == [1, 2, 3]
    assert payload["query"] == "k8s pg timeout"
    assert payload["max_selected_bindings"] == 2
    assert payload["include_rejected"] is True
    assert "skn_" not in _read(path)


def test_route_plan_docs_are_discoverable() -> None:
    root_readme = _read(ROOT / "README.md")
    docs_index = _read(DOCS / "README.md")
    package_readme = _read(ROOT / "packages" / "skeinrank-governance-api" / "README.md")

    for content in (root_readme, docs_index, package_readme):
        assert "route-plan" in content
        assert (
            "multi-binding" in content.lower()
            or "selected/rejected bindings" in content.lower()
        )

    assert "Patch 63" not in root_readme
