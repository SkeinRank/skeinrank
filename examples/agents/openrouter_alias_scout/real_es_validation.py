"""Real Elasticsearch validation scenario for the OpenRouter alias scout.

Patch 42B provides a reproducible, operator-run scenario for validating the
agent against a real Elasticsearch/OpenSearch index. The module keeps all
network and mutating work explicit: fixture generation is offline, evidence
sampling is read-only, and indexing sample documents is only performed when the
operator calls the dedicated indexing command.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:  # pragma: no cover - import style depends on how the example is executed.
    from .candidate_discovery import CandidateDiscoveryConfig, discover_alias_candidates
    from .elasticsearch_source import (
        ElasticsearchSourceApiError,
        ElasticsearchSourceClient,
        ElasticsearchSourceConfig,
        build_elasticsearch_evidence_report,
    )
    from .evidence_sampler import EvidenceSamplerConfig
except ImportError:  # pragma: no cover
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from candidate_discovery import CandidateDiscoveryConfig, discover_alias_candidates
    from elasticsearch_source import (
        ElasticsearchSourceApiError,
        ElasticsearchSourceClient,
        ElasticsearchSourceConfig,
        build_elasticsearch_evidence_report,
    )
    from evidence_sampler import EvidenceSamplerConfig

JsonDict = dict[str, Any]

DEFAULT_SAMPLE_DOCUMENTS: tuple[JsonDict, ...] = (
    {
        "id": "es-doc-001",
        "title": "PostgreSQL failover runbook",
        "text": (
            "When pg connection pool is exhausted during PostgreSQL failover, "
            "check postgres primary health, inspect replicas, and restart the "
            "pool only after approval."
        ),
        "source_type": "runbook",
    },
    {
        "id": "es-doc-002",
        "title": "Kubernetes rollout incident",
        "text": (
            "The k8s rollout was stuck after a bad image tag. The kube worker "
            "recovered after pod eviction and Kubernetes deployment retry."
        ),
        "source_type": "incident",
    },
    {
        "id": "es-doc-003",
        "title": "Kube DNS troubleshooting",
        "text": (
            "Kube DNS failures can cause service discovery issues in "
            "Kubernetes clusters. Check CoreDNS logs and k8s service endpoints."
        ),
        "source_type": "runbook",
    },
    {
        "id": "es-doc-004",
        "title": "RabbitMQ queue incident",
        "text": (
            "RabbitMQ queue depth increased after worker restart. Consumers "
            "were stuck and messages accumulated in the queue."
        ),
        "source_type": "incident",
    },
)

DEFAULT_FAILED_QUERIES: tuple[JsonDict, ...] = (
    {"query": "pg timeout after failover", "count": 12, "source": "search_logs"},
    {"query": "k8s pod crashloop", "count": 9, "source": "search_logs"},
    {"query": "kube dns incident", "count": 7, "source": "search_logs"},
    {"query": "rabbit queue stuck", "count": 5, "source": "search_logs"},
)

DEFAULT_EXPECTED_OUTCOMES: tuple[JsonDict, ...] = (
    {
        "candidate_alias": "pg",
        "expected_action": "propose",
        "expected_canonical": "postgresql",
        "outcome": "accepted",
    },
    {
        "candidate_alias": "k8s",
        "expected_action": "propose",
        "expected_canonical": "kubernetes",
        "outcome": "accepted",
    },
    {
        "candidate_alias": "kube",
        "expected_action": "propose",
        "expected_canonical": "kubernetes",
        "outcome": "accepted",
    },
    {
        "candidate_alias": "queue",
        "expected_action": "reject",
        "outcome": "noisy",
    },
)


@dataclass(frozen=True)
class RealElasticsearchValidationConfig:
    """Settings for the Patch 42B real Elasticsearch validation scenario."""

    artifacts_dir: Path
    docs_filename: str = "documents.jsonl"
    failed_queries_filename: str = "failed_queries.jsonl"
    expected_outcomes_filename: str = "expected_outcomes.jsonl"
    bulk_filename: str = "documents.bulk.ndjson"
    index_mapping_filename: str = "index_mapping.json"
    max_candidates: int = 3
    reset_index: bool = False
    refresh_after_index: bool = True
    id_field: str = "id"
    run_id_prefix: str = "real-es-validation"

    @classmethod
    def from_mapping(
        cls, raw: Mapping[str, Any] | None, *, base_dir: Path
    ) -> "RealElasticsearchValidationConfig":
        """Create config from optional JSON config values."""

        raw = raw or {}
        artifacts_dir = Path(str(raw.get("artifacts_dir", "real_es_validation")))
        if not artifacts_dir.is_absolute():
            artifacts_dir = base_dir / artifacts_dir
        return cls(
            artifacts_dir=artifacts_dir,
            docs_filename=str(raw.get("docs_filename", cls.docs_filename)),
            failed_queries_filename=str(
                raw.get("failed_queries_filename", cls.failed_queries_filename)
            ),
            expected_outcomes_filename=str(
                raw.get("expected_outcomes_filename", cls.expected_outcomes_filename)
            ),
            bulk_filename=str(raw.get("bulk_filename", cls.bulk_filename)),
            index_mapping_filename=str(
                raw.get("index_mapping_filename", cls.index_mapping_filename)
            ),
            max_candidates=int(raw.get("max_candidates", cls.max_candidates)),
            reset_index=bool(raw.get("reset_index", cls.reset_index)),
            refresh_after_index=bool(
                raw.get("refresh_after_index", cls.refresh_after_index)
            ),
            id_field=str(raw.get("id_field", cls.id_field)),
            run_id_prefix=str(raw.get("run_id_prefix", cls.run_id_prefix)),
        )

    def with_overrides(
        self,
        *,
        artifacts_dir: Path | None = None,
        max_candidates: int | None = None,
        reset_index: bool | None = None,
    ) -> "RealElasticsearchValidationConfig":
        """Return a copy with CLI overrides applied."""

        return RealElasticsearchValidationConfig(
            artifacts_dir=artifacts_dir or self.artifacts_dir,
            docs_filename=self.docs_filename,
            failed_queries_filename=self.failed_queries_filename,
            expected_outcomes_filename=self.expected_outcomes_filename,
            bulk_filename=self.bulk_filename,
            index_mapping_filename=self.index_mapping_filename,
            max_candidates=max_candidates or self.max_candidates,
            reset_index=self.reset_index if reset_index is None else reset_index,
            refresh_after_index=self.refresh_after_index,
            id_field=self.id_field,
            run_id_prefix=self.run_id_prefix,
        )

    @property
    def docs_path(self) -> Path:
        return self.artifacts_dir / self.docs_filename

    @property
    def failed_queries_path(self) -> Path:
        return self.artifacts_dir / self.failed_queries_filename

    @property
    def expected_outcomes_path(self) -> Path:
        return self.artifacts_dir / self.expected_outcomes_filename

    @property
    def bulk_path(self) -> Path:
        return self.artifacts_dir / self.bulk_filename

    @property
    def index_mapping_path(self) -> Path:
        return self.artifacts_dir / self.index_mapping_filename

    def to_plan(self, *, source_config: ElasticsearchSourceConfig) -> JsonDict:
        """Return a network-free scenario plan."""

        return {
            "schema_version": "skeinrank.agent_real_elasticsearch_validation_plan.v1",
            "runner": "openrouter_alias_scout",
            "patch": "42B",
            "artifacts_dir": str(self.artifacts_dir),
            "fixtures": {
                "docs_path": str(self.docs_path),
                "failed_queries_path": str(self.failed_queries_path),
                "expected_outcomes_path": str(self.expected_outcomes_path),
                "bulk_path": str(self.bulk_path),
                "index_mapping_path": str(self.index_mapping_path),
            },
            "elasticsearch": {
                "url": source_config.url,
                "index": source_config.index,
                "text_fields": list(source_config.text_fields),
                "max_docs_per_candidate": source_config.max_docs_per_candidate,
            },
            "safe_defaults": {
                "fixture_generation_network_calls": False,
                "indexing_requires_explicit_flag": True,
                "sample_evidence_readonly": True,
                "openrouter_calls": False,
                "skeinrank_api_calls": False,
                "runtime_mutation_enabled": False,
                "snapshot_publish_enabled": False,
            },
            "commands": [
                "--write-real-elasticsearch-validation-fixtures",
                "--index-real-elasticsearch-validation-docs",
                "--run-real-elasticsearch-validation",
            ],
            "next_steps": [
                "Generate fixtures and inspect the JSONL documents.",
                "Index fixtures into an isolated local Elasticsearch index.",
                "Run the read-only validation scenario and inspect evidence coverage.",
            ],
        }


def write_real_elasticsearch_validation_fixtures(
    config: RealElasticsearchValidationConfig,
    *,
    source_config: ElasticsearchSourceConfig,
) -> JsonDict:
    """Write sample docs, failed queries, outcomes, mapping, and bulk NDJSON."""

    config.artifacts_dir.mkdir(parents=True, exist_ok=True)
    _write_jsonl(config.docs_path, DEFAULT_SAMPLE_DOCUMENTS)
    _write_jsonl(config.failed_queries_path, DEFAULT_FAILED_QUERIES)
    _write_jsonl(config.expected_outcomes_path, DEFAULT_EXPECTED_OUTCOMES)
    mapping = build_real_es_index_mapping(source_config.text_fields)
    config.index_mapping_path.write_text(
        json.dumps(mapping, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    config.bulk_path.write_text(
        build_bulk_ndjson(
            DEFAULT_SAMPLE_DOCUMENTS,
            index=source_config.index,
            id_field=config.id_field,
        ),
        encoding="utf-8",
    )
    return {
        "schema_version": "skeinrank.agent_real_elasticsearch_validation_fixtures.v1",
        "runner": "openrouter_alias_scout",
        "network_calls": False,
        "documents_written": len(DEFAULT_SAMPLE_DOCUMENTS),
        "failed_queries_written": len(DEFAULT_FAILED_QUERIES),
        "expected_outcomes_written": len(DEFAULT_EXPECTED_OUTCOMES),
        "paths": {
            "docs": str(config.docs_path),
            "failed_queries": str(config.failed_queries_path),
            "expected_outcomes": str(config.expected_outcomes_path),
            "bulk": str(config.bulk_path),
            "index_mapping": str(config.index_mapping_path),
        },
        "index": source_config.index,
    }


def index_real_elasticsearch_validation_docs(
    *,
    config: RealElasticsearchValidationConfig,
    source_config: ElasticsearchSourceConfig,
    client: ElasticsearchSourceClient,
) -> JsonDict:
    """Explicitly index the validation fixture documents into Elasticsearch."""

    docs = (
        load_jsonl(config.docs_path)
        if config.docs_path.exists()
        else list(DEFAULT_SAMPLE_DOCUMENTS)
    )
    mapping = build_real_es_index_mapping(source_config.text_fields)
    operations: list[JsonDict] = []

    if config.reset_index:
        try:
            client.request("DELETE", f"/{source_config.index}", None)
            operations.append(
                {"operation": "delete_index", "index": source_config.index}
            )
        except ElasticsearchSourceApiError as exc:
            if exc.status_code != 404:
                raise
            operations.append(
                {
                    "operation": "delete_index",
                    "index": source_config.index,
                    "status": "not_found",
                }
            )

    client.request("PUT", f"/{source_config.index}", mapping)
    operations.append({"operation": "put_index", "index": source_config.index})

    bulk_body = build_bulk_ndjson(
        docs, index=source_config.index, id_field=config.id_field
    )
    client.request("POST", "/_bulk", bulk_body)
    operations.append(
        {
            "operation": "bulk_index",
            "index": source_config.index,
            "documents": len(docs),
        }
    )

    if config.refresh_after_index:
        client.request("POST", f"/{source_config.index}/_refresh", None)
        operations.append({"operation": "refresh_index", "index": source_config.index})

    return {
        "schema_version": "skeinrank.agent_real_elasticsearch_validation_indexing.v1",
        "runner": "openrouter_alias_scout",
        "elasticsearch_calls": True,
        "mutating_elasticsearch_calls": True,
        "openrouter_calls": False,
        "skeinrank_api_calls": False,
        "runtime_mutation_enabled": False,
        "snapshot_publish_enabled": False,
        "index": source_config.index,
        "documents_indexed": len(docs),
        "operations": operations,
        "safety": {
            "isolated_validation_index_expected": True,
            "reset_index": config.reset_index,
            "direct_dictionary_write": False,
            "snapshot_publish": False,
        },
    }


def run_real_elasticsearch_validation_scenario(
    *,
    config: RealElasticsearchValidationConfig,
    source_config: ElasticsearchSourceConfig,
    evidence_config: EvidenceSamplerConfig,
    candidate_config: CandidateDiscoveryConfig,
    client: ElasticsearchSourceClient,
    binding_id: int | None = None,
    profile_name: str | None = None,
) -> JsonDict:
    """Run a read-only evidence scenario against a real Elasticsearch index."""

    failed_queries = (
        load_jsonl(config.failed_queries_path)
        if config.failed_queries_path.exists()
        else list(DEFAULT_FAILED_QUERIES)
    )
    expected_outcomes = (
        load_jsonl(config.expected_outcomes_path)
        if config.expected_outcomes_path.exists()
        else list(DEFAULT_EXPECTED_OUTCOMES)
    )
    candidates = discover_alias_candidates(failed_queries, config=candidate_config)
    scoped_candidates = candidates[: config.max_candidates]
    evidence_report = build_elasticsearch_evidence_report(
        scoped_candidates,
        client=client,
        source_config=source_config,
        evidence_config=evidence_config,
        binding_id=binding_id,
        profile_name=profile_name,
    )
    expected_aliases = {
        str(row.get("candidate_alias"))
        for row in expected_outcomes
        if row.get("candidate_alias")
    }
    candidate_aliases = {candidate.surface for candidate in scoped_candidates}
    samples_by_alias = {
        str(sample.get("candidate_alias")): sample
        for sample in evidence_report.get("samples", [])
        if isinstance(sample, Mapping)
    }
    aliases_with_evidence = {
        alias
        for alias, sample in samples_by_alias.items()
        if int(sample.get("windows_found", 0) or 0) > 0
    }
    expected_aliases_found = sorted(expected_aliases & candidate_aliases)
    expected_aliases_with_evidence = sorted(expected_aliases & aliases_with_evidence)
    missing_expected_aliases = sorted(expected_aliases - candidate_aliases)
    missing_expected_evidence = sorted(expected_aliases - aliases_with_evidence)
    errors = evidence_report.get("errors", [])
    status = "passed"
    reasons: list[str] = []
    if errors:
        status = "error"
        reasons.append("elasticsearch_evidence_errors")
    if missing_expected_aliases:
        status = "needs_review"
        reasons.append("missing_expected_aliases")
    if missing_expected_evidence:
        status = "needs_review"
        reasons.append("missing_expected_evidence")

    return {
        "schema_version": "skeinrank.agent_real_elasticsearch_validation_report.v1",
        "runner": "openrouter_alias_scout",
        "status": status,
        "reasons": reasons or ["expected_aliases_have_evidence"],
        "elasticsearch_calls": True,
        "mutating_elasticsearch_calls": False,
        "openrouter_calls": False,
        "skeinrank_api_calls": False,
        "runtime_mutation_enabled": False,
        "snapshot_publish_enabled": False,
        "input_summary": {
            "failed_queries_loaded": len(failed_queries),
            "expected_outcomes_loaded": len(expected_outcomes),
            "candidates_discovered": len(candidates),
            "candidates_evaluated": len(scoped_candidates),
        },
        "elasticsearch": {
            "url": source_config.url,
            "index": source_config.index,
            "text_fields": list(source_config.text_fields),
        },
        "candidate_summary": {
            "candidate_aliases": [candidate.surface for candidate in scoped_candidates],
            "expected_aliases": sorted(expected_aliases),
            "expected_aliases_found": expected_aliases_found,
            "missing_expected_aliases": missing_expected_aliases,
        },
        "evidence_quality": {
            "records_returned": evidence_report.get("records_returned", 0),
            "total_evidence_windows": evidence_report.get("total_evidence_windows", 0),
            "aliases_with_evidence": sorted(aliases_with_evidence),
            "expected_aliases_with_evidence": expected_aliases_with_evidence,
            "missing_expected_evidence": missing_expected_evidence,
            "evidence_coverage": _ratio(
                len(expected_aliases_with_evidence), len(expected_aliases)
            ),
        },
        "evidence_report": evidence_report,
        "quality_gate": {"status": status, "reasons": reasons or ["passed"]},
        "safety": {
            "readonly_evidence_sampling": True,
            "proposal_submission_enabled": False,
            "runtime_mutation_enabled": False,
            "snapshot_publish_enabled": False,
        },
    }


def build_real_es_index_mapping(text_fields: Sequence[str]) -> JsonDict:
    """Build a compact mapping for validation fixture documents."""

    properties: JsonDict = {
        "id": {"type": "keyword"},
        "source_type": {"type": "keyword"},
    }
    for field_name in text_fields:
        if field_name in {"id", "source_type"}:
            continue
        properties[field_name] = {"type": "text"}
    return {"mappings": {"properties": properties}}


def build_bulk_ndjson(
    docs: Sequence[Mapping[str, Any]], *, index: str, id_field: str = "id"
) -> str:
    """Build Elasticsearch bulk NDJSON for fixture documents."""

    lines: list[str] = []
    for doc in docs:
        doc_id = str(doc.get(id_field) or doc.get("id") or "")
        action: JsonDict = {"index": {"_index": index}}
        if doc_id:
            action["index"]["_id"] = doc_id
        lines.append(json.dumps(action, sort_keys=True))
        lines.append(json.dumps(dict(doc), sort_keys=True))
    return "\n".join(lines) + "\n"


def load_jsonl(path: Path) -> list[JsonDict]:
    """Load JSONL objects from a path."""

    rows: list[JsonDict] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), 1
    ):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"Expected JSON object at {path}:{line_number}")
        rows.append(value)
    return rows


def _write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(dict(row), sort_keys=True) + "\n")


def _ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)


__all__ = [
    "DEFAULT_EXPECTED_OUTCOMES",
    "DEFAULT_FAILED_QUERIES",
    "DEFAULT_SAMPLE_DOCUMENTS",
    "RealElasticsearchValidationConfig",
    "build_bulk_ndjson",
    "build_real_es_index_mapping",
    "index_real_elasticsearch_validation_docs",
    "load_jsonl",
    "run_real_elasticsearch_validation_scenario",
    "write_real_elasticsearch_validation_fixtures",
]
