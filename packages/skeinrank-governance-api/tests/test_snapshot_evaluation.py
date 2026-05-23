from __future__ import annotations

import json

import pytest
from skeinrank_governance_api.runtime_snapshots import (
    runtime_snapshot_artifact_checksum,
)
from skeinrank_governance_api.snapshot_evaluation import (
    evaluate_runtime_snapshot_artifacts,
    load_evaluation_queries,
)


def _artifact(version: str, entries: list[dict]) -> dict:
    payload = {
        "schema_version": "skeinrank.runtime_snapshot_artifact.v1",
        "artifact_type": "runtime_snapshot",
        "binding": {
            "id": 7,
            "name": "platform knowledge base",
            "index_name": "platform_kb",
            "text_fields": ["title", "body"],
            "target_field": "skeinrank",
        },
        "profile": {"id": 3, "name": "platform_ops"},
        "runtime_snapshot": {
            "version": version,
            "checksum": f"runtime-{version}",
            "alias_entries": entries,
        },
    }
    payload["manifest"] = {
        "checksum": runtime_snapshot_artifact_checksum(payload),
        "runtime_checksum": f"runtime-{version}",
        "snapshot_source": "latest_profile",
        "snapshot_version": version,
        "alias_entries_total": len(entries),
    }
    return payload


def _entry(alias: str, canonical: str, slot: str, *, tags=None, confidence=1.0) -> dict:
    return {
        "alias_value": alias,
        "normalized_alias": alias.lower(),
        "canonical_value": canonical,
        "normalized_canonical": canonical.lower(),
        "slot": slot,
        "confidence": confidence,
        "tags": list(tags or []),
    }


def test_evaluate_runtime_snapshot_artifacts_reports_alias_and_query_changes(tmp_path):
    before_path = tmp_path / "before.json"
    after_path = tmp_path / "after.json"
    queries_path = tmp_path / "queries.jsonl"
    before_path.write_text(
        json.dumps(
            _artifact(
                "platform_ops@before",
                [
                    _entry("k8s", "kubernetes", "TOOL", tags=["infra"]),
                    _entry("pg", "page", "DOCUMENT_COMPONENT", tags=["docs"]),
                ],
            )
        ),
        encoding="utf-8",
    )
    after_path.write_text(
        json.dumps(
            _artifact(
                "platform_ops@after",
                [
                    _entry(
                        "k8s", "kubernetes", "TOOL", tags=["infra", "orchestration"]
                    ),
                    _entry("pg", "postgresql", "DATABASE", tags=["backend", "storage"]),
                    _entry(
                        "psql", "postgresql", "DATABASE", tags=["backend", "storage"]
                    ),
                ],
            )
        ),
        encoding="utf-8",
    )
    queries_path.write_text(
        '{"id":"q1","query":"pg timeout"}\n"k8s pod crash"\n',
        encoding="utf-8",
    )

    report = evaluate_runtime_snapshot_artifacts(
        before_path=before_path,
        after_path=after_path,
        queries_path=queries_path,
    )

    assert report["schema_version"] == "skeinrank.snapshot_evaluation.v1"
    assert report["before"]["snapshot_version"] == "platform_ops@before"
    assert report["after"]["snapshot_version"] == "platform_ops@after"
    assert report["aliases"]["added_total"] == 1
    assert report["aliases"]["changed_total"] == 2
    assert report["aliases"]["added"][0]["normalized_alias"] == "psql"
    changed = {item["normalized_alias"]: item for item in report["aliases"]["changed"]}
    assert changed["pg"]["before"]["canonical_value"] == "page"
    assert changed["pg"]["after"]["canonical_value"] == "postgresql"
    assert changed["k8s"]["after"]["tags"] == ["infra", "orchestration"]
    assert report["tags"]["added"] == ["backend", "orchestration", "storage"]
    assert report["queries"]["total"] == 2
    assert report["queries"]["changed_total"] == 2
    first_query_change = report["queries"]["changed"][0]
    assert first_query_change["query_id"] == "q1"
    assert first_query_change["before"]["canonical_query"] == "page timeout"
    assert first_query_change["after"]["canonical_query"] == "postgresql timeout"
    assert report["risk_summary"]["has_alias_changes"] is True
    assert report["risk_summary"]["has_query_changes"] is True


def test_load_evaluation_queries_accepts_json_list(tmp_path):
    path = tmp_path / "queries.json"
    path.write_text(
        json.dumps(["pg timeout", {"query_id": "q2", "query": "k8s crash"}]),
        encoding="utf-8",
    )

    queries = load_evaluation_queries(path)

    assert [item.query for item in queries] == ["pg timeout", "k8s crash"]
    assert queries[0].query_id is None
    assert queries[1].query_id == "q2"


def test_load_evaluation_queries_rejects_empty_query(tmp_path):
    path = tmp_path / "queries.json"
    path.write_text(json.dumps([{"query": ""}]), encoding="utf-8")

    with pytest.raises(ValueError, match="is empty"):
        load_evaluation_queries(path)
