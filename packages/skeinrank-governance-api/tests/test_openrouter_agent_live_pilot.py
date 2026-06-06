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


def _mock_openrouter_response(action: str = "propose") -> dict[str, Any]:
    payload: dict[str, Any]
    if action == "propose":
        payload = {
            "action": "propose",
            "confidence": 0.93,
            "reason": "Pilot evidence links pg to PostgreSQL incident handling.",
            "risk_flags": [],
            "alias_value": "pg",
            "canonical_value": "postgresql",
            "slot": "database",
            "context": "pg appears near postgres failover and pool evidence.",
        }
    else:
        payload = {
            "action": action,
            "confidence": 0.4,
            "reason": "Pilot test response.",
            "risk_flags": ["test"],
        }
    return {
        "id": "or-live-pilot-1",
        "choices": [{"message": {"role": "assistant", "content": json.dumps(payload)}}],
        "usage": {
            "prompt_tokens": 120,
            "completion_tokens": 40,
            "total_tokens": 160,
            "cost": 0.0002,
        },
    }


class _ValidationClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def validate_alias(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("validate", dict(kwargs)))
        return {
            "validation_summary": {
                "status": "passed",
                "checks": {"alias_state": {"status": "passed"}},
                "counts": {"passed": 1, "warning": 0, "blocked": 0},
            }
        }

    def suggest_alias(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("suggest", dict(kwargs)))
        return {"created": True, "suggestion_id": 123}


def _load_inputs() -> tuple[Any, Any, list[dict[str, Any]]]:
    runner = _load_module("agent_run_alias_scout_48b", AGENT_DIR / "run_alias_scout.py")
    config = runner.AgentRunnerConfig.from_file(AGENT_DIR / "agent_config.example.json")
    failed_queries = runner.load_failed_queries(config.failed_queries_path)
    return runner, config, failed_queries


def test_48b_live_pilot_files_and_docs_are_linked() -> None:
    assert (AGENT_DIR / "live_pilot.py").exists()

    readme = (AGENT_DIR / "README.md").read_text(encoding="utf-8")
    for fragment in (
        "Live pilot",
        "--print-openrouter-live-pilot-plan",
        "--run-openrouter-live-pilot",
        "skeinrank.openrouter_live_pilot_report.v1",
    ):
        assert fragment in readme

    docs = (REPO_ROOT / "docs" / "benchmarks" / "openrouter-live-pilot.md").read_text(
        encoding="utf-8"
    )
    assert "OPENROUTER_API_KEY" in docs
    assert "does not approve/apply" in docs


def test_live_pilot_plan_cli_is_offline_and_bounded() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(AGENT_DIR / "run_alias_scout.py"),
            "--config",
            str(AGENT_DIR / "agent_config.example.json"),
            "--print-openrouter-live-pilot-plan",
            "--max-candidates",
            "1",
            "--max-llm-calls",
            "1",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    plan = json.loads(result.stdout)
    assert plan["schema_version"] == "skeinrank.openrouter_live_pilot_plan.v1"
    assert plan["openrouter_calls"] is False
    assert plan["skeinrank_api_calls"] is False
    assert plan["pilot_config"]["max_candidates"] == 1
    assert plan["pilot_config"]["max_llm_calls"] == 1
    assert plan["safety"]["submit_proposals_default"] is False


