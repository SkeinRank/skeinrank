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


def test_57c_company_model_integration_docs_and_cli_exist() -> None:
    assert (AGENT_DIR / "company_model_integration.py").exists()
    docs = [
        REPO_ROOT / "docs" / "README.md",
        REPO_ROOT / "packages" / "skeinrank-governance-api" / "README.md",
        AGENT_DIR / "README.md",
        REPO_ROOT / "docs" / "deployment" / "company-model-integration.md",
        REPO_ROOT / "docs" / "deployment" / "model-provider-adapters.md",
    ]
    for path in docs:
        content = path.read_text(encoding="utf-8")
        assert "Patch 57C" in content, path
        assert "local_endpoint" in content, path

    runner = (AGENT_DIR / "run_alias_scout.py").read_text(encoding="utf-8")
    assert "--print-company-model-integration-plan" in runner


def test_company_model_integration_plan_cli_is_offline_and_redacted() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(AGENT_DIR / "run_alias_scout.py"),
            "--config",
            str(AGENT_DIR / "agent_config.example.json"),
            "--print-company-model-integration-plan",
        ],
        check=True,
        capture_output=True,
        text=True,
        env={
            "PATH": "",
            "SKEINRANK_MODEL_PROVIDER_TYPE": "local_endpoint",
            "SKEINRANK_MODEL_PROVIDER_BASE_URL": "http://127.0.0.1:8000/v1",
            "SKEINRANK_MODEL_PROVIDER_MODEL": "company-model",
            "SKEINRANK_LOCAL_MODEL_API_KEY": "secret-value-that-must-not-leak",
        },
    )
    assert "secret-value-that-must-not-leak" not in result.stdout
    plan = json.loads(result.stdout)
    assert plan["schema_version"] == "skeinrank.company_model_integration_plan.v1"
    assert plan["status"] == "planned"
    assert plan["provider_plan"]["provider"]["provider_type"] == "local_endpoint"
    assert plan["company_model"]["api_key_value"] is None
    assert plan["safety"] == {
        "network_calls": False,
        "openrouter_calls": False,
        "local_endpoint_calls": False,
        "skeinrank_api_calls": False,
        "requires_explicit_live_run": True,
        "runtime_mutation_enabled": False,
        "proposal_submission_default": False,
        "snapshot_publish_enabled": False,
        "secrets_included": False,
    }
    assert "--print-model-provider-plan" in plan["commands"]["preview_provider_plan"]
    assert "--run-openrouter-live-pilot" in plan["commands"]["one_call_smoke"]
    assert (
        "--write-openrouter-validated-pilot-report"
        in plan["commands"]["validated_pilot_after_seeding"]
    )


def test_company_model_integration_plan_warns_when_local_base_url_lacks_v1() -> None:
    provider_module = _load_module(
        "agent_model_provider_57c", AGENT_DIR / "model_provider.py"
    )
    company_module = _load_module(
        "agent_company_model_integration_57c",
        AGENT_DIR / "company_model_integration.py",
    )
    cfg = provider_module.ModelProviderConfig.from_mapping(
        {
            "provider_type": "local_endpoint",
            "provider_name": "company-gateway",
            "base_url": "http://127.0.0.1:8000",
            "model": "company-model",
            "require_api_key": False,
        }
    )
    plan = company_module.build_company_model_integration_plan(
        cfg,
        skeinrank_api_url="http://127.0.0.1:8010",
        profile_name="platform_ops_benchmark",
    )
    checks = {check["name"]: check for check in plan["checks"]}
    assert checks["provider_type_supported"]["status"] == "passed"
    assert checks["local_endpoint_base_url"]["status"] == "warning"
    assert checks["local_endpoint_api_key_policy"]["status"] == "passed"
    assert plan["skeinrank_context"]["profile_name"] == "platform_ops_benchmark"


def test_company_model_integration_plan_references_existing_docs_commands() -> None:
    doc = (
        REPO_ROOT / "docs" / "deployment" / "company-model-integration.md"
    ).read_text(encoding="utf-8")
    runner = (AGENT_DIR / "run_alias_scout.py").read_text(encoding="utf-8")
    for command in [
        "--print-company-model-integration-plan",
        "--print-model-provider-plan",
        "--run-openrouter-live-pilot",
        "--write-openrouter-validated-pilot-report",
    ]:
        assert command in doc
        assert command in runner
    assert "proposal_submission_enabled == false" in doc
    assert "secrets_included" in doc
