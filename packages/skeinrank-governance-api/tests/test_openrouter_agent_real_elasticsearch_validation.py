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
    sys.path.insert(0, str(AGENT_DIR))
    try:
        spec.loader.exec_module(module)
    finally:
        try:
            sys.path.remove(str(AGENT_DIR))
        except ValueError:
            pass
    return module


class FakeScenarioTransport:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, Any]] = []
        self.docs = {
            "pg": {
                "_id": "es-doc-001",
                "_index": "skeinrank-agent-evidence",
                "_score": 10.0,
                "_source": {
                    "id": "es-doc-001",
                    "title": "PostgreSQL failover runbook",
                    "text": "pg timeout during PostgreSQL failover and postgres pool recovery",
                },
            },
            "k8s": {
                "_id": "es-doc-002",
                "_index": "skeinrank-agent-evidence",
                "_score": 9.0,
                "_source": {
                    "id": "es-doc-002",
                    "title": "Kubernetes rollout incident",
                    "text": "k8s rollout failed and Kubernetes deployment recovered",
                },
            },
            "kube": {
                "_id": "es-doc-003",
                "_index": "skeinrank-agent-evidence",
                "_score": 8.0,
                "_source": {
                    "id": "es-doc-003",
                    "title": "Kube DNS troubleshooting",
                    "text": "kube dns incident in Kubernetes cluster and k8s endpoints",
                },
            },
        }

    def __call__(self, method: str, path: str, payload: Any) -> dict[str, Any]:
        self.calls.append((method, path, payload))
        if path.endswith("/_search"):
            query = payload["query"]["multi_match"]["query"]
            hit = self.docs.get(query)
            return {"hits": {"hits": [hit] if hit else []}}
        return {"acknowledged": True, "errors": False}


def test_real_elasticsearch_validation_files_are_present_and_documented() -> None:
    assert (AGENT_DIR / "real_es_validation.py").exists()
    assert (AGENT_DIR / "real_es_validation" / "documents.jsonl").exists()
    readme = (AGENT_DIR / "README.md").read_text(encoding="utf-8")
    guide = (REPO_ROOT / "docs" / "guides" / "openrouter-agent.md").read_text(
        encoding="utf-8"
    )
    for content in (readme, guide):
        assert "Patch 42B" in content
        assert "--print-real-elasticsearch-validation-plan" in content
        assert "--run-real-elasticsearch-validation" in content


def test_fixture_generation_writes_bulk_and_mapping(tmp_path: Path) -> None:
    module = _load_module(
        "agent_real_es_validation", AGENT_DIR / "real_es_validation.py"
    )
    es = _load_module(
        "agent_es_source_for_real_validation", AGENT_DIR / "elasticsearch_source.py"
    )
    config = module.RealElasticsearchValidationConfig(artifacts_dir=tmp_path)
    report = module.write_real_elasticsearch_validation_fixtures(
        config,
        source_config=es.ElasticsearchSourceConfig(index="validation-index"),
    )

    assert report["schema_version"] == (
        "skeinrank.agent_real_elasticsearch_validation_fixtures.v1"
    )
    assert report["documents_written"] == 4
    assert config.docs_path.exists()
    assert config.bulk_path.exists()
    bulk = config.bulk_path.read_text(encoding="utf-8")
    assert '"_index": "validation-index"' in bulk
    assert "es-doc-001" in bulk


def test_indexing_uses_explicit_mutating_es_calls(tmp_path: Path) -> None:
    module = _load_module(
        "agent_real_es_validation_index", AGENT_DIR / "real_es_validation.py"
    )
    es = _load_module(
        "agent_es_source_for_real_validation_index",
        AGENT_DIR / "elasticsearch_source.py",
    )
    config = module.RealElasticsearchValidationConfig(
        artifacts_dir=tmp_path, reset_index=True
    )
    source_config = es.ElasticsearchSourceConfig(index="validation-index")
    module.write_real_elasticsearch_validation_fixtures(
        config, source_config=source_config
    )
    transport = FakeScenarioTransport()
    client = es.ElasticsearchSourceClient(source_config, transport=transport)

    report = module.index_real_elasticsearch_validation_docs(
        config=config, source_config=source_config, client=client
    )

    assert report["schema_version"] == (
        "skeinrank.agent_real_elasticsearch_validation_indexing.v1"
    )
    assert report["documents_indexed"] == 4
    assert report["mutating_elasticsearch_calls"] is True
    assert [call[0] for call in transport.calls] == ["DELETE", "PUT", "POST", "POST"]
    assert transport.calls[2][1] == "/_bulk"


def test_readonly_real_es_validation_uses_fake_transport(tmp_path: Path) -> None:
    module = _load_module(
        "agent_real_es_validation_run", AGENT_DIR / "real_es_validation.py"
    )
    es = _load_module(
        "agent_es_source_for_real_validation_run", AGENT_DIR / "elasticsearch_source.py"
    )
    discovery = _load_module(
        "agent_discovery_for_real_validation", AGENT_DIR / "candidate_discovery.py"
    )
    sampler = _load_module(
        "agent_sampler_for_real_validation", AGENT_DIR / "evidence_sampler.py"
    )
    config = module.RealElasticsearchValidationConfig(
        artifacts_dir=tmp_path, max_candidates=3
    )
    source_config = es.ElasticsearchSourceConfig(
        index="skeinrank-agent-evidence", text_fields=("title", "text")
    )
    module.write_real_elasticsearch_validation_fixtures(
        config, source_config=source_config
    )
    transport = FakeScenarioTransport()
    report = module.run_real_elasticsearch_validation_scenario(
        config=config,
        source_config=source_config,
        evidence_config=sampler.EvidenceSamplerConfig(text_fields=("title", "text")),
        candidate_config=discovery.CandidateDiscoveryConfig(
            max_candidates=10,
            noise_tokens=("queue", "pod", "dns", "timeout", "failover"),
        ),
        client=es.ElasticsearchSourceClient(source_config, transport=transport),
        profile_name="infra_incidents",
    )

    assert report["schema_version"] == (
        "skeinrank.agent_real_elasticsearch_validation_report.v1"
    )
    assert report["mutating_elasticsearch_calls"] is False
    assert report["openrouter_calls"] is False
    assert report["candidate_summary"]["expected_aliases_found"] == [
        "k8s",
        "kube",
        "pg",
    ]
    assert report["evidence_quality"]["evidence_coverage"] >= 0.75
    assert all(
        call[0] == "POST" and call[1].endswith("/_search") for call in transport.calls
    )


def test_cli_print_real_elasticsearch_validation_plan_outputs_json() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(AGENT_DIR / "run_alias_scout.py"),
            "--config",
            str(AGENT_DIR / "agent_config.example.json"),
            "--print-real-elasticsearch-validation-plan",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)

    assert payload["schema_version"] == (
        "skeinrank.agent_real_elasticsearch_validation_plan.v1"
    )
    assert payload["safe_defaults"]["indexing_requires_explicit_flag"] is True
    assert payload["safe_defaults"]["sample_evidence_readonly"] is True


def test_cli_write_real_elasticsearch_validation_fixtures(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(AGENT_DIR / "run_alias_scout.py"),
            "--config",
            str(AGENT_DIR / "agent_config.example.json"),
            "--write-real-elasticsearch-validation-fixtures",
            "--real-es-validation-artifacts-dir",
            str(tmp_path),
            "--elasticsearch-index",
            "validation-index",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)

    assert payload["documents_written"] == 4
    assert payload["index"] == "validation-index"
    assert (tmp_path / "documents.jsonl").exists()
    assert (tmp_path / "documents.bulk.ndjson").exists()
