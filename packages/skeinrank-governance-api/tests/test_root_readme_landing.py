from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
ROOT_README = REPO_ROOT / "README.md"
ARCHITECTURE_IMAGE = (
    REPO_ROOT
    / "docs"
    / "assets"
    / "architecture"
    / "skeinrank-sidecar-architecture.jpeg"
)


def test_root_readme_has_drift_hook_and_control_plane_positioning() -> None:
    readme = ROOT_README.read_text(encoding="utf-8")
    first_screen = readme[:3000]

    assert "Your RAG was great in January" in first_screen
    assert "nobody changed the model" in first_screen
    assert "Your team's language drifts" in first_screen
    assert "retrieval rots silently" in first_screen
    assert "open-source control plane" in first_screen
    assert "keeps your search vocabulary under control as it drifts" in first_screen


def test_root_readme_keeps_product_model_without_stale_dashboard_preview() -> None:
    readme = ROOT_README.read_text(encoding="utf-8")

    assert "## The problem nobody is measuring" in readme
    assert "## Try it in 60 seconds" in readme
    assert "## Why this can't just be a synonym file" in readme
    assert "## How the value compounds" in readme
    assert "## What's in the box" in readme
    assert '### "But our search tools already have AI now"' in readme
    assert "Production changes never touch the database directly" in readme
    assert "proposal → validation → risk policy → review → snapshot → rollout" in readme
    assert "Binding-aware runtime" in readme
    assert "AI Inbox" in readme
    assert "write-intent without write-access" in readme
    assert 'skeinrank.canonicalize("k8s pg timeout")' in readme
    assert "TODO" not in readme
    assert "Patch 63" not in readme
    assert "dashboard-runtime-control-center-dark.png" not in readme


def test_root_readme_architecture_asset_exists() -> None:
    assert ARCHITECTURE_IMAGE.exists()
    assert ARCHITECTURE_IMAGE.stat().st_size > 100_000


def test_root_readme_keeps_agent_entry_points_without_legacy_markers() -> None:
    readme = ROOT_README.read_text(encoding="utf-8")
    docs_index = (REPO_ROOT / "docs/README.md").read_text(encoding="utf-8")

    assert "MCP & agent integration" in readme
    assert "skeinrank_submit_alias_proposal" in readme
    assert "docs/deployment/mcp-integration-kit.md" in readme
    assert "guides/openrouter-agent.md" in docs_index
    assert "../examples/agents/openrouter_alias_scout" in docs_index
    assert "Documentation discoverability compatibility index" not in readme
    assert "Patch 40G" not in readme
    assert "Patch 57A" not in readme
    assert "--print-tool-schemas" not in readme
    assert "--discover-candidates" not in readme


def test_root_readme_documents_zero_friction_sdk_and_drift_demo() -> None:
    readme = ROOT_README.read_text(encoding="utf-8")

    assert "## Try it in 60 seconds" in readme
    assert "No Docker. No Elasticsearch. No config file." in readme
    assert "pip install skeinrank" in readme
    assert 'skeinrank.canonicalize("pg layout")' in readme
    assert "skeinrank drift-scan ./docs --profile platform_ops" in readme
    assert "Terminology drift report" in readme
    assert "docs/guides/terminology-drift-report.md" in readme
    assert "examples/drift-scan" in readme
    assert "release-cлompose" not in readme
    assert "docs/deployment/release-compose.md" in readme
    assert "<details>" in readme
    assert "Benchmarks, Docker/Kubernetes, docs map & repo layout" in readme
    assert "Patch" not in readme
    assert "TODO" not in readme


def test_root_readme_keeps_platform_preview_inside_details() -> None:
    readme = ROOT_README.read_text(encoding="utf-8")
    quickstart = readme.split("## Quickstart paths", 1)[1].split("## Community", 1)[0]

    assert "docs/deployment/docker-compose.md" in quickstart
    assert "<summary><strong>Run the full platform preview" in quickstart
    assert "docker compose -f docker-compose.dev.yml up --build -d" in quickstart
    assert "make demo-reset" in quickstart
    assert "make demo-tour" in quickstart
    assert "make demo-tour-smoke" in quickstart
    assert quickstart.index(
        "<summary><strong>Run the full platform preview"
    ) < quickstart.index("docker compose -f docker-compose.dev.yml up --build -d")


def test_root_readme_explains_language_drift_problem() -> None:
    readme = ROOT_README.read_text(encoding="utf-8")
    problem = readme.split("## The problem nobody is measuring", 1)[1].split(
        "## Try it in 60 seconds", 1
    )[0]

    assert 'January:  on-call types "checkout timeout"' in problem
    assert 'the feature is now "payments-core"' in problem
    assert 'on-call still types "the checkout thing"' in problem
    assert "retrieval that is a few percent worse every month" in problem
    assert "the bot got dumb" in problem
    assert (
        "your vocabulary is the one input to retrieval that changes constantly"
        in problem
    )


def test_root_readme_answers_platform_ai_objection() -> None:
    readme = ROOT_README.read_text(encoding="utf-8")
    section = readme.split('### "But our search tools already have AI now"', 1)[
        1
    ].split("## Core model", 1)[0]

    assert "inside their own walls" in section
    assert "Jira's AI searches Jira" in section
    assert "Slack's AI searches Slack" in section
    assert "no reusable layer" in section
    assert "data **you own**" in section


def test_root_readme_community_section_is_public_facing() -> None:
    readme = ROOT_README.read_text(encoding="utf-8")
    community = readme.split("## Community", 1)[1].split("## Project status", 1)[0]

    assert "pinned discussion drafts" not in community
    assert "GitHub CLI sync commands" not in community
    assert "Issues" in community
    assert "Discussions" in community
    assert "public-beta talk" in community


def test_root_readme_local_markdown_links_exist() -> None:
    readme = ROOT_README.read_text(encoding="utf-8")

    local_links = []
    for link in re.findall(r"\]\(([^)]+)\)", readme):
        if link.startswith(("http://", "https://", "mailto:", "#")):
            continue
        target = link.split("#", 1)[0]
        if target:
            local_links.append(target)

    assert local_links
    missing = [link for link in local_links if not (REPO_ROOT / link).exists()]
    assert missing == []
