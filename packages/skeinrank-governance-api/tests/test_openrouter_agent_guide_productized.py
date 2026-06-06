from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

OPENROUTER_DOCS = [
    REPO_ROOT / "docs" / "guides" / "openrouter-agent.md",
    REPO_ROOT / "docs" / "deployment" / "openrouter-alias-scout.md",
    REPO_ROOT / "docs" / "deployment" / "openrouter-agent-full-demo.md",
    REPO_ROOT / "examples" / "agents" / "openrouter_alias_scout" / "README.md",
    REPO_ROOT / "examples" / "agents" / "openrouter_alias_scout" / "env.example",
]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_openrouter_agent_docs_are_productized() -> None:
    forbidden = (
        "Patch",
        "patch-era",
        "later patches",
        "dev diary",
        "development diary",
    )
    for path in OPENROUTER_DOCS:
        content = _read(path)
        for fragment in forbidden:
            assert fragment not in content, path


def test_openrouter_agent_guide_keeps_real_operator_surfaces() -> None:
    guide = _read(REPO_ROOT / "docs" / "guides" / "openrouter-agent.md")

    for fragment in (
        "LLM / agent -> proposal -> validation -> review / policy -> snapshot -> runtime",
        "GET  /v1/tools/bindings",
        "POST /v1/tools/explain-query",
        "POST /v1/tools/validate-alias",
        "POST /v1/tools/suggest-alias",
        "--print-tool-schemas",
        "--discover-candidates",
        "--sample-evidence",
        "--run-demo-report",
        "--print-llm-review-plan",
        "--print-security-profile",
        "--print-budget-cache-plan",
        "--run-evaluation-report",
        "--print-deployment-recipe",
        "--validate-ready-proposals",
        "--print-dictionary-quickstart-plan",
        "--print-runtime-api-smoke-plan",
        "--print-docker-demo-plan",
        "--print-openrouter-live-pilot-plan",
    ):
        assert fragment in guide


def test_openrouter_docs_markdown_links_point_to_existing_files() -> None:
    markdown_link = re.compile(r"\[[^\]]+\]\((?!https?://|#)([^)]+)\)")
    for path in OPENROUTER_DOCS[:4]:
        content = _read(path)
        for match in markdown_link.finditer(content):
            target = match.group(1).split("#", 1)[0]
            if not target:
                continue
            resolved = (path.parent / target).resolve()
            assert resolved.exists(), f"{path} links to missing {target}"