def test_live_pilot_uses_mock_openrouter_without_skeinrank_mutation() -> None:
    runner, config, failed_queries = _load_inputs()
    live_pilot = _load_module("agent_live_pilot_48b", AGENT_DIR / "live_pilot.py")
    client_module = _load_module(
        "agent_openrouter_client_48b", AGENT_DIR / "openrouter_client.py"
    )
    calls: list[tuple[str, str]] = []

    def transport(method: str, path: str, payload: dict[str, Any] | None) -> Any:
        assert payload is not None
        calls.append((method, path))
        return _mock_openrouter_response("propose")

    client = client_module.OpenRouterClient(api_key="test-key", transport=transport)
    report = live_pilot.run_openrouter_live_pilot(
        failed_queries=failed_queries,
        evidence_records_path=config.evidence_records_path,
        openrouter_client=client,
        pilot_config=live_pilot.OpenRouterLivePilotConfig(
            max_candidates=1,
            max_llm_calls=1,
            max_proposals=1,
            validate_with_skeinrank=False,
        ),
        candidate_config=config.candidate_discovery,
        evidence_config=config.evidence_sampler,
        demo_config=config.demo_report,
        canonical_hints_config=config.canonical_hints,
        submission_config=config.proposal_submission,
        security_config=config.security_profile,
        openrouter_model=config.openrouter_model,
        profile_name=config.default_profile_name,
        proposal_source_name=config.proposal_source_name,
    )

    assert calls == [("POST", "/chat/completions")]
    assert report["schema_version"] == "skeinrank.openrouter_live_pilot_report.v1"
    assert report["openrouter_calls"] is True
    assert report["skeinrank_api_calls"] is False
    assert report["summary"]["candidates_sent_to_model"] == 1
    assert report["summary"]["proposals_prepared"] == 1
    assert report["summary"]["eligible_proposals"] == 1
    assert report["summary"]["estimated_cost_usd"] == 0.0002
    assert report["proposal_submission_report"] is None
    assert report["safety"]["agent_may_mutate_runtime"] is False


def test_live_pilot_can_validate_ready_payloads_with_mock_skeinrank_client() -> None:
    _, config, failed_queries = _load_inputs()
    live_pilot = _load_module(
        "agent_live_pilot_48b_validate", AGENT_DIR / "live_pilot.py"
    )
    client_module = _load_module(
        "agent_openrouter_client_48b_validate", AGENT_DIR / "openrouter_client.py"
    )
    openrouter_client = client_module.OpenRouterClient(
        api_key="test-key",
        transport=lambda method, path, payload: _mock_openrouter_response("propose"),
    )
    skeinrank_client = _ValidationClient()

    report = live_pilot.run_openrouter_live_pilot(
        failed_queries=failed_queries,
        evidence_records_path=config.evidence_records_path,
        openrouter_client=openrouter_client,
        pilot_config=live_pilot.OpenRouterLivePilotConfig(
            max_candidates=1,
            max_llm_calls=1,
            max_proposals=1,
            validate_with_skeinrank=True,
            submit_proposals=False,
        ),
        candidate_config=config.candidate_discovery,
        evidence_config=config.evidence_sampler,
        demo_config=config.demo_report,
        canonical_hints_config=config.canonical_hints,
        submission_config=config.proposal_submission,
        security_config=config.security_profile,
        skeinrank_client=skeinrank_client,
        openrouter_model=config.openrouter_model,
        profile_name=config.default_profile_name,
        proposal_source_name=config.proposal_source_name,
    )

    assert [call[0] for call in skeinrank_client.calls] == ["validate"]
    assert report["skeinrank_api_calls"] is True
    assert report["summary"]["validation_passed"] == 1
    assert report["summary"]["submitted"] == 0
    assert report["status"] == "passed"


def test_live_pilot_cli_requires_openrouter_key_for_live_run() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(AGENT_DIR / "run_alias_scout.py"),
            "--config",
            str(AGENT_DIR / "agent_config.example.json"),
            "--run-openrouter-live-pilot",
            "--max-candidates",
            "1",
        ],
        check=False,
        capture_output=True,
        text=True,
        env={"PATH": ""},
    )
    assert result.returncode != 0
    assert "OpenRouter API key is required" in result.stderr


def test_live_pilot_makefile_report_targets_run_live_mode() -> None:
    makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")

    assert "agent-openrouter-pilot-report:" in makefile
    assert (
        "--run-openrouter-live-pilot --write-openrouter-live-pilot-report "
        "examples/agents/openrouter_alias_scout/reports/live-pilot/"
        "openrouter-live-pilot-report.json"
    ) in makefile
    assert (
        "--run-openrouter-live-pilot --write-openrouter-live-pilot-report "
        "examples/agents/openrouter_alias_scout/reports/live-pilot/"
        "openrouter-live-pilot-validated-report.json --pilot-validate-proposals"
    ) in makefile


