from __future__ import annotations

import json
import zipfile
from pathlib import Path

from skeinrank_governance_api.support_bundle import (
    SUPPORT_BUNDLE_HEALTH_SUMMARY_VERSION,
    SUPPORT_BUNDLE_LAST_RUNS_VERSION,
    SUPPORT_BUNDLE_MANIFEST_VERSION,
    SUPPORT_BUNDLE_PLAN_VERSION,
    _build_health_summary,
    _build_last_runs_summary,
    build_support_bundle_plan,
    export_support_bundle,
    inspect_support_bundle,
)
from skeinrank_governance_api.support_bundle import main as support_bundle_main

REPO_ROOT = Path(__file__).resolve().parents[3]


def _read(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def _mini_project(tmp_path: Path) -> Path:
    root = tmp_path / "skeinrank-mini"
    (root / "docs" / "pilots").mkdir(parents=True)
    (root / "examples" / "pilots" / "reports").mkdir(parents=True)
    (
        root
        / "examples"
        / "agents"
        / "openrouter_alias_scout"
        / "reports"
        / "live-pilot"
    ).mkdir(parents=True)
    (
        root / "examples" / "benchmarks" / "platform_ops_v1" / "reports" / "synthetic"
    ).mkdir(parents=True)
    (root / "deploy" / "docker").mkdir(parents=True)
    (root / "packages" / "skeinrank-governance-api").mkdir(parents=True)
    (root / "logs").mkdir(parents=True)

    (root / "README.md").write_text("# mini\n", encoding="utf-8")
    (root / "Makefile").write_text("support-bundle-plan:\n", encoding="utf-8")
    (root / "docker-compose.dev.yml").write_text("services: {}\n", encoding="utf-8")
    (root / "packages" / "skeinrank-governance-api" / "pyproject.toml").write_text(
        "[tool.poetry]\nname = 'mini'\n", encoding="utf-8"
    )
    (root / "docs" / "README.md").write_text("# docs\n", encoding="utf-8")
    (root / "docs" / "pilots" / "first-company-pilot-runbook.md").write_text(
        "runbook\n", encoding="utf-8"
    )
    (root / "docs" / "pilots" / "troubleshooting-bundle-export.md").write_text(
        "bundle docs\n", encoding="utf-8"
    )
    (
        root / "examples" / "pilots" / "reports" / "pilot-integration-report.json"
    ).write_text(
        json.dumps(
            {
                "status": "passed",
                "api_token": "secret-token-value",
                "nested": {"password": "change-me"},
            }
        ),
        encoding="utf-8",
    )
    (
        root
        / "examples"
        / "agents"
        / "openrouter_alias_scout"
        / "reports"
        / "live-pilot"
        / "openrouter-live-pilot-report.json"
    ).write_text(
        json.dumps(
            {
                "summary": {"live_openrouter_calls": 1},
                "openrouter_api_key": "sk-or-v1-abc123SECRET",
                "authorization": "Bearer abc.def.ghi",
            }
        ),
        encoding="utf-8",
    )
    (
        root
        / "examples"
        / "benchmarks"
        / "platform_ops_v1"
        / "reports"
        / "synthetic"
        / "platform_ops_v1-5k-manifest.json"
    ).write_text(
        json.dumps({"documents_total": 5000, "token": "should-not-leak"}),
        encoding="utf-8",
    )
    (root / "deploy" / "docker" / "benchmark.env.example").write_text(
        "POSTGRES_PASSWORD=example-password\nOPENROUTER_API_KEY=sk-or-v1-raw\n",
        encoding="utf-8",
    )
    (root / "logs" / "governance-api.log").write_text(
        "INFO started\nAuthorization: Bearer log-secret-token\nOPENROUTER_API_KEY=sk-or-v1-log-secret\n",
        encoding="utf-8",
    )
    (root / ".env").write_text(
        "OPENROUTER_API_KEY=sk-or-v1-do-not-include\n", encoding="utf-8"
    )
    return root


def test_support_bundle_plan_is_read_only_and_lists_candidate_files(
    tmp_path: Path,
) -> None:
    root = _mini_project(tmp_path)

    plan = build_support_bundle_plan(project_root=root, out="support.zip")

    assert plan["schema_version"] == SUPPORT_BUNDLE_PLAN_VERSION
    assert plan["status"] == "planned"
    assert plan["candidate_files_total"] >= 4
    assert "README.md" in plan["candidate_files"]
    assert ".env" not in plan["candidate_files"]
    assert plan["log_files_total"] == 1
    assert "logs/governance-api.log" in plan["log_files"]
    assert "docker-compose.dev.yml" in plan["config_files"]
    assert "/v1/ops/alerts/report" in plan["api_snapshot"]["endpoints"]
    assert "/v1/agents/runs?limit=10" in plan["api_snapshot"]["endpoints"]
    assert plan["safety"] == {
        "openrouter_calls": False,
        "elasticsearch_calls": False,
        "database_calls": False,
        "runtime_mutation_enabled": False,
        "raw_secrets_included": False,
        "generated_bundle_committed_by_default": False,
    }


def test_support_bundle_export_writes_zip_and_redacts_secrets(
    tmp_path: Path, monkeypatch
) -> None:
    root = _mini_project(tmp_path)
    out = root / "examples" / "pilots" / "reports" / "bundle.zip"
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-env-secret")
    monkeypatch.setenv("SKEINRANK_AGENT_API_TOKEN", "agent-token-secret")
    monkeypatch.setenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")

    manifest = export_support_bundle(project_root=root, out=out)

    assert out.exists()
    assert manifest["schema_version"] == SUPPORT_BUNDLE_MANIFEST_VERSION
    assert manifest["status"] == "exported"
    assert manifest["safety"]["raw_secrets_included"] is False
    assert (
        manifest["health_summary"]["schema_version"]
        == SUPPORT_BUNDLE_HEALTH_SUMMARY_VERSION
    )
    assert (
        manifest["last_runs_summary"]["schema_version"]
        == SUPPORT_BUNDLE_LAST_RUNS_VERSION
    )
    assert manifest["config_inventory"]["files_total"] >= 2
    assert manifest["log_inventory"]["files_total"] == 1
    assert any(item["category"] == "generated_report" for item in manifest["files"])
    assert any(item["category"] == "log" for item in manifest["files"])

    raw_zip = out.read_bytes()
    assert b"sk-or-v1-env-secret" not in raw_zip
    assert b"sk-or-v1-abc123SECRET" not in raw_zip
    assert b"secret-token-value" not in raw_zip
    assert b"should-not-leak" not in raw_zip
    assert b"log-secret-token" not in raw_zip
    assert b"sk-or-v1-log-secret" not in raw_zip

    with zipfile.ZipFile(out) as bundle:
        names = set(bundle.namelist())
        assert "manifest.json" in names
        assert "env/redacted_environment.json" in names
        assert "system/runtime_metadata.json" in names
        assert "commands/replay_commands.txt" in names
        assert "health/health_summary.json" in names
        assert "runs/last_agent_runs.json" in names
        assert "config/config_inventory.json" in names
        assert "logs/log_inventory.json" in names
        assert "files/README.md" in names
        assert "files/logs/governance-api.log" in names
        assert "files/.env" not in names
        concatenated = b"\n".join(
            bundle.read(name) for name in names if not name.endswith("/")
        )
        assert b"sk-or-v1-env-secret" not in concatenated
        assert b"sk-or-v1-abc123SECRET" not in concatenated
        assert b"secret-token-value" not in concatenated
        assert b"should-not-leak" not in concatenated
        assert b"log-secret-token" not in concatenated
        assert b"sk-or-v1-log-secret" not in concatenated
        assert b"***REDACTED***" in concatenated
        env = json.loads(bundle.read("env/redacted_environment.json"))
        assert env["variables"]["OPENROUTER_API_KEY"] == "***REDACTED***"
        assert env["variables"]["SKEINRANK_AGENT_API_TOKEN"] == "***REDACTED***"
        assert env["variables"]["OPENROUTER_MODEL"] == "openai/gpt-4o-mini"


def test_support_bundle_inspect_reads_manifest_without_extracting(
    tmp_path: Path,
) -> None:
    root = _mini_project(tmp_path)
    out = root / "bundle.zip"
    exported = export_support_bundle(project_root=root, out=out)

    inspected = inspect_support_bundle(out)

    assert inspected["schema_version"] == SUPPORT_BUNDLE_MANIFEST_VERSION
    assert inspected["bundle_path"] == exported["bundle_path"]
    assert inspected["files"] == exported["files"]


def test_support_bundle_cli_plan_export_and_inspect(tmp_path: Path, capsys) -> None:
    root = _mini_project(tmp_path)
    out = root / "examples" / "pilots" / "reports" / "cli-bundle.zip"

    assert (
        support_bundle_main(["plan", "--project-root", str(root), "--out", str(out)])
        == 0
    )
    plan_stdout = capsys.readouterr().out
    assert '"schema_version": "skeinrank.support_bundle_plan.v1"' in plan_stdout

    assert (
        support_bundle_main(["export", "--project-root", str(root), "--out", str(out)])
        == 0
    )
    export_stdout = capsys.readouterr().out
    assert '"schema_version": "skeinrank.support_bundle_manifest.v1"' in export_stdout
    assert out.exists()

    assert support_bundle_main(["inspect", "--file", str(out)]) == 0
    inspect_stdout = capsys.readouterr().out
    assert '"status": "exported"' in inspect_stdout


def test_support_bundle_health_and_last_runs_summaries_are_sanitized() -> None:
    snapshots = [
        {
            "endpoint": "/livez",
            "status": "ok",
            "http_status": 200,
            "payload": {"status": "ok"},
        },
        {
            "endpoint": "/v1/ops/alerts/report",
            "status": "ok",
            "http_status": 200,
            "payload": {"status": "degraded", "severity": "warning"},
        },
        {
            "endpoint": "/v1/agents/runs?limit=10",
            "status": "ok",
            "http_status": 200,
            "payload": [
                {
                    "run_id": "run-1",
                    "agent_name": "openrouter-alias-scout",
                    "status": "failed",
                    "profile_name": "platform_ops",
                    "binding_id": 7,
                    "created_at": "2026-05-28T00:00:00Z",
                    "updated_at": "2026-05-28T00:01:00Z",
                    "artifacts_uri": "reports/run-1.json",
                    "report_uri": "reports/run-1-report.json",
                    "secret_token": "must-not-be-copied",
                }
            ],
        },
    ]

    health = _build_health_summary(snapshots)
    runs = _build_last_runs_summary(snapshots)

    assert health["schema_version"] == SUPPORT_BUNDLE_HEALTH_SUMMARY_VERSION
    assert health["status"] == "degraded"
    assert "/v1/ops/alerts/report" in health["degraded_endpoints"]
    assert runs["schema_version"] == SUPPORT_BUNDLE_LAST_RUNS_VERSION
    assert runs["runs_total"] == 1
    assert runs["by_status"] == {"failed": 1}
    assert runs["runs"][0] == {
        "run_id": "run-1",
        "agent_name": "openrouter-alias-scout",
        "status": "failed",
        "profile_name": "platform_ops",
        "binding_id": 7,
        "created_at": "2026-05-28T00:00:00Z",
        "updated_at": "2026-05-28T00:01:00Z",
        "artifacts_uri": "reports/run-1.json",
        "report_uri": "reports/run-1-report.json",
    }


def test_support_bundle_docs_reference_real_targets_and_cli() -> None:
    guide = _read("docs/pilots/troubleshooting-bundle-export.md")
    production_guide = _read("docs/pilots/support-bundle-production.md")
    makefile = _read("Makefile")
    pyproject = _read("packages/skeinrank-governance-api/pyproject.toml")
    docs_readme = _read("docs/README.md")
    package_readme = _read("packages/skeinrank-governance-api/README.md")

    for target in [
        "support-bundle-plan",
        "support-bundle-export",
        "support-bundle-inspect",
        "support-bundle-clean",
    ]:
        assert f"make {target}" in guide or target == "support-bundle-clean"
        assert f"{target}:" in makefile

    # The CLI defines common args on each subcommand, so Makefile targets must
    # call `support_bundle plan --project-root ...`, not
    # `support_bundle --project-root ... plan`. This guards the shell path that
    # tests do not execute through Poetry.
    assert "$(SUPPORT_BUNDLE_CLI) plan $(SUPPORT_BUNDLE_COMMON_ARGS)" in makefile
    assert "$(SUPPORT_BUNDLE_CLI) export $(SUPPORT_BUNDLE_COMMON_ARGS)" in makefile
    assert (
        "$(SUPPORT_BUNDLE_CLI) inspect --file ../../$(SUPPORT_BUNDLE_OUT)" in makefile
    )

    assert "skeinrank_governance_api.support_bundle" in guide
    assert "logs/log_inventory.json" in production_guide
    assert "runs/last_agent_runs.json" in production_guide
    assert "health/health_summary.json" in production_guide
    assert "skeinrank-governance-support-bundle" in pyproject
    assert "pilots/troubleshooting-bundle-export.md" in docs_readme
    assert "pilots/support-bundle-production.md" in docs_readme
    assert "support_bundle" in package_readme
