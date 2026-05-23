from __future__ import annotations

from fastapi.testclient import TestClient
from skeinrank_governance.models import ElasticsearchBinding
from skeinrank_governance_api import GovernanceApiConfig, create_app
from skeinrank_governance_api.runtime_snapshots import build_runtime_snapshot_payload
from sqlalchemy import select


def _client(tmp_path) -> TestClient:
    app = create_app(
        GovernanceApiConfig(
            database_url=f"sqlite:///{tmp_path / 'governance.db'}",
            create_tables_on_startup=True,
            service_version="test",
        )
    )
    return TestClient(app)


def _dictionary_payload() -> dict:
    return {
        "schema_version": "skeinrank.dictionary.v1",
        "profile_name": "platform_ops",
        "profile_description": "Platform operations terminology",
        "terms": [
            {
                "canonical_value": "kubernetes",
                "slot": "TOOL",
                "aliases": ["k8s", "kube"],
            },
            {
                "canonical_value": "postgresql",
                "slot": "DATABASE",
                "aliases": ["postgres", "pg"],
            },
        ],
    }


def _seed_binding(client: TestClient) -> int:
    apply_response = client.post(
        "/v1/headless/dictionaries/apply",
        json=_dictionary_payload(),
    )
    assert apply_response.status_code == 200, apply_response.text
    binding_response = client.post(
        "/v1/governance/elasticsearch/bindings",
        json={
            "name": "platform knowledge base",
            "profile_name": "platform_ops",
            "index_name": "platform_kb",
            "text_fields": ["title", "body"],
            "target_field": "skeinrank",
            "filter_field": "team",
            "filter_value": "platform",
            "mode": "write",
            "write_strategy": "reindex_alias_swap",
        },
    )
    assert binding_response.status_code == 201, binding_response.text
    return int(binding_response.json()["id"])


def test_headless_snapshot_artifact_export_builds_from_latest_profile(tmp_path):
    client = _client(tmp_path)
    binding_id = _seed_binding(client)

    response = client.get(
        "/v1/headless/snapshots/export",
        params={
            "binding_id": binding_id,
            "snapshot_version": "platform_ops@v1",
            "description": "Golden runtime snapshot",
        },
    )

    assert response.status_code == 200, response.text
    artifact = response.json()
    assert artifact["schema_version"] == "skeinrank.runtime_snapshot_artifact.v1"
    assert artifact["artifact_type"] == "runtime_snapshot"
    assert artifact["binding"]["id"] == binding_id
    assert artifact["binding"]["index_name"] == "platform_kb"
    assert artifact["binding"]["text_fields"] == ["title", "body"]
    assert artifact["binding"]["filter_field"] == "team"
    assert artifact["profile"]["name"] == "platform_ops"
    assert artifact["runtime_snapshot"]["version"] == "platform_ops@v1"
    assert artifact["runtime_snapshot"]["normalized_profile_name"] == "platform_ops"
    assert len(artifact["runtime_snapshot"]["alias_entries"]) == 4
    assert artifact["manifest"]["snapshot_source"] == "latest_profile"
    assert artifact["manifest"]["snapshot_version"] == "platform_ops@v1"
    assert artifact["manifest"]["alias_entries_total"] == 4
    assert artifact["manifest"]["description"] == "Golden runtime snapshot"
    assert len(artifact["manifest"]["checksum"]) == 64


def test_headless_snapshot_artifact_export_can_use_pinned_runtime_snapshot(tmp_path):
    client = _client(tmp_path)
    binding_id = _seed_binding(client)
    session_factory = client.app.state.governance_session_factory
    with session_factory() as session:
        binding = session.scalar(
            select(ElasticsearchBinding).where(ElasticsearchBinding.id == binding_id)
        )
        assert binding is not None
        snapshot_payload = build_runtime_snapshot_payload(
            session,
            binding.profile,
            snapshot_version="platform_ops@pinned",
        )
        binding.runtime_snapshot_json = snapshot_payload
        binding.last_successful_snapshot_version = "platform_ops@pinned"
        session.commit()

    response = client.get(
        "/v1/headless/snapshots/export",
        params={"binding_id": binding_id, "source": "runtime"},
    )

    assert response.status_code == 200, response.text
    artifact = response.json()
    assert artifact["manifest"]["snapshot_source"] == "binding_runtime_snapshot"
    assert artifact["manifest"]["snapshot_version"] == "platform_ops@pinned"
    assert artifact["runtime_snapshot"]["version"] == "platform_ops@pinned"


def test_headless_snapshot_artifact_runtime_source_requires_pinned_snapshot(tmp_path):
    client = _client(tmp_path)
    binding_id = _seed_binding(client)

    response = client.get(
        "/v1/headless/snapshots/export",
        params={"binding_id": binding_id, "source": "runtime"},
    )

    assert response.status_code == 409
    assert "no pinned runtime snapshot" in response.json()["detail"]
