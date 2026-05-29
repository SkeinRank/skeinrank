from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
DOC = REPO_ROOT / "docs/guides/enrichment-beta-hardening.md"
ENRICHMENT_DOC = REPO_ROOT / "docs/guides/elasticsearch-enrichment.md"
DOCS_README = REPO_ROOT / "docs/README.md"
ROOT_README = REPO_ROOT / "README.md"
API_DOC = REPO_ROOT / "docs/api/governance-api.md"
GOVERNANCE_API_README = REPO_ROOT / "packages/skeinrank-governance-api/README.md"
ROUTES = (
    REPO_ROOT
    / "packages/skeinrank-governance-api/skeinrank_governance_api/routes/governance.py"
)
SCHEMAS = (
    REPO_ROOT / "packages/skeinrank-governance-api/skeinrank_governance_api/schemas.py"
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_enrichment_beta_hardening_docs_are_discoverable() -> None:
    assert DOC.exists()
    assert "docs/guides/enrichment-beta-hardening.md" in _read(ROOT_README)
    assert "guides/enrichment-beta-hardening.md" in _read(DOCS_README)
    assert "enrichment-beta-hardening.md" in _read(ENRICHMENT_DOC)
    assert "docs/guides/enrichment-beta-hardening.md" in _read(GOVERNANCE_API_README)


def test_enrichment_beta_hardening_documents_real_api_surface() -> None:
    doc = _read(DOC)
    api_doc = _read(API_DOC)
    routes = _read(ROUTES)
    schemas = _read(SCHEMAS)

    expected_fragments = (
        "POST /v1/governance/elasticsearch/bindings/{binding_id}/jobs/preflight",
        "POST /v1/governance/elasticsearch/bindings/{binding_id}/jobs",
        "GET /v1/governance/elasticsearch/jobs?binding_id=...",
        "POST /v1/governance/elasticsearch/jobs/{job_id}/cancel",
        "POST /v1/governance/elasticsearch/jobs/{job_id}/rollback",
        "blocking_issues",
        "recommended_request",
        "cancel_requested",
        "reindex_alias_swap",
        "in_place",
    )
    for fragment in expected_fragments:
        assert fragment in doc

    assert "/elasticsearch/bindings/{binding_id}/jobs/preflight" in routes
    assert "preflight_elasticsearch_enrichment_job" in routes
    assert "ElasticsearchEnrichmentPreflightResponse" in routes
    assert "ElasticsearchEnrichmentPreflightResponse" in schemas
    assert "/elasticsearch/bindings/{binding_id}/jobs/preflight" in api_doc

    forbidden_fragments = (
        "/v1/enrichment/reload",
        "/v1/runtime/reload",
        "skeinrank-enrichmentctl",
        "pause_elasticsearch_enrichment_job",
    )
    for fragment in forbidden_fragments:
        assert fragment not in doc