def test_live_pilot_validation_preflight_fails_before_openrouter_when_api_is_down() -> (
    None
):
    result = subprocess.run(
        [
            sys.executable,
            str(AGENT_DIR / "run_alias_scout.py"),
            "--config",
            str(AGENT_DIR / "agent_config.example.json"),
            "--run-openrouter-live-pilot",
            "--pilot-validate-proposals",
            "--max-candidates",
            "1",
            "--max-llm-calls",
            "1",
        ],
        check=False,
        capture_output=True,
        text=True,
        env={
            "PATH": "/usr/bin:/bin",
            "OPENROUTER_API_KEY": "test-openrouter-key",
            # Keep this test isolated from a locally running dev API.
            # The assertion below verifies that validation/submission preflight
            # fails before any OpenRouter request can be made.
            "SKEINRANK_AGENT_API_URL": "http://127.0.0.1:9",
        },
    )

    assert result.returncode == 2
    assert "SkeinRank Governance API is required" in result.stderr
    assert "Configured URL: http://127.0.0.1:9" in result.stderr
    stderr_before_message = result.stderr.split(
        "SkeinRank Governance API is required", 1
    )[0]
    assert "OpenRouter" not in stderr_before_message


def test_live_pilot_report_writer_prints_operator_summary(tmp_path: Path) -> None:
    runner, _config, _failed_queries = _load_inputs()
    summary = runner._live_pilot_cli_summary(
        {
            "status": "passed",
            "openrouter_calls": True,
            "skeinrank_api_calls": False,
            "summary": {"live_openrouter_calls": 1, "proposals_prepared": 1},
            "recommended_exit_code": 0,
        },
        tmp_path / "pilot-report.json",
    )

    assert summary == {
        "schema_version": "skeinrank.openrouter_live_pilot_cli_summary.v1",
        "status": "passed",
        "report": str(tmp_path / "pilot-report.json"),
        "openrouter_calls": True,
        "skeinrank_api_calls": False,
        "summary": {"live_openrouter_calls": 1, "proposals_prepared": 1},
        "recommended_exit_code": 0,
    }


def test_49d_validated_pilot_plan_is_explicit_and_validate_only() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(AGENT_DIR / "run_alias_scout.py"),
            "--config",
            str(AGENT_DIR / "agent_config.example.json"),
            "--print-openrouter-validated-pilot-plan",
            "--profile-name",
            "platform_ops_benchmark",
            "--binding-id",
            "7",
            "--max-candidates",
            "1",
            "--max-llm-calls",
            "1",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    plan = json.loads(result.stdout)
    assert plan["schema_version"] == "skeinrank.openrouter_live_pilot_plan.v1"
    assert plan["openrouter_calls"] is False
    assert plan["skeinrank_api_calls"] is False
    assert plan["profile_name"] == "platform_ops_benchmark"
    assert plan["binding_id"] == 7
    assert plan["pilot_config"]["validate_with_skeinrank"] is True
    assert plan["pilot_config"]["submit_proposals"] is False
    assert plan["validated_pilot"] == {
        "schema_version": "skeinrank.openrouter_validated_pilot_plan.v1",
        "enabled": True,
        "mode": "validate_only",
        "requires_skeinrank_api": True,
        "submit_proposals": False,
        "runtime_mutation_enabled": False,
    }


