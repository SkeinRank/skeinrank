from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
CONFIG_PATH = REPO_ROOT / "examples" / "pilots" / "elasticsearch_pilot.example.json"
MODULE_PATH = (
    REPO_ROOT
    / "packages"
    / "skeinrank-governance-api"
    / "skeinrank_governance_api"
    / "pilot_integration.py"
)


def _read(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def _load_module() -> Any:
    spec = importlib.util.spec_from_file_location("pilot_integration_49e", MODULE_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["pilot_integration_49e"] = module
    spec.loader.exec_module(module)
    return module


class _FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, Any]] = []

    def ensure_token(self) -> str:
        return "token"

    def request(self, method: str, path: str, payload: Any = None) -> Any:
        self.calls.append((method, path, payload))
        if path == "/healthz":
            return {"status": "ok"}
        if path == "/schema/health":
            return {
                "ok": True,
                "current_matches_head": True,
                "current_revision": "head",
            }
        if path == "/v1/governance/elasticsearch/connection/status":
            return {"configured": True, "ok": True, "cluster_name": "docker-cluster"}
        if path.endswith("/mapping"):
            return {
                "fields": [
                    {"name": "title"},
                    {"name": "body"},
                    {"name": "skeinrank_terms"},
                ]
            }
        if path == "/v1/console/dictionary/validate":
            return {
                "status": "valid",
                "profile_name": payload["profile_name"],
                "summary": {"terms_total": 4},
            }
        if path == "/v1/console/dictionary/import":
            return {
                "status": "applied",
                "profile_name": payload["profile_name"],
                "summary": {"created_terms": 4},
            }
        if path == "/v1/governance/elasticsearch/bindings":
            return {
                "id": 7,
                "name": payload["name"],
                "index_name": payload["index_name"],
                "mode": payload["mode"],
                "is_enabled": True,
            }
        if path.startswith("/v1/governance/elasticsearch/bindings?"):
            return [
                {
                    "id": 7,
                    "name": "Platform Ops Pilot Docs",
                    "index_name": "platform-ops-benchmark-docs",
                    "mode": "dry_run",
                    "is_enabled": True,
                }
            ]
        if path.endswith("/evidence"):
            return {"documents": [{"document_id": "doc-1"}]}
        if path == "/v1/query/plan":
            query = payload["query"]
            if "otel" in query:
                return {"canonical_values": ["opentelemetry", "postgresql"]}
            return {"canonical_values": ["kubernetes", "rabbitmq"]}
        raise AssertionError(f"Unexpected request: {method} {path}")


def test_pilot_config_example_is_valid_json() -> None:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))

    assert config["schema_version"] == "skeinrank.pilot.integration.v1"
    assert config["dictionary"]["schema_version"] == "skeinrank.dictionary.v1"
    assert config["binding"]["index_name"] == "platform-ops-benchmark-docs"
    assert config["binding"]["text_fields"] == ["title", "body"]
    assert config["evidence_checks"]
    assert config["runtime_queries"]


def test_pilot_plan_cli_is_offline() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(MODULE_PATH),
            "plan",
            "--config",
            str(CONFIG_PATH),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    plan = json.loads(result.stdout)

    assert plan["schema_version"] == "skeinrank.pilot.integration_plan.v1"
    assert plan["network_calls"] is False
    assert plan["openrouter_calls"] is False
    assert plan["runtime_mutation_enabled"] is False
    assert plan["dictionary"]["terms_total"] == 4


def test_pilot_preflight_seed_and_eval_with_fake_client() -> None:
    module = _load_module()
    config = module.load_pilot_config(CONFIG_PATH)
    client = _FakeClient()

    preflight = module.run_pilot_preflight(client, config)
    seed = module.seed_pilot_integration(client, config)
    report = module.run_pilot_evaluation(client, config)

    assert preflight["status"] == "passed"
    assert seed["status"] == "seeded"
    assert seed["binding"]["binding"]["id"] == 7
    assert report["schema_version"] == "skeinrank.pilot.integration_report.v1"
    assert report["status"] == "passed"
    assert report["checks_failed"] == 0
    assert report["safety"]["openrouter_calls"] is False
    assert (
        "POST",
        "/v1/console/dictionary/import",
        config["dictionary"],
    ) in client.calls


def test_pilot_makefile_targets_are_available() -> None:
    makefile = _read("Makefile")

    for target in [
        "pilot-plan:",
        "pilot-preflight:",
        "pilot-seed:",
        "pilot-eval:",
        "pilot-report:",
        "pilot-run:",
        "pilot-stack-run:",
    ]:
        assert target in makefile

    assert "skeinrank_governance_api.pilot_integration" in makefile
    assert (
        "PILOT_CONFIG ?= examples/pilots/elasticsearch_pilot.example.json" in makefile
    )
    assert "PILOT_CONFIG_PATH := $(abspath $(PILOT_CONFIG))" in makefile
    assert "PILOT_REPORT_PATH := $(abspath $(PILOT_REPORT))" in makefile
    assert '--config "$(PILOT_CONFIG_PATH)"' in makefile
    assert '--config "../../$(PILOT_CONFIG)"' not in makefile
    assert 'report --file "$(PILOT_REPORT_PATH)"' in makefile
    assert "PILOT_AUTH_ARGS" in makefile


def test_pilot_docs_are_linked() -> None:
    docs_readme = _read("docs/README.md")
    root_readme = _read("README.md")
    package_readme = _read("packages/skeinrank-governance-api/README.md")
    guide = _read("docs/pilots/elasticsearch-pilot-integration.md")

    assert "pilots/elasticsearch-pilot-integration.md" in docs_readme
    assert "make pilot-plan" in root_readme
    assert "skeinrank-governance-pilot" in package_readme
    assert "skeinrank.pilot.integration_report.v1" in guide
    assert "No OpenRouter calls are made" in guide
