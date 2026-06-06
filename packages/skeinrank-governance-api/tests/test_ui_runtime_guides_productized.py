from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

PRODUCTIZED_GUIDES = [
    REPO_ROOT / "docs/guides/context-trigger-disambiguation.md",
    REPO_ROOT / "docs/guides/control-plane-navigation-slim-down.md",
    REPO_ROOT / "docs/guides/demo-product-tour.md",
    REPO_ROOT / "docs/guides/dictionary-cli-planning.md",
    REPO_ROOT / "docs/guides/elasticsearch-enrichment.md",
    REPO_ROOT / "docs/guides/enrichment-beta-hardening.md",
    REPO_ROOT / "docs/guides/enrichment-pause-resume-checkpointing.md",
    REPO_ROOT / "docs/guides/playground-snapshot-compare-ui.md",
    REPO_ROOT / "docs/guides/proposal-inbox-ui.md",
    REPO_ROOT / "docs/guides/read-only-legacy-admin-cockpit.md",
    REPO_ROOT / "docs/guides/runtime-routing-api.md",
    REPO_ROOT / "docs/guides/schema-snapshots-tree-ui.md",
    REPO_ROOT / "docs/guides/seeded-demo-walkthrough.md",
    REPO_ROOT / "docs/guides/terminology-as-code.md",
    REPO_ROOT / "docs/guides/ui-polish-empty-states-degraded-banners.md",
]

FEATURE_ID_PATTERN = re.compile(r"\b(?:58|59|60|61|63)[A-Z](?:\.\d+)?\b")
MARKDOWN_LINK_PATTERN = re.compile(r"\[[^\]]+\]\((?!https?://|#)([^)]+)\)")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_ui_and_runtime_guides_are_productized() -> None:
    forbidden_fragments = (
        "Patch",
        "patch",
        "dev diary",
        "development diary",
        "future patches",
        "later patches",
    )

    for path in PRODUCTIZED_GUIDES:
        content = _read(path)
        for fragment in forbidden_fragments:
            assert fragment not in content, path
        assert not FEATURE_ID_PATTERN.search(content), path


def test_ui_guides_keep_existing_safe_surfaces() -> None:
    guide_fragments = {
        "playground-snapshot-compare-ui.md": (
            "POST /v1/query/plan",
            "No new backend endpoint",
            "No runtime mutation",
        ),
        "proposal-inbox-ui.md": (
            "GET  /v1/governance/profiles",
            "POST /v1/governance/profiles/{profile_name}/suggestions/{suggestion_id}/approve",
            "skeinrank.apply_policy.v1",
        ),
        "schema-snapshots-tree-ui.md": (
            "GET /v1/snapshots/summary",
            "GET /v1/governance/elasticsearch/bindings",
            "No term, alias, stop-list, binding, or snapshot mutation is added",
        ),
        "read-only-legacy-admin-cockpit.md": (
            "VITE_SKEINRANK_ENABLE_LEGACY_WRITE_TOOLS=true npm run dev",
            "Backend RBAC remains authoritative",
        ),
        "demo-product-tour.md": (
            "make demo-tour",
            "make demo-tour-smoke",
            "examples/platform_ops_demo/reports/platform_ops_demo_tour_report.json",
        ),
        "seeded-demo-walkthrough.md": (
            "make demo-reset",
            "platform_ops_demo_walkthrough.json",
            "k8s pg timeout during phoenix rollout",
        ),
    }

    for filename, fragments in guide_fragments.items():
        content = _read(REPO_ROOT / "docs/guides" / filename)
        for fragment in fragments:
            assert fragment in content


def test_runtime_guides_keep_existing_contract_surfaces() -> None:
    guide_fragments = {
        "runtime-routing-api.md": (
            "POST /v1/text/canonicalize",
            "POST /v1/query/plan",
            "POST /v1/query/route-plan",
            "POST /v1/search",
            "route_plan_only",
            "candidate_binding_ids",
            "selected_bindings",
            "rejected_bindings",
            "failed_bindings",
            "profile_preview",
            "binding_runtime",
            "binding_latest_profile",
        ),
        "context-trigger-disambiguation.md": (
            "context_triggers",
            "alias_context_trigger",
            "POST /v1/text/canonicalize",
            "POST /v1/search/multi",
            "No new endpoint is introduced",
        ),
        "terminology-as-code.md": (
            "YAML outside, JSON inside.",
            "skeinrank.dictionary.v1",
            "skeinrank.runtime_snapshot_artifact.v1",
            "skeinrank-migrate snapshot-export",
            "skeinrank-migrate snapshot-eval",
        ),
        "dictionary-cli-planning.md": (
            "skeinrank-migrate lint FILE",
            "skeinrank-migrate plan FILE",
            "skeinrank.dictionary_apply_plan.v1",
            "safe_to_apply",
        ),
        "enrichment-beta-hardening.md": (
            "POST /v1/governance/elasticsearch/bindings/{binding_id}/jobs/preflight",
            "blocking_issues",
            "recommended_request",
            "reindex_alias_swap",
        ),
        "enrichment-pause-resume-checkpointing.md": (
            "POST /v1/governance/elasticsearch/jobs/{job_id}/pause",
            "POST /v1/governance/elasticsearch/jobs/{job_id}/resume",
            "result_json.chunked_enrichment.checkpoint",
        ),
        "elasticsearch-enrichment.md": (
            "POST /v1/governance/elasticsearch/bindings/{binding_id}/dry-run",
            "POST /v1/governance/elasticsearch/bindings/{binding_id}/evidence",
            "POST /v1/governance/elasticsearch/jobs/{job_id}/rollback",
        ),
    }

    for filename, fragments in guide_fragments.items():
        content = _read(REPO_ROOT / "docs/guides" / filename)
        for fragment in fragments:
            assert fragment in content


def test_productized_ui_runtime_guide_links_point_to_existing_files() -> None:
    for path in PRODUCTIZED_GUIDES:
        content = _read(path)
        for match in MARKDOWN_LINK_PATTERN.finditer(content):
            target = match.group(1).split("#", 1)[0]
            if not target:
                continue
            resolved = (path.parent / target).resolve()
            assert resolved.exists(), f"{path} links to missing {target}"