def test_49d_validated_pilot_report_contains_validation_diagnostics() -> None:
    _, config, failed_queries = _load_inputs()
    live_pilot = _load_module(
        "agent_live_pilot_49d_validate", AGENT_DIR / "live_pilot.py"
    )
    client_module = _load_module(
        "agent_openrouter_client_49d_validate", AGENT_DIR / "openrouter_client.py"
    )
    openrouter_client = client_module.OpenRouterClient(
        api_key="test-key",
        transport=lambda method, path, payload: _mock_openrouter_response("propose"),
    )
    skeinrank_client = _ValidationClient()

    report = live_pilot.run_openrouter_live_pilot(
        failed_queries=failed_queries,
        evidence_records_path=config.evidence_records_path,
        openrouter_client=openrouter_client,
        pilot_config=live_pilot.OpenRouterLivePilotConfig(
            max_candidates=1,
            max_llm_calls=1,
            max_proposals=1,
            validate_with_skeinrank=True,
            submit_proposals=False,
        ),
        candidate_config=config.candidate_discovery,
        evidence_config=config.evidence_sampler,
        demo_config=config.demo_report,
        canonical_hints_config=config.canonical_hints,
        submission_config=config.proposal_submission,
        security_config=config.security_profile,
        skeinrank_client=skeinrank_client,
        openrouter_model=config.openrouter_model,
        profile_name="platform_ops_benchmark",
        proposal_source_name=config.proposal_source_name,
    )

    validated = report["validated_pilot"]
    assert validated["schema_version"] == "skeinrank.openrouter_validated_pilot.v1"
    assert validated["enabled"] is True
    assert validated["mode"] == "validate_only"
    assert validated["validated"] is True
    assert validated["metrics"]["live_openrouter_calls"] == 1
    assert validated["metrics"]["validation_passed"] == 1
    assert validated["metrics"]["validation_coverage"] == 1.0
    assert validated["metrics"]["errors"] == 0
    assert validated["metrics"]["submitted"] == 0
    assert validated["safety"]["runtime_mutation_enabled"] is False
    assert [gate["status"] for gate in validated["quality_gates"]] == [
        "passed",
        "passed",
        "passed",
        "passed",
        "passed",
    ]
    assert validated["aliases"][0]["alias"] == "pg"
    assert validated["aliases"][0]["validation_status"] == "passed"


def test_49d_makefile_exposes_validated_pilot_targets() -> None:
    makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")

    for target in (
        "benchmark-agent-live-validated-pilot-plan:",
        "benchmark-agent-live-validated-pilot:",
        "benchmark-agent-live-validated-pilot-report:",
        "benchmark-agent-live-validated-pilot-stack:",
        "agent-openrouter-validated-pilot-plan:",
        "agent-openrouter-validated-pilot-report:",
    ):
        assert target in makefile

    assert "OPENROUTER_VALIDATED_PILOT_PROFILE ?= platform_ops_benchmark" in makefile
    assert "--print-openrouter-validated-pilot-plan" in makefile
    assert "--write-openrouter-validated-pilot-report" in makefile
    assert "--profile-name $(OPENROUTER_VALIDATED_PILOT_PROFILE)" in makefile
    assert (
        "benchmark-stack-up benchmark-stack-wait benchmark-stack-reset "
        "benchmark-stack-seed"
    ) in makefile
    assert "benchmark-stack-auth-token:" in makefile
    assert (
        'SKEINRANK_AGENT_API_TOKEN="$$( $(MAKE) --no-print-directory '
        'benchmark-stack-auth-token )"'
    ) in makefile


def test_49d_validation_preflight_checks_auth_tools_before_openrouter() -> None:
    runner = _load_module(
        "agent_run_alias_scout_49d_auth_preflight",
        AGENT_DIR / "run_alias_scout.py",
    )
    config = runner.AgentRunnerConfig.from_file(AGENT_DIR / "agent_config.example.json")

    calls: list[tuple[str, str, dict[str, Any] | None]] = []

    def transport(method: str, path: str, payload: dict[str, Any] | None) -> Any:
        calls.append((method, path, payload))
        if path == "/livez":
            return {"status": "ok"}
        raise runner.SkeinRankAgentApiError(401, {"detail": "Missing bearer token"})

    client = runner.SkeinRankAgentClient(
        base_url="http://127.0.0.1:8010",
        api_token=None,
        transport=transport,
    )

    try:
        runner._preflight_skeinrank_api_for_live_pilot(client, config)
    except RuntimeError as exc:
        message = str(exc)
    else:  # pragma: no cover - assertion guard.
        raise AssertionError(
            "preflight should fail without an authenticated tools call"
        )

    assert "validation preflight failed before the OpenRouter call" in message
    assert "SKEINRANK_AGENT_API_TOKEN" in message
    assert [call[1] for call in calls] == [
        "/livez",
        "/v1/tools/bindings?enabled_only=true&profile_name=infra_incidents",
    ]


