from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
AGENT_DIR = REPO_ROOT / "examples" / "agents" / "openrouter_alias_scout"

_PATCH_ERA_PATTERN = re.compile(
    r"\bPatch\b|\bpatch\b|patch-era|later patches|future patches|"
    r"\b4[0-9][A-Z]\b|\b5[0-9][A-Z]\b"
)


def _load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    sys.path.insert(0, str(AGENT_DIR))
    try:
        spec.loader.exec_module(module)
    finally:
        try:
            sys.path.remove(str(AGENT_DIR))
        except ValueError:
            pass
    return module


def test_alias_scout_example_text_is_productized() -> None:
    checked_suffixes = {".py", ".md", ".json", ".jsonl", ".example"}
    for path in sorted(AGENT_DIR.rglob("*")):
        if not path.is_file() or path.suffix not in checked_suffixes:
            continue
        content = path.read_text(encoding="utf-8")
        assert not _PATCH_ERA_PATTERN.search(content), path


def test_report_helpers_use_workflow_not_internal_milestone_key() -> None:
    docker_demo = _load_module(
        "agent_docker_demo_productized", AGENT_DIR / "docker_demo_scenario.py"
    )
    dictionary = _load_module(
        "agent_dictionary_quickstart_productized",
        AGENT_DIR / "dictionary_quickstart.py",
    )
    runtime = _load_module(
        "agent_runtime_smoke_productized", AGENT_DIR / "runtime_api_smoke.py"
    )
    real_es = _load_module(
        "agent_real_es_validation_productized", AGENT_DIR / "real_es_validation.py"
    )
    es_source = _load_module(
        "agent_es_source_productized", AGENT_DIR / "elasticsearch_source.py"
    )

    reports = [
        docker_demo.build_docker_full_demo_plan(docker_demo.DockerFullDemoConfig()),
        dictionary.build_dictionary_quickstart_plan(
            dictionary.DictionaryQuickstartConfig(
                artifacts_dir=Path("/tmp/dictionary-quickstart")
            )
        ),
        runtime.build_runtime_api_smoke_plan(
            runtime.RuntimeApiSmokeConfig(artifacts_dir=Path("/tmp/runtime-api-smoke"))
        ),
        real_es.RealElasticsearchValidationConfig(
            artifacts_dir=Path("/tmp/real-es-validation")
        ).to_plan(source_config=es_source.ElasticsearchSourceConfig()),
    ]

    expected_workflows = {
        "docker_compose_full_demo",
        "dictionary_quickstart",
        "runtime_api_smoke",
        "real_elasticsearch_validation",
    }
    assert {report["workflow"] for report in reports} == expected_workflows
    assert all("patch" not in report for report in reports)
