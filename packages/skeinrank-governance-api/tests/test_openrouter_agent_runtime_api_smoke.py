from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
AGENT_DIR = REPO_ROOT / "examples" / "agents" / "openrouter_alias_scout"


def _load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class FakeRuntimeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any] | None]] = []

    def request(
        self, method: str, path: str, payload: dict[str, Any] | None = None
    ) -> Any:
        self.calls.append((method, path, payload))
        if path == "/v1/text/canonicalize":
            return {
                "profile_name": payload.get("profile_name", "infra_incidents"),
                "normalized_profile_name": "infra_incidents",
                "mode": payload["mode"],
                "original_text": payload["text"],
                "canonical_text": "postgresql timeout after kubernetes rollout",
                "changed": True,
                "canonical_values": ["postgresql", "kubernetes"],
                "matched_aliases": ["pg", "k8s"],
                "replacements": [],
                "evidence": [],
                "warnings": [],
            }
        if path == "/v1/query/plan":
            return {
                "profile_name": payload.get("profile_name", "infra_incidents"),
                "normalized_profile_name": "infra_incidents",
                "query": payload["query"],
                "canonical_query": "postgresql timeout kubernetes rollout",
                "changed": True,
                "text_fields": payload["text_fields"],
                "target_field": payload["target_field"],
                "canonical_values": ["postgresql", "kubernetes"],
                "matched_aliases": ["pg", "k8s"],
                "replacements": [],
                "evidence": [],
                "elasticsearch": {"query": {"bool": {"should": []}}},
                "warnings": [],
            }
        if path.startswith("/v1/headless/snapshots/export?"):
            return {
                "schema_version": "skeinrank.runtime_snapshot_artifact.v1",
                "snapshot": {"version": "runtime-smoke-v1"},
                "aliases": [{"canonical_value": "postgresql", "aliases": ["pg"]}],
            }
        raise AssertionError(f"Unexpected request: {method} {path}")


class FailingRuntimeClient:
    def request(
        self, method: str, path: str, payload: dict[str, Any] | None = None
    ) -> Any:
        raise RuntimeError(f"boom: {method} {path}")


def test_runtime_api_smoke_plan_is_read_only_and_uses_existing_endpoints() -> None:
    module = _load_module("agent_runtime_api_smoke", AGENT_DIR / "runtime_api_smoke.py")
    config = module.RuntimeApiSmokeConfig(artifacts_dir=Path("/tmp/runtime-smoke"))
    plan = module.build_runtime_api_smoke_plan(config)

    assert plan["schema_version"] == "skeinrank.agent_runtime_api_smoke_plan.v1"
    assert "POST /v1/text/canonicalize" in plan["api_flow"]
    assert "POST /v1/query/plan" in plan["api_flow"]
    assert plan["safe_defaults"]["runtime_mutation_enabled"] is False
    assert plan["safe_defaults"]["proposal_submission_enabled"] is False
    assert plan["payloads"]["canonicalize"]["profile_name"] == "infra_incidents"


def test_runtime_api_smoke_runs_canonicalize_and_query_plan_without_mutation() -> None:
    module = _load_module(
        "agent_runtime_api_smoke_run", AGENT_DIR / "runtime_api_smoke.py"
    )
    client = FakeRuntimeClient()
    report = module.run_runtime_api_smoke(
        client=client,
        config=module.RuntimeApiSmokeConfig(artifacts_dir=Path("/tmp/runtime-smoke")),
    )

    assert report["schema_version"] == "skeinrank.agent_runtime_api_smoke.v1"
    assert report["status"] == "passed"
    assert report["runtime_mutation_enabled"] is False
    assert report["snapshot_publish_enabled"] is False
    assert report["proposal_submission_enabled"] is False
    assert report["summary"]["passed"] == 2
    assert report["summary"]["skipped"] == 1
    assert [call[1] for call in client.calls] == [
        "/v1/text/canonicalize",
        "/v1/query/plan",
    ]


def test_runtime_api_smoke_can_export_binding_snapshot_when_requested() -> None:
    module = _load_module(
        "agent_runtime_api_smoke_snapshot", AGENT_DIR / "runtime_api_smoke.py"
    )
    client = FakeRuntimeClient()
    config = module.RuntimeApiSmokeConfig(
        artifacts_dir=Path("/tmp/runtime-smoke"), binding_id=42
    )
    report = module.run_runtime_api_smoke(
        client=client, config=config, export_snapshot=True
    )

    assert report["status"] == "passed"
    assert report["summary"]["passed"] == 3
    assert any(
        path.startswith("/v1/headless/snapshots/export?") for _, path, _ in client.calls
    )
    assert report["responses"]["snapshot_export"]["schema_version"]


def test_runtime_api_smoke_reports_failed_api_calls() -> None:
    module = _load_module(
        "agent_runtime_api_smoke_failure", AGENT_DIR / "runtime_api_smoke.py"
    )
    report = module.run_runtime_api_smoke(
        client=FailingRuntimeClient(),
        config=module.RuntimeApiSmokeConfig(artifacts_dir=Path("/tmp/runtime-smoke")),
    )

    assert report["status"] == "failed"
    assert report["recommended_exit_code"] == 2
    assert report["summary"]["failed"] == 2


def test_cli_print_runtime_api_smoke_plan_outputs_json() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(AGENT_DIR / "run_alias_scout.py"),
            "--config",
            str(AGENT_DIR / "agent_config.example.json"),
            "--print-runtime-api-smoke-plan",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)

    assert payload["schema_version"] == "skeinrank.agent_runtime_api_smoke_plan.v1"
    assert payload["workflow"] == "runtime_api_smoke"
    assert "patch" not in payload
    assert payload["safe_defaults"]["runtime_mutation_enabled"] is False
    assert payload["payloads"]["query_plan"]["query"]
