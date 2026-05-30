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


def test_security_profile_files_exist_and_are_documented() -> None:
    assert (AGENT_DIR / "security_profile.py").exists()

    readme = (AGENT_DIR / "README.md").read_text(encoding="utf-8")
    for fragment in (
        "Patch 40L adds the service-account security profile",
        "--print-security-profile",
        "skeinrank.agent_security_profile.v1",
        "proposal submission remains disabled",
    ):
        assert fragment in readme


def test_security_profile_report_is_redacted_and_safe_by_default(
    monkeypatch: Any,
) -> None:
    runner = _load_module("agent_run_alias_scout_40l", AGENT_DIR / "run_alias_scout.py")

    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-secret-openrouter")
    monkeypatch.setenv("SKEINRANK_AGENT_API_TOKEN", "sk-sr-secret-token")

    config = runner.AgentRunnerConfig.from_file(AGENT_DIR / "agent_config.example.json")
    report = runner.build_security_report_for_config(config)

    assert report["schema_version"] == "skeinrank.agent_security_profile.v1"
    assert report["status"] == "ok"
    assert report["roles"]["role_allowed"] is True
    assert report["proposal_submission"]["configured_in_llm_review"] is False
    assert report["proposal_submission"]["will_submit_proposals"] is False
    assert report["runtime_mutation"]["agent_may_mutate_runtime"] is False
    assert report["auth"]["openrouter_api_key"]["configured"] is True
    assert report["auth"]["skeinrank_api_token"]["configured"] is True

    serialized = json.dumps(report)
    assert "sk-or-v1-secret-openrouter" not in serialized
    assert "sk-sr-secret-token" not in serialized
    assert "sk-o...uter" in serialized
    assert "sk-s...oken" in serialized


def test_security_profile_blocks_submit_proposals_without_policy(
    tmp_path: Path,
) -> None:
    config = json.loads((AGENT_DIR / "agent_config.example.json").read_text())
    config["llm_review"]["submit_proposals"] = True
    path = tmp_path / "unsafe-agent-config.json"
    path.write_text(json.dumps(config), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(AGENT_DIR / "run_alias_scout.py"),
            "--config",
            str(path),
            "--check-security-profile",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    report = json.loads(result.stdout)
    assert report["status"] == "error"
    assert any(
        finding["code"] == "proposal_submission_blocked_by_policy"
        for finding in report["findings"]
    )


def test_security_profile_cli_prints_sanitized_report(monkeypatch: Any) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-test-secret")
    result = subprocess.run(
        [
            sys.executable,
            str(AGENT_DIR / "run_alias_scout.py"),
            "--config",
            str(AGENT_DIR / "agent_config.example.json"),
            "--print-security-profile",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    report = json.loads(result.stdout)
    assert report["schema_version"] == "skeinrank.agent_security_profile.v1"
    assert report["status"] == "ok"
    assert report["auth"]["openrouter_api_key"]["configured"] is True
    assert "sk-or-v1-test-secret" not in result.stdout
    assert "POST /v1/tools/suggest-alias" in report["allowed_skeinrank_tool_paths"]


def test_security_assert_rejects_runtime_mutation() -> None:
    security = _load_module(
        "agent_security_profile_40l", AGENT_DIR / "security_profile.py"
    )

    cfg = security.SecurityProfileConfig.from_mapping(
        {
            "allow_runtime_mutation": True,
        }
    )
    try:
        security.assert_security_allows_llm_review(
            security_config=cfg,
            skeinrank_role="contributor",
            api_token_env=None,
            llm_submit_proposals=False,
        )
    except RuntimeError as exc:
        assert "runtime mutation" in str(exc)
    else:  # pragma: no cover - defensive assertion branch
        raise AssertionError("runtime mutation should be rejected")


def test_security_profile_docs_are_linked() -> None:
    paths = [
        REPO_ROOT / "docs" / "README.md",
        REPO_ROOT / "docs" / "api" / "governance-api.md",
        REPO_ROOT / "packages" / "skeinrank-governance-api" / "README.md",
        REPO_ROOT / "docs" / "guides" / "openrouter-agent.md",
    ]
    for path in paths:
        content = path.read_text(encoding="utf-8")
        assert "Patch 40L" in content, path
        assert "--print-security-profile" in content, path
