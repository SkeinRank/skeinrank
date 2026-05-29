from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
ROOT_README = REPO_ROOT / "README.md"
DOCS_README = REPO_ROOT / "docs/README.md"
PRODUCT_POSITIONING = REPO_ROOT / "docs/product-positioning.md"
CONTRIBUTING = REPO_ROOT / "CONTRIBUTING.md"
SECURITY = REPO_ROOT / "SECURITY.md"
CODE_OF_CONDUCT = REPO_ROOT / "CODE_OF_CONDUCT.md"
PR_TEMPLATE = REPO_ROOT / ".github/PULL_REQUEST_TEMPLATE.md"
BUG_TEMPLATE = REPO_ROOT / ".github/ISSUE_TEMPLATE/bug_report.md"
FEATURE_TEMPLATE = REPO_ROOT / ".github/ISSUE_TEMPLATE/feature_request.md"
ISSUE_CONFIG = REPO_ROOT / ".github/ISSUE_TEMPLATE/config.yml"
CI_WORKFLOW = REPO_ROOT / ".github/workflows/ci.yml"


def test_readme_positions_skeinrank_as_control_plane_not_crud_console() -> None:
    readme = ROOT_README.read_text(encoding="utf-8")

    assert "Terminology Control Plane" in readme
    assert "enterprise search, RAG, and AI-agent workflows" in readme
    assert "Control Plane" in readme
    assert "Data Plane" in readme
    assert "Playground -> debug query canonicalization" in readme
    assert "AI Inbox -> review evidence-backed agent proposals" in readme
    assert "Schema & Snapshots -> inspect profiles" in readme
    assert "not a direct production CRUD console" in readme
    assert "proposal, validation, risk policy, review, snapshots" in readme
    assert "docs/product-positioning.md" in readme
    assert "make demo-tour" in readme
    assert "make demo-tour-smoke" in readme


def test_product_positioning_doc_covers_personas_demo_and_safety() -> None:
    doc = PRODUCT_POSITIONING.read_text(encoding="utf-8")

    assert "SkeinRank product positioning" in doc
    assert "Terminology Control Plane" in doc
    assert "Who it is for" in doc
    assert "Search / platform engineers" in doc
    assert "ML / RAG engineers" in doc
    assert "Knowledge managers / reviewers" in doc
    assert "Control Plane" in doc
    assert "Data Plane / Runtime" in doc
    assert "Playground" in doc
    assert "AI Inbox" in doc
    assert "Schema & Snapshots" in doc
    assert "What SkeinRank is not" in doc
    assert "not trying to replace Elasticsearch" in doc
    assert "make demo-tour" in doc
    assert "make demo-tour-smoke" in doc
    assert "platform_ops_demo_tour_report.json" in doc
    assert "Public beta readiness checklist" in doc
    assert "CONTRIBUTING.md" in doc
    assert "SECURITY.md" in doc
    assert "CODE_OF_CONDUCT.md" in doc


def test_docs_index_links_product_positioning_and_demo_guides() -> None:
    docs = DOCS_README.read_text(encoding="utf-8")

    assert "product-positioning.md" in docs
    assert "seeded-demo-walkthrough.md" in docs
    assert "demo-product-tour.md" in docs
    assert "make demo-tour" in docs
    assert "platform_ops_demo_tour_report.json" in docs


def test_github_community_files_exist_and_are_skeinrank_specific() -> None:
    for path in (
        CONTRIBUTING,
        SECURITY,
        CODE_OF_CONDUCT,
        PR_TEMPLATE,
        BUG_TEMPLATE,
        FEATURE_TEMPLATE,
        ISSUE_CONFIG,
        CI_WORKFLOW,
    ):
        assert path.exists(), path

    contributing = CONTRIBUTING.read_text(encoding="utf-8")
    security = SECURITY.read_text(encoding="utf-8")
    conduct = CODE_OF_CONDUCT.read_text(encoding="utf-8")
    pr_template = PR_TEMPLATE.read_text(encoding="utf-8")
    bug_template = BUG_TEMPLATE.read_text(encoding="utf-8")
    feature_template = FEATURE_TEMPLATE.read_text(encoding="utf-8")

    assert (
        "proposal -> validation -> risk policy -> human review -> snapshot"
        in contributing
    )
    assert "make demo-tour" in contributing
    assert "npm run typecheck" in contributing
    assert "scoped agent credentials" in security
    assert "support bundle redaction" in security
    assert "SkeinRank aims to be" in conduct
    assert "No new direct production mutation path" in pr_template
    assert "Legacy UI write tools remain locked by default" in pr_template
    assert "Redact secrets" in bug_template
    assert "GitOps / Terminology-as-Code" in feature_template
