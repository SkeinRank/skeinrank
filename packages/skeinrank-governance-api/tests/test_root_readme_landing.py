from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
ROOT_README = REPO_ROOT / "README.md"
ARCHITECTURE_IMAGE = (
    REPO_ROOT
    / "docs"
    / "assets"
    / "architecture"
    / "skeinrank-sidecar-architecture.png"
)


def test_root_readme_has_fast_pain_hook_and_sidecar_positioning() -> None:
    readme = ROOT_README.read_text(encoding="utf-8")
    first_screen = readme[:3000]

    assert "Your RAG is not failing because retrieval is hard" in first_screen
    assert "company's language is a mess" in first_screen
    assert "Terminology Control Plane" in first_screen
    assert "binding-aware runtime context" in first_screen
    assert "docs/assets/architecture/skeinrank-sidecar-architecture.png" in first_screen
    assert "Drop SkeinRank into your stack as a terminology sidecar" in first_screen


def test_root_readme_keeps_product_model_without_stale_dashboard_preview() -> None:
    readme = ROOT_README.read_text(encoding="utf-8")

    assert "## The problem" in readme
    assert "## What SkeinRank does" in readme
    assert "## Why a control plane, not a synonym file" in readme
    assert "not a direct production CRUD console" in readme
    assert (
        "proposal -> validation -> risk policy -> review -> snapshot -> rollout"
        in readme
    )
    assert "Binding-aware runtime" in readme
    assert "AI Inbox -> review evidence-backed agent proposals" in readme
    assert "## See it in 30 seconds" in readme
    assert "TODO" not in readme
    assert "Patch 63" not in readme
    assert "dashboard-runtime-control-center-dark.png" not in readme


def test_root_readme_architecture_asset_exists() -> None:
    assert ARCHITECTURE_IMAGE.exists()
    assert ARCHITECTURE_IMAGE.stat().st_size > 100_000


def test_root_readme_keeps_agent_entry_points_without_legacy_patch_markers() -> None:
    readme = ROOT_README.read_text(encoding="utf-8")

    assert "examples/agents/openrouter_alias_scout" in readme
    assert "docs/guides/openrouter-agent.md" in readme
    assert "Documentation discoverability compatibility index" not in readme
    assert "Patch 40G" not in readme
    assert "Patch 57A" not in readme
    assert "--print-tool-schemas" not in readme
    assert "--discover-candidates" not in readme
