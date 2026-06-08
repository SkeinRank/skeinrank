from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
DOC = REPO_ROOT / "docs/guides/enrichment-beta-hardening.md"
ENRICHMENT_DOC = REPO_ROOT / "docs/guides/elasticsearch-enrichment.md"
DOCS_README = REPO_ROOT / "docs/README.md"
ROOT_README = REPO_ROOT / "README.md"
API_DOC = REPO_ROOT / "docs/api/governance-api.md"
SEARCH_SCOPE_DOC = REPO_ROOT / "docs/concepts/search-integration-scope.md"
CONTRIBUTING = REPO_ROOT / "CONTRIBUTING.md"
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


def test_operator_controlled_search_delivery_docs_are_discoverable() -> None:
    assert DOC.exists()
    assert "docs/guides/enrichment-beta-hardening.md" in _read(ROOT_README)
    assert "Operator-controlled search delivery" in _read(ROOT_README)
    assert "guides/enrichment-beta-hardening.md" in _read(DOCS_README)
    assert "Operator-controlled search delivery hardening" in _read(DOCS_README)
    assert "enrichment-beta-hardening.md" in _read(ENRICHMENT_DOC)
    assert "SkeinRank remains the source of truth" in _read(ENRICHMENT_DOC)
    assert "docs/guides/enrichment-beta-hardening.md" in _read(GOVERNANCE_API_README)
    assert SEARCH_SCOPE_DOC.exists()
    assert "concepts/search-integration-scope.md" in _read(DOCS_README)
    assert "docs/concepts/search-integration-scope.md" in _read(ROOT_README)
    assert "docs/concepts/search-integration-scope.md" in _read(CONTRIBUTING)


def test_operator_controlled_search_delivery_documents_real_api_surface() -> None:
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
        "confirmation_token",
        "cancel_requested",
        "reindex_alias_swap",
        "in_place",
        "Operator-controlled delivery",
        "SkeinRank owns governed terminology artifacts",
    )
    for fragment in expected_fragments:
        assert fragment in doc

    assert "/elasticsearch/bindings/{binding_id}/jobs/preflight" in routes
    assert "preflight_elasticsearch_enrichment_job" in routes
    assert "ElasticsearchEnrichmentPreflightResponse" in routes
    assert "ElasticsearchEnrichmentPreflightResponse" in schemas
    assert "confirmation_token" in schemas
    assert "/elasticsearch/bindings/{binding_id}/jobs/preflight" in api_doc
    assert "operator-controlled delivery jobs" in api_doc
    assert "not reversible by alias rollback" in api_doc

    forbidden_fragments = (
        "/v1/enrichment/reload",
        "/v1/runtime/reload",
        "skeinrank-enrichmentctl",
        "pause_elasticsearch_enrichment_job",
    )
    for fragment in forbidden_fragments:
        assert fragment not in doc


def test_operator_controlled_delivery_docs_avoid_dev_and_management_positioning() -> (
    None
):
    docs = {
        "root": _read(ROOT_README),
        "hardening": _read(DOC),
        "enrichment": _read(ENRICHMENT_DOC),
        "docs_index": _read(DOCS_README),
        "governance_readme": _read(GOVERNANCE_API_README),
    }

    for name, content in docs.items():
        assert "Enrichment safety" not in content, name
        assert "61B operator runbook" not in content, name
        assert "Patch" not in content, name

    hardening = docs["hardening"]
    assert "Search engines execute retrieval" in hardening
    assert "general Elasticsearch/OpenSearch management layer" in hardening
    assert "Every delivery run confirms one concrete plan" in hardening
    assert "UI remains an inspection and review surface" in hardening


def test_search_integration_scope_policy_keeps_engine_boundaries_explicit() -> None:
    policy = _read(SEARCH_SCOPE_DOC)

    required_fragments = (
        "SkeinRank is a terminology control plane, not a search-engine management platform",
        "Query-time lexical adapter",
        "Vector pre-embedding adapter",
        "Export artifacts",
        "Operator-controlled delivery",
        "the UI remains an inspection and review surface",
        "per-run confirmation token",
        "SkeinRank remains the source of truth",
        "Avoid these scopes",
        "owning search-engine mappings, analyzers, templates, or cluster settings",
        "allowing agents to mutate search backends directly",
        "adding heavyweight backend clients to `skeinrank-core`",
    )
    for fragment in required_fragments:
        assert fragment in policy

    assert "SkeinRankVectorStore" not in policy
    assert "apply --to elasticsearch://prod" not in policy
    assert "Patch" not in policy
