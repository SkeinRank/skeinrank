from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "examples/platform_ops_demo/demo_product_tour.py"
SEED_SCRIPT_PATH = REPO_ROOT / "examples/platform_ops_demo/seed_platform_demo.py"
WALKTHROUGH_PATH = (
    REPO_ROOT / "examples/platform_ops_demo/platform_ops_demo_walkthrough.json"
)
MAKEFILE_PATH = REPO_ROOT / "Makefile"
ROOT_README_PATH = REPO_ROOT / "README.md"
DOCS_README_PATH = REPO_ROOT / "docs/README.md"
DEMO_README_PATH = REPO_ROOT / "examples/platform_ops_demo/README.md"
GUIDE_PATH = REPO_ROOT / "docs/guides/demo-product-tour.md"


def _load_tour_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("platform_ops_demo_tour", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_demo_product_tour_assets_exist_and_make_targets_are_wired() -> None:
    assert SCRIPT_PATH.exists()
    assert SEED_SCRIPT_PATH.exists()
    assert WALKTHROUGH_PATH.exists()
    assert GUIDE_PATH.exists()

    makefile = MAKEFILE_PATH.read_text(encoding="utf-8")
    assert "DEMO_TOUR := examples/platform_ops_demo/demo_product_tour.py" in makefile
    for target in (
        "demo-tour-plan:",
        "demo-tour-smoke:",
        "demo-tour:",
        "demo-tour-show:",
        "demo-tour-clean:",
    ):
        assert target in makefile
    assert (
        "DEMO_TOUR_REPORT ?= examples/platform_ops_demo/reports/platform_ops_demo_tour_report.json"
        in makefile
    )


def test_demo_product_tour_plan_is_offline_and_matches_walkthrough() -> None:
    module = _load_tour_module()
    config = module.parse_args(["--plan"])
    plan = module.build_plan(config)

    assert plan["schema_version"] == "skeinrank.demo_product_tour_report.v1"
    assert plan["status"] == "planned"
    assert plan["demo"]["profile"] == "platform_ops"
    assert plan["demo"]["binding_name"] == "Production knowledge base"
    assert plan["demo"]["query"] == "k8s pg timeout during phoenix rollout"
    assert plan["walkthrough"]["tabs"] == [
        "Playground",
        "AI Inbox",
        "Schema & Snapshots",
    ]
    assert plan["commands"]["one_command_tour"] == "make demo-tour"
    assert plan["safety"]["network_calls"] is False
    assert plan["safety"]["database_mutation_enabled"] is False
    assert plan["safety"]["elasticsearch_mutation_enabled"] is False
    assert plan["safety"]["legacy_write_tools_enabled_by_default"] is False


def test_demo_product_tour_pending_proposal_summary_is_stable() -> None:
    module = _load_tour_module()
    summary = module.find_pending_demo_proposals(
        [
            {
                "id": 1,
                "alias_value": "edge",
                "canonical_value": "api-gateway",
                "status": "pending",
                "confidence": 0.91,
                "source": "discovery",
                "proposal_source_type": "agent",
                "proposal_source_name": "platform-demo-alias-scout",
            },
            {
                "id": 2,
                "alias_value": "EKS",
                "canonical_value": "kubernetes",
                "status": "approved",
            },
            {
                "id": 3,
                "alias_value": "prod",
                "canonical_value": "production environment",
                "status": "pending",
            },
        ]
    )

    assert summary["pending_aliases"] == ["edge", "prod"]
    assert summary["missing_aliases"] == ["EKS", "OpenSearch"]
    assert [row["alias_value"] for row in summary["rows"]] == ["edge", "prod"]


def test_demo_product_tour_safe_url_checks_reject_non_local_ui() -> None:
    module = _load_tour_module()
    config = module.parse_args(
        [
            "--api-url",
            "http://127.0.0.1:8010",
            "--elasticsearch-url",
            "http://127.0.0.1:19200",
            "--ui-url",
            "https://example.invalid",
        ]
    )

    try:
        module.check_safe_urls(config)
    except module.DemoSeedError as exc:
        assert "Refusing to check non-local UI URL" in str(exc)
    else:  # pragma: no cover - defensive assertion for a safety check
        raise AssertionError("non-local UI URL should be rejected by default")


def test_demo_product_tour_report_writer_uses_stable_schema(tmp_path: Path) -> None:
    module = _load_tour_module()
    path = tmp_path / "tour-report.json"
    report = {
        "schema_version": module.SCHEMA_VERSION,
        "status": "passed",
        "summary": {"checks_total": 1},
    }

    module.write_report(path, report)
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded == report


def test_demo_product_tour_docs_are_discoverable() -> None:
    root_readme = ROOT_README_PATH.read_text(encoding="utf-8")
    docs_readme = DOCS_README_PATH.read_text(encoding="utf-8")
    demo_readme = DEMO_README_PATH.read_text(encoding="utf-8")
    guide = GUIDE_PATH.read_text(encoding="utf-8")

    for content in (root_readme, docs_readme, demo_readme, guide):
        assert "make demo-tour" in content
        assert "make demo-tour-smoke" in content
        assert "platform_ops_demo_tour_report.json" in content

    assert "demo-product-tour.md" in docs_readme
    assert "demo_product_tour.py" in demo_readme
