from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
RUNBOOK = REPO_ROOT / "docs/deployment/blue-green-alias-swap-runbook.md"
DOCS_README = REPO_ROOT / "docs/README.md"
ROOT_README = REPO_ROOT / "README.md"
GOVERNANCE_API_README = REPO_ROOT / "packages/skeinrank-governance-api/README.md"
ENRICHMENT_DOC = REPO_ROOT / "docs/guides/elasticsearch-enrichment.md"
HARDENING_DOC = REPO_ROOT / "docs/guides/enrichment-beta-hardening.md"
API_DOC = REPO_ROOT / "docs/api/governance-api.md"
EXAMPLES_DIR = REPO_ROOT / "examples/blue-green-alias-swap"
PREFLIGHT_REQUEST = EXAMPLES_DIR / "preflight-request.json"
START_JOB_REQUEST = EXAMPLES_DIR / "start-job-request.json"
ROLLBACK_REQUEST = EXAMPLES_DIR / "rollback-request.json"
OPERATOR_CHECKLIST = EXAMPLES_DIR / "operator-checklist.md"
ROUTES = (
    REPO_ROOT
    / "packages/skeinrank-governance-api/skeinrank_governance_api/routes/governance.py"
)
SCHEMAS = (
    REPO_ROOT / "packages/skeinrank-governance-api/skeinrank_governance_api/schemas.py"
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_blue_green_alias_swap_runbook_is_discoverable() -> None:
    assert RUNBOOK.exists()
    assert (EXAMPLES_DIR / "README.md").exists()
    assert OPERATOR_CHECKLIST.exists()

    assert "docs/deployment/blue-green-alias-swap-runbook.md" in _read(ROOT_README)
    assert "examples/blue-green-alias-swap" in _read(ROOT_README)
    assert "deployment/blue-green-alias-swap-runbook.md" in _read(DOCS_README)
    assert "../examples/blue-green-alias-swap" in _read(DOCS_README)
    assert "docs/deployment/blue-green-alias-swap-runbook.md" in _read(
        GOVERNANCE_API_README
    )
    assert "../deployment/blue-green-alias-swap-runbook.md" in _read(ENRICHMENT_DOC)
    assert "../deployment/blue-green-alias-swap-runbook.md" in _read(HARDENING_DOC)
    assert "../deployment/blue-green-alias-swap-runbook.md" in _read(API_DOC)


def test_blue_green_alias_swap_runbook_documents_existing_api_surface() -> None:
    runbook = _read(RUNBOOK)
    routes = _read(ROUTES)
    schemas = _read(SCHEMAS)

    expected_fragments = (
        "reindex_alias_swap",
        "blue index",
        "green index",
        "serving alias",
        "GET  /v1/governance/elasticsearch/connection/status",
        "GET  /v1/governance/elasticsearch/indices",
        "GET  /v1/governance/elasticsearch/indices/{index_name}/mapping",
        "POST /v1/governance/elasticsearch/bindings/{binding_id}/dry-run",
        "POST /v1/governance/elasticsearch/bindings/{binding_id}/jobs/preflight",
        "POST /v1/governance/elasticsearch/bindings/{binding_id}/jobs",
        "GET  /v1/governance/elasticsearch/jobs?binding_id=...",
        "GET  /v1/governance/elasticsearch/jobs/{job_id}",
        "POST /v1/governance/elasticsearch/jobs/{job_id}/cancel",
        "POST /v1/governance/elasticsearch/jobs/{job_id}/rollback",
        "result_json.rollout",
        "previous_alias_indices",
        "new_alias_indices",
        "alias_swap_completed",
        "rollback_available",
        "rollback_candidate_index",
    )
    for fragment in expected_fragments:
        assert fragment in runbook

    route_fragments = (
        "/elasticsearch/connection/status",
        "/elasticsearch/indices",
        "/elasticsearch/indices/{index_name}/mapping",
        "/elasticsearch/bindings/{binding_id}/dry-run",
        "/elasticsearch/bindings/{binding_id}/jobs/preflight",
        "/elasticsearch/bindings/{binding_id}/jobs",
        "/elasticsearch/jobs",
        "/elasticsearch/jobs/{job_id}",
        "/elasticsearch/jobs/{job_id}/cancel",
        "/elasticsearch/jobs/{job_id}/rollback",
        "rollback_elasticsearch_enrichment_job",
        "cancel_elasticsearch_enrichment_job",
        "preflight_elasticsearch_enrichment_job",
    )
    for fragment in route_fragments:
        assert fragment in routes

    assert "ElasticsearchEnrichmentJobRollbackRequest" in schemas
    assert "ElasticsearchEnrichmentJobCreateRequest" in schemas

    forbidden_fragments = (
        "POST /v1/governance/elasticsearch/aliases/swap",
        "POST /v1/governance/elasticsearch/jobs/{job_id}/pause",
        "POST /v1/governance/elasticsearch/jobs/{job_id}/resume",
        "DELETE /v1/governance/elasticsearch/indices",
        "skeinrank-alias-swap",
        "skeinrank-enrichmentctl",
        "pause_elasticsearch_enrichment_job",
        "resume_elasticsearch_enrichment_job",
    )
    for fragment in forbidden_fragments:
        assert fragment not in runbook


def test_blue_green_alias_swap_examples_are_valid_and_safe() -> None:
    for path in (
        PREFLIGHT_REQUEST,
        START_JOB_REQUEST,
        ROLLBACK_REQUEST,
        OPERATOR_CHECKLIST,
    ):
        assert path.exists(), path

    preflight = json.loads(_read(PREFLIGHT_REQUEST))
    start_job = json.loads(_read(START_JOB_REQUEST))
    rollback = json.loads(_read(ROLLBACK_REQUEST))

    assert preflight == start_job
    assert preflight["alias_name"] == "platform_knowledge_base_search"
    assert preflight["target_index_name"].startswith(
        "platform_knowledge_base__skeinrank_"
    )
    assert preflight["target_index_name"] != preflight["alias_name"]
    assert preflight["max_documents"] == 1000
    assert preflight["chunk_size"] == 250
    assert "reason" in rollback

    checklist = _read(OPERATOR_CHECKLIST)
    assert "write_strategy = reindex_alias_swap" in checklist
    assert "result_json.rollout.alias_swap_completed" in checklist
    assert "GET /v1/governance/elasticsearch/jobs/{job_id}" in checklist