def test_53a1_validation_preflight_checks_validate_alias_context_before_openrouter() -> (
    None
):
    runner = _load_module(
        "agent_run_alias_scout_53a1_validate_alias_preflight",
        AGENT_DIR / "run_alias_scout.py",
    )
    config = runner.AgentRunnerConfig.from_file(AGENT_DIR / "agent_config.example.json")

    calls: list[tuple[str, str, dict[str, Any] | None]] = []

    def transport(method: str, path: str, payload: dict[str, Any] | None) -> Any:
        calls.append((method, path, payload))
        if path == "/livez":
            return {"status": "ok"}
        if path.startswith("/v1/tools/bindings"):
            return []
        if path == "/v1/tools/validate-alias":
            return {
                "validation_summary": {
                    "status": "warning",
                    "checks": {"canonical_state": {"status": "warning"}},
                }
            }
        raise AssertionError(f"unexpected path: {path}")

    client = runner.SkeinRankAgentClient(
        base_url="http://127.0.0.1:8010",
        api_token=None,
        transport=transport,
    )

    runner._preflight_skeinrank_api_for_live_pilot(
        client,
        config,
        profile_name="infra_incidents",
        binding_id=None,
        proposal_source_name="openrouter-alias-scout",
    )

    assert [call[1] for call in calls] == [
        "/livez",
        "/v1/tools/bindings?enabled_only=true&profile_name=infra_incidents",
        "/v1/tools/validate-alias",
    ]
    validate_payload = calls[2][2]
    assert validate_payload is not None
    assert validate_payload["profile_name"] == "infra_incidents"
    assert validate_payload["canonical_value"] == "skeinrank_preflight_canonical"
    assert validate_payload["alias_value"] == "skeinrank_preflight_alias"
    assert validate_payload["source_payload"]["preflight"] is True


def test_53a1_validation_preflight_reports_missing_profile_before_openrouter() -> None:
    runner = _load_module(
        "agent_run_alias_scout_53a1_missing_profile_preflight",
        AGENT_DIR / "run_alias_scout.py",
    )
    config = runner.AgentRunnerConfig.from_file(AGENT_DIR / "agent_config.example.json")

    calls: list[tuple[str, str, dict[str, Any] | None]] = []

    def transport(method: str, path: str, payload: dict[str, Any] | None) -> Any:
        calls.append((method, path, payload))
        if path == "/livez":
            return {"status": "ok"}
        if path.startswith("/v1/tools/bindings"):
            return []
        if path == "/v1/tools/validate-alias":
            raise runner.SkeinRankAgentApiError(
                404, {"detail": "Profile not found: infra_incidents"}
            )
        raise AssertionError(f"unexpected path: {path}")

    client = runner.SkeinRankAgentClient(
        base_url="http://127.0.0.1:8010",
        api_token=None,
        transport=transport,
    )

    try:
        runner._preflight_skeinrank_api_for_live_pilot(
            client,
            config,
            profile_name="infra_incidents",
            binding_id=None,
            proposal_source_name="openrouter-alias-scout",
        )
    except RuntimeError as exc:
        message = str(exc)
    else:  # pragma: no cover - assertion guard.
        raise AssertionError("preflight should fail when profile context is missing")

    assert "validation context was not found" in message
    assert "Seed the benchmark stack first" in message
    assert "Profile: 'infra_incidents'" in message
    assert [call[1] for call in calls] == [
        "/livez",
        "/v1/tools/bindings?enabled_only=true&profile_name=infra_incidents",
        "/v1/tools/validate-alias",
    ]
