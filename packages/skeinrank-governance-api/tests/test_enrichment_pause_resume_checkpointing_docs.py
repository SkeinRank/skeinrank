from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def _read(relative: str) -> str:
    return (REPO_ROOT / relative).read_text(encoding="utf-8")


def test_pause_resume_checkpointing_guide_documents_real_endpoints() -> None:
    guide = _read("docs/guides/enrichment-pause-resume-checkpointing.md")

    assert "POST /v1/governance/elasticsearch/jobs/{job_id}/pause" in guide
    assert "POST /v1/governance/elasticsearch/jobs/{job_id}/resume" in guide
    assert "GET  /v1/governance/elasticsearch/jobs/{job_id}" in guide
    assert "result_json.chunked_enrichment.checkpoint" in guide
    assert "SKEINRANK_GOVERNANCE_API_ENRICHMENT_JOBS_BACKEND=celery" in guide
    assert "queued\nrunning\npause_requested\npaused\ncancel_requested" in guide


def test_pause_resume_examples_are_valid_json() -> None:
    pause = json.loads(_read("examples/enrichment-pause-resume/pause-request.json"))
    resume = json.loads(_read("examples/enrichment-pause-resume/resume-request.json"))

    assert pause == {"reason": "maintenance window closed"}
    assert resume == {"reason": "maintenance window reopened"}


def test_docs_index_and_api_reference_link_pause_resume() -> None:
    docs_index = _read("docs/README.md")
    api_doc = _read("docs/api/governance-api.md")
    package_readme = _read("packages/skeinrank-governance-api/README.md")

    assert "guides/enrichment-pause-resume-checkpointing.md" in docs_index
    assert "POST /v1/governance/elasticsearch/jobs/{job_id}/pause" in api_doc
    assert "POST /v1/governance/elasticsearch/jobs/{job_id}/resume" in api_doc
    assert "examples/enrichment-pause-resume" in package_readme


def test_status_constraint_migration_includes_pause_states() -> None:
    migration = _read(
        "packages/skeinrank-governance/alembic/versions/"
        "20260529_0026_enrichment_pause_resume_statuses.py"
    )
    models = _read("packages/skeinrank-governance/skeinrank_governance/models.py")

    assert "pause_requested" in migration
    assert "paused" in migration
    assert '"pause_requested"' in models
    assert '"paused"' in models
