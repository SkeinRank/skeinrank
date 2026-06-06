from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

RUNBOOKS = [
    "docs/pilots/first-company-pilot-runbook.md",
    "docs/pilots/elasticsearch-pilot-integration.md",
    "docs/pilots/troubleshooting-bundle-export.md",
    "docs/pilots/support-bundle-production.md",
    "docs/deployment/docker-compose.md",
    "docs/deployment/production-compose.md",
    "docs/deployment/env-and-secrets.md",
    "docs/deployment/backup-restore.md",
    "docs/deployment/backup-restore-verified-scenario.md",
    "docs/deployment/upgrade-guide.md",
    "docs/deployment/blue-green-alias-swap-runbook.md",
    "docs/deployment/alerting-hooks-degraded-state-reports.md",
]

FORBIDDEN_IMPLEMENTATION_LOG_PATTERNS = [
    re.compile(r"\bpatch\b", re.IGNORECASE),
    re.compile(r"\badds\s+a\b", re.IGNORECASE),
    re.compile(r"\badded\s+a\b", re.IGNORECASE),
    re.compile(r"\b(?:45C|46A|46B|46C|49E|54A|54B|54C|56A|56B|61A|61B|61C)\b"),
]


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def test_pilot_and_production_runbooks_use_product_language() -> None:
    for path in RUNBOOKS:
        content = _read(path)
        for pattern in FORBIDDEN_IMPLEMENTATION_LOG_PATTERNS:
            assert not pattern.search(content), f"{path} still looks like a change log"


def test_runbook_links_still_point_to_existing_files() -> None:
    markdown_link = re.compile(r"\[[^\]]+\]\(([^)]+\.md)(?:#[^)]+)?\)")

    for path in RUNBOOKS:
        doc_path = REPO_ROOT / path
        for target in markdown_link.findall(_read(path)):
            if target.startswith(("http://", "https://", "mailto:")):
                continue
            target_path = (doc_path.parent / target).resolve()
            assert target_path.exists(), f"{path} links to missing file: {target}"


def test_pilot_runbooks_keep_safe_first_value_flow() -> None:
    first_pilot = _read("docs/pilots/first-company-pilot-runbook.md")
    elasticsearch_pilot = _read("docs/pilots/elasticsearch-pilot-integration.md")

    for fragment in [
        "dry-run binding",
        "OpenRouter calls: false",
        "proposal submission: false",
        "snapshot publishing: false",
        "Elasticsearch writes: false",
        "make pilot-run",
        "PILOT_CONFIG=/tmp/skeinrank-company-pilot.json",
    ]:
        assert fragment in first_pilot

    for fragment in [
        "make pilot-plan",
        "make pilot-preflight",
        "make pilot-seed",
        "make pilot-eval",
        "make pilot-report",
        "skeinrank.pilot.integration_report.v1",
        "No OpenRouter calls are made",
    ]:
        assert fragment in elasticsearch_pilot


def test_production_runbooks_keep_operator_safety_flow() -> None:
    production = _read("docs/deployment/production-compose.md")
    env = _read("docs/deployment/env-and-secrets.md")
    backup = _read("docs/deployment/backup-restore.md")
    blue_green = _read("docs/deployment/blue-green-alias-swap-runbook.md")
    alerting = _read("docs/deployment/alerting-hooks-degraded-state-reports.md")

    for fragment in [
        "make prod-env-check",
        "make prod-config",
        "make prod-up",
        "make prod-smoke",
        "make prod-upgrade-check",
        "make prod-upgrade",
        "--profile observability",
    ]:
        assert fragment in production

    assert "skeinrank_governance_api.env_validation validate" in env
    assert "python -m skeinrank_governance_api.backup_restore export" in backup
    assert "make backup-restore-drill-run" in backup
    assert "reindex_alias_swap" in blue_green
    assert (
        "POST /v1/governance/elasticsearch/bindings/{binding_id}/jobs/preflight"
        in blue_green
    )
    assert "GET /v1/ops/alerts/report" in alerting
