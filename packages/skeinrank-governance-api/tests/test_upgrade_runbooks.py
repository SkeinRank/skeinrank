from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def test_production_upgrade_make_targets_are_declared() -> None:
    makefile = _read("Makefile")

    expected_targets = (
        "prod-preflight:",
        "prod-upgrade-check:",
        "prod-upgrade:",
        "prod-post-upgrade-smoke:",
    )
    for target in expected_targets:
        assert target in makefile

    expected_commands = (
        "deploy/docker/scripts/prod-upgrade-preflight.sh",
        "--no-backup --no-schema-check",
        "$(PROD_COMPOSE) up --build -d",
        "deploy/docker/scripts/prod-smoke-test.sh",
        "PROD_COMPOSE_FILE",
    )
    for command in expected_commands:
        assert command in makefile


def test_production_upgrade_preflight_script_is_safe_and_parseable() -> None:
    script_path = REPO_ROOT / "deploy/docker/scripts/prod-upgrade-preflight.sh"
    script = script_path.read_text(encoding="utf-8")

    expected_fragments = (
        "set -euo pipefail",
        "SKEINRANK_PROD_ENV_FILE",
        "SKEINRANK_PROD_COMPOSE_FILE",
        "skeinrank_governance_api.env_validation validate",
        "docker compose --env-file",
        "governance-backup-export",
        "governance-schema-check",
        "--strict-env",
        "--no-backup",
        "--no-schema-check",
        "SkeinRank production upgrade preflight passed.",
    )
    for fragment in expected_fragments:
        assert fragment in script

    subprocess.run(["bash", "-n", str(script_path)], check=True)


def test_production_smoke_script_builds_login_payload_safely() -> None:
    script_path = REPO_ROOT / "deploy/docker/scripts/prod-smoke-test.sh"
    script = script_path.read_text(encoding="utf-8")

    assert "LOGIN_PAYLOAD" in script
    assert "json.dumps" in script
    assert '--data-binary "${LOGIN_PAYLOAD}"' in script
    subprocess.run(["bash", "-n", str(script_path)], check=True)


def test_production_smoke_script_handles_unreachable_api_cleanly() -> None:
    script = _read("deploy/docker/scripts/prod-smoke-test.sh")

    expected_fragments = (
        "fetch_json()",
        "fetch_text()",
        "API endpoint ${path} is not reachable",
        "Check that the production Compose stack is running",
        "did not return valid JSON",
    )
    for fragment in expected_fragments:
        assert fragment in script

    assert "json.decoder.JSONDecodeError" not in script


def test_upgrade_docs_are_linked_from_primary_docs() -> None:
    docs_index = _read("docs/README.md")
    package_readme = _read("packages/skeinrank-governance-api/README.md")
    docker_readme = _read("deploy/docker/README.md")
    production_guide = _read("docs/deployment/production-compose.md")
    backup_guide = _read("docs/deployment/backup-restore.md")
    security_guide = _read("docs/deployment/security.md")

    for content in (
        docs_index,
        package_readme,
        docker_readme,
        production_guide,
        backup_guide,
        security_guide,
    ):
        assert (
            "docs/deployment/upgrade-guide.md" in content
            or "deployment/upgrade-guide.md" in content
        )
        assert (
            "docs/deployment/migration-safety.md" in content
            or "deployment/migration-safety.md" in content
        )

    assert "deployment/release-checklist.md" in docs_index
    assert "docs/deployment/release-checklist.md" in package_readme


def test_upgrade_runbooks_document_safe_sequence() -> None:
    upgrade = _read("docs/deployment/upgrade-guide.md")
    migration = _read("docs/deployment/migration-safety.md")
    checklist = _read("docs/deployment/release-checklist.md")

    for fragment in (
        "make prod-env-check",
        "make prod-config",
        "make prod-backup-export",
        "make prod-schema-check",
        "make prod-upgrade",
        "make prod-post-upgrade-smoke",
        "deploy/docker/scripts/prod-upgrade-preflight.sh",
        "--replace --yes",
    ):
        assert fragment in upgrade

    for fragment in (
        "python -m skeinrank_governance_api.migrations check",
        "GET /schema/health",
        "current_matches_head=true",
        "multiple_heads=false",
        "SKEINRANK_GOVERNANCE_API_CREATE_TABLES=true",
    ):
        assert fragment in migration

    for fragment in (
        "tests/test_upgrade_runbooks.py",
        "make prod-upgrade-check",
        "make prod-backup-export",
        "make prod-smoke-strict",
        "docs/deployment/upgrade-guide.md",
    ):
        assert fragment in checklist
