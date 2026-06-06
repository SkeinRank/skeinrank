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


class FakeSmokeClient:
    def __init__(self, *, validation_status: str = "passed") -> None:
        self.validation_status = validation_status
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.suggest_calls = 0

    def validate_alias(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("validate", kwargs))
        return {
            "canonical_value": kwargs["canonical_value"],
            "alias_value": kwargs["alias_value"],
            "slot": kwargs["slot"],
            "validation_summary": {"status": self.validation_status},
        }

    def suggest_alias(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("suggest", kwargs))
        self.suggest_calls += 1
        created = self.suggest_calls == 1
        return {
            "created": created,
            "suggestion": {
                "id": 100,
                "status": "pending",
                "alias_value": kwargs["alias_value"],
                "canonical_value": kwargs["canonical_value"],
            },
            "validation_summary": {"status": "passed"},
        }


def test_new_alias_smoke_files_are_present_and_documented() -> None:
    assert (AGENT_DIR / "new_alias_smoke.py").exists()
    readme = (AGENT_DIR / "README.md").read_text(encoding="utf-8")
    guide = (REPO_ROOT / "docs" / "guides" / "openrouter-agent.md").read_text(
        encoding="utf-8"
    )
    for content in (readme, guide):
        assert "--print-new-alias-smoke-plan" in content
        assert "--print-new-alias-smoke-plan" in content
        assert "--submit-new-alias-smoke-test" in content


def test_new_alias_smoke_llm_report_contains_ready_payload() -> None:
    module = _load_module(
        "agent_new_alias_smoke_report", AGENT_DIR / "new_alias_smoke.py"
    )
    config = module.NewAliasSmokeConfig(alias_value="pgx")

    report = module.build_new_alias_smoke_llm_report(config)

    assert report["schema_version"] == "skeinrank.agent_llm_review_report.v1"
    item = report["reviewed_items"][0]
    assert item["proposal_ready_for_validation"] is True
    assert item["proposal_payload"]["alias_value"] == "pgx"
    assert item["proposal_payload"]["canonical_value"] == "postgresql"
    assert item["proposal_payload"]["idempotency_key"]


def test_new_alias_smoke_plan_is_offline_and_safe() -> None:
    module = _load_module(
        "agent_new_alias_smoke_plan", AGENT_DIR / "new_alias_smoke.py"
    )
    plan = module.build_new_alias_smoke_plan(module.NewAliasSmokeConfig(), submit=False)

    assert plan["schema_version"] == "skeinrank.agent_new_alias_smoke_plan.v1"
    assert plan["skeinrank_api_calls"] is False
    assert plan["will_validate_alias"] is True
    assert plan["will_submit_alias"] is False
    assert plan["safety"]["runtime_mutation_enabled"] is False


def test_new_alias_smoke_validate_only_does_not_submit() -> None:
    module = _load_module(
        "agent_new_alias_smoke_validate", AGENT_DIR / "new_alias_smoke.py"
    )
    client = FakeSmokeClient()

    report = module.run_new_alias_smoke_test(
        client=client,
        config=module.NewAliasSmokeConfig(alias_value="pgx"),
        submit=False,
    )

    assert [call[0] for call in client.calls] == ["validate"]
    assert report["summary"]["validated"] == 1
    assert report["summary"]["submitted"] == 0
    assert report["result"]["status"] == "validation_passed"


def test_new_alias_smoke_submit_verifies_idempotent_retry() -> None:
    module = _load_module(
        "agent_new_alias_smoke_submit", AGENT_DIR / "new_alias_smoke.py"
    )
    client = FakeSmokeClient()

    report = module.run_new_alias_smoke_test(
        client=client,
        config=module.NewAliasSmokeConfig(alias_value="pgx"),
        submit=True,
    )

    assert [call[0] for call in client.calls] == ["validate", "suggest", "suggest"]
    assert report["summary"]["submitted"] == 1
    assert report["summary"]["created"] == 1
    assert report["summary"]["idempotent_retry_verified"] == 1
    assert report["result"]["idempotent_retry_verified"] is True


def test_new_alias_smoke_blocked_validation_is_not_submitted() -> None:
    module = _load_module(
        "agent_new_alias_smoke_blocked", AGENT_DIR / "new_alias_smoke.py"
    )
    client = FakeSmokeClient(validation_status="blocked")

    report = module.run_new_alias_smoke_test(
        client=client,
        config=module.NewAliasSmokeConfig(alias_value="pgx"),
        submit=True,
    )

    assert [call[0] for call in client.calls] == ["validate"]
    assert report["summary"]["blocked"] == 1
    assert report["summary"]["submitted"] == 0


def test_cli_print_new_alias_smoke_plan() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(AGENT_DIR / "run_alias_scout.py"),
            "--config",
            str(AGENT_DIR / "agent_config.example.json"),
            "--print-new-alias-smoke-plan",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)

    assert payload["schema_version"] == "skeinrank.agent_new_alias_smoke_plan.v1"
    assert payload["smoke_alias"] == "pgx"
    assert payload["will_submit_alias"] is False
