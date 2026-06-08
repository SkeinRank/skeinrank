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


class FakeQuickstartClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any] | None]] = []

    def request(
        self, method: str, path: str, payload: dict[str, Any] | None = None
    ) -> Any:
        self.calls.append((method, path, payload))
        if path == "/v1/console/dictionary/validate":
            return {"status": "valid", "summary": {"terms_total": 4}}
        if path == "/v1/console/dictionary/import":
            return {"status": "applied", "summary": {"created_terms": 4}}
        if path == "/v1/governance/elasticsearch/bindings":
            return {
                "id": 42,
                "name": payload["name"],
                "index_name": payload["index_name"],
            }
        if path.startswith("/v1/headless/snapshots/export?"):
            return {
                "schema_version": "skeinrank.runtime_snapshot_artifact.v1",
                "binding_id": 42,
                "source": "latest",
            }
        raise AssertionError(f"Unexpected request: {method} {path}")


def test_dictionary_quickstart_plan_is_safe_and_uses_existing_endpoints() -> None:
    module = _load_module(
        "agent_dictionary_quickstart", AGENT_DIR / "dictionary_quickstart.py"
    )
    config = module.DictionaryQuickstartConfig(artifacts_dir=Path("/tmp/quickstart"))
    plan = module.build_dictionary_quickstart_plan(config)

    assert plan["schema_version"] == "skeinrank.agent_dictionary_quickstart_plan.v1"
    assert plan["workflow"] == "dictionary_quickstart"
    assert "patch" not in plan
    assert "POST /v1/console/dictionary/validate" in plan["api_flow"]
    assert (
        "POST /v1/governance/elasticsearch/bindings (explicit flag only)"
        in plan["api_flow"]
    )
    assert plan["safe_defaults"]["network_calls_in_plan"] is False
    assert plan["safe_defaults"]["runtime_mutation_enabled"] is False
    assert plan["safe_defaults"]["snapshot_publish_enabled"] is False


def test_dictionary_and_binding_payloads_match_console_and_binding_shapes(
    tmp_path: Path,
) -> None:
    module = _load_module(
        "agent_dictionary_quickstart_payloads", AGENT_DIR / "dictionary_quickstart.py"
    )
    config = module.DictionaryQuickstartConfig(artifacts_dir=tmp_path)
    report = module.write_dictionary_quickstart_payloads(config)

    assert Path(report["dictionary_payload_path"]).exists()
    assert Path(report["binding_payload_path"]).exists()
    dictionary = json.loads(Path(report["dictionary_payload_path"]).read_text())
    binding = json.loads(Path(report["binding_payload_path"]).read_text())

    assert dictionary["schema_version"] == "skeinrank.dictionary.v1"
    assert dictionary["profile_name"] == "infra_incidents"
    assert len(dictionary["terms"]) == 4
    assert {term["canonical_value"] for term in dictionary["terms"]} >= {
        "kubernetes",
        "postgresql",
    }
    assert binding == {
        "name": "infra-incidents-demo",
        "profile_name": "infra_incidents",
        "description": "Demo Elasticsearch binding for infra incidents.",
        "index_name": "skeinrank_agent_demo",
        "text_fields": ["title", "text", "query"],
        "target_field": "skeinrank.canonical_terms",
        "mode": "dry_run",
        "write_strategy": "reindex_alias_swap",
        "is_enabled": True,
    }


def test_quickstart_validate_only_calls_validate_endpoint_only(tmp_path: Path) -> None:
    module = _load_module(
        "agent_dictionary_quickstart_validate", AGENT_DIR / "dictionary_quickstart.py"
    )
    client = FakeQuickstartClient()
    report = module.run_dictionary_quickstart(
        config=module.DictionaryQuickstartConfig(artifacts_dir=tmp_path),
        client=client,
    )

    assert report["summary"]["dictionary_validated"] is True
    assert report["summary"]["dictionary_imported"] is False
    assert report["summary"]["binding_created"] is False
    assert report["summary"]["snapshot_exported"] is False
    assert [call[1] for call in client.calls] == ["/v1/console/dictionary/validate"]


def test_quickstart_apply_binding_and_snapshot_export_use_existing_paths(
    tmp_path: Path,
) -> None:
    module = _load_module(
        "agent_dictionary_quickstart_apply", AGENT_DIR / "dictionary_quickstart.py"
    )
    client = FakeQuickstartClient()
    report = module.run_dictionary_quickstart(
        config=module.DictionaryQuickstartConfig(artifacts_dir=tmp_path),
        client=client,
        apply_import=True,
        create_binding=True,
        export_snapshot=True,
    )

    assert report["binding_id"] == 42
    assert report["summary"]["dictionary_imported"] is True
    assert report["summary"]["binding_created"] is True
    assert report["summary"]["snapshot_exported"] is True
    paths = [call[1] for call in client.calls]
    assert paths[0] == "/v1/console/dictionary/validate"
    assert paths[1] == "/v1/console/dictionary/import"
    assert paths[2] == "/v1/governance/elasticsearch/bindings"
    assert paths[3].startswith("/v1/headless/snapshots/export?")
    assert (tmp_path / "snapshot.artifact.json").exists()


def test_cli_print_and_write_payload_commands_work(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(AGENT_DIR / "run_alias_scout.py"),
            "--config",
            str(AGENT_DIR / "agent_config.example.json"),
            "--print-dictionary-quickstart-plan",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    plan = json.loads(result.stdout)
    assert plan["schema_version"] == "skeinrank.agent_dictionary_quickstart_plan.v1"

    result = subprocess.run(
        [
            sys.executable,
            str(AGENT_DIR / "run_alias_scout.py"),
            "--config",
            str(AGENT_DIR / "agent_config.example.json"),
            "--write-dictionary-quickstart-payloads",
            "--dictionary-quickstart-artifacts-dir",
            str(tmp_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload_report = json.loads(result.stdout)
    assert (
        payload_report["schema_version"]
        == "skeinrank.agent_dictionary_quickstart_payloads.v1"
    )
    assert (tmp_path / "dictionary.payload.json").exists()
    assert (tmp_path / "binding.payload.json").exists()


def test_docs_mention_42e_quickstart() -> None:
    for path in (
        REPO_ROOT / "docs" / "guides" / "openrouter-agent.md",
        AGENT_DIR / "README.md",
    ):
        content = path.read_text(encoding="utf-8")
        assert "--print-dictionary-quickstart-plan" in content, path
        assert "--write-dictionary-quickstart-payloads" in content, path

    docs_index = (REPO_ROOT / "docs" / "README.md").read_text(encoding="utf-8")
    assert "guides/openrouter-agent.md" in docs_index
