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


class FakeElasticsearchTransport:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any] | None]] = []

    def __call__(
        self, method: str, path: str, payload: dict[str, Any] | None
    ) -> dict[str, Any]:
        self.calls.append((method, path, payload))
        query = payload["query"]["multi_match"]["query"] if payload else "unknown"
        return {
            "hits": {
                "hits": [
                    {
                        "_id": f"doc-{query}",
                        "_index": "incidents",
                        "_score": 12.5,
                        "_source": {
                            "title": f"{query} incident",
                            "text": (
                                f"Runbook evidence for {query} during production "
                                "incident."
                            ),
                        },
                    }
                ]
            }
        }


def test_elasticsearch_source_files_are_present_and_documented() -> None:
    assert (AGENT_DIR / "elasticsearch_source.py").exists()
    readme = (AGENT_DIR / "README.md").read_text(encoding="utf-8")
    guide = (REPO_ROOT / "docs" / "guides" / "openrouter-agent.md").read_text(
        encoding="utf-8"
    )
    for content in (readme, guide):
        assert "--print-elasticsearch-evidence-plan" in content
        assert "--print-elasticsearch-evidence-plan" in content
        assert "--sample-evidence-from-elasticsearch" in content


def test_elasticsearch_payload_and_hit_normalization_are_deterministic() -> None:
    module = _load_module(
        "agent_elasticsearch_source", AGENT_DIR / "elasticsearch_source.py"
    )

    payload = module.build_elasticsearch_search_payload(
        "k8s", text_fields=("title", "text"), size=3
    )
    assert payload["size"] == 3
    assert payload["query"]["multi_match"]["query"] == "k8s"
    assert payload["query"]["multi_match"]["fields"] == ["title", "text"]
    assert payload["_source"] is True

    records = module.elasticsearch_hits_to_records(
        {
            "hits": {
                "hits": [
                    {
                        "_id": "abc",
                        "_index": "docs",
                        "_score": 1.2,
                        "_source": {"title": "K8s guide", "text": "k8s rollout"},
                    }
                ]
            }
        },
        config=module.ElasticsearchSourceConfig(text_fields=("title", "text")),
    )
    assert records == [
        {
            "title": "K8s guide",
            "text": "k8s rollout",
            "id": "abc",
            "source_type": "elasticsearch",
            "index": "docs",
            "score": 1.2,
            "rank": 1,
        }
    ]


def test_elasticsearch_evidence_report_uses_fake_transport() -> None:
    discovery = _load_module(
        "agent_candidate_discovery_for_es", AGENT_DIR / "candidate_discovery.py"
    )
    es = _load_module(
        "agent_elasticsearch_source_report", AGENT_DIR / "elasticsearch_source.py"
    )
    sampler = _load_module(
        "agent_evidence_sampler_for_es", AGENT_DIR / "evidence_sampler.py"
    )

    candidate = discovery.AliasCandidate(
        surface="k8s",
        weighted_count=5.0,
        document_frequency=1,
        score=10.0,
        reasons=("mixed_alpha_digit",),
        example_queries=("k8s rollout",),
    )
    transport = FakeElasticsearchTransport()
    config = es.ElasticsearchSourceConfig(
        index="incidents", text_fields=("title", "text")
    )
    client = es.ElasticsearchSourceClient(config, transport=transport)

    report = es.build_elasticsearch_evidence_report(
        [candidate],
        client=client,
        source_config=config,
        evidence_config=sampler.EvidenceSamplerConfig(window_chars=40),
        profile_name="infra_incidents",
    )

    assert report["schema_version"] == (
        "skeinrank.agent_elasticsearch_evidence_sampling.v1"
    )
    assert report["elasticsearch_calls"] is True
    assert report["skeinrank_api_calls"] is False
    assert report["samples"][0]["candidate_alias"] == "k8s"
    assert report["samples"][0]["records_returned"] == 1
    assert report["samples"][0]["windows_found"] >= 1
    assert transport.calls[0][0] == "POST"
    assert transport.calls[0][1] == "/incidents/_search"


def test_cli_print_elasticsearch_evidence_plan_outputs_safe_json() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(AGENT_DIR / "run_alias_scout.py"),
            "--config",
            str(AGENT_DIR / "agent_config.example.json"),
            "--print-elasticsearch-evidence-plan",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)

    assert payload["schema_version"] == "skeinrank.agent_elasticsearch_evidence_plan.v1"
    assert payload["elasticsearch_calls"] is False
    assert payload["safety"]["readonly"] is True
    assert payload["index"] == "skeinrank-agent-evidence"


def test_cli_overrides_are_reflected_in_elasticsearch_plan() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(AGENT_DIR / "run_alias_scout.py"),
            "--config",
            str(AGENT_DIR / "agent_config.example.json"),
            "--print-elasticsearch-evidence-plan",
            "--elasticsearch-url",
            "http://localhost:9999",
            "--elasticsearch-index",
            "custom-index",
            "--elasticsearch-text-field",
            "title",
            "--elasticsearch-text-field",
            "body",
            "--elasticsearch-max-docs",
            "2",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)

    assert payload["url"] == "http://localhost:9999"
    assert payload["index"] == "custom-index"
    assert payload["text_fields"] == ["title", "body"]
    assert payload["max_docs_per_candidate"] == 2
