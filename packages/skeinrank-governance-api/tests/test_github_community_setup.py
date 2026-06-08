from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
ISSUE_TEMPLATE_DIR = REPO_ROOT / ".github" / "ISSUE_TEMPLATE"
LABELS = REPO_ROOT / ".github" / "labels.yml"
PR_TEMPLATE = REPO_ROOT / ".github" / "PULL_REQUEST_TEMPLATE.md"
DISCUSSIONS_DOC = REPO_ROOT / "docs" / "community" / "discussions.md"
LABELS_DOC = REPO_ROOT / "docs" / "community" / "github-labels.md"
ROOT_README = REPO_ROOT / "README.md"
DOCS_README = REPO_ROOT / "docs" / "README.md"
CONTRIBUTING = REPO_ROOT / "CONTRIBUTING.md"

REQUIRED_LABELS = [
    "type: bug",
    "type: feature",
    "type: docs",
    "type: refactor",
    "type: question",
    "type: integration",
    "area: governance-api",
    "area: ui",
    "area: core",
    "area: elasticsearch",
    "area: mcp",
    "area: docs",
    "area: ci",
    "area: site",
    "status: needs-triage",
    "status: accepted",
    "status: blocked",
    "status: good-first-issue",
    "priority: p0",
    "priority: p1",
    "priority: p2",
]

ISSUE_FORMS = [
    "bug_report.yml",
    "feature_request.yml",
    "docs_issue.yml",
    "integration_request.yml",
    "ci_failure.yml",
    "config.yml",
]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_github_labels_are_defined_for_triage_taxonomy() -> None:
    content = _read(LABELS)

    for label in REQUIRED_LABELS:
        assert f'name: "{label}"' in content

    # Keep the label taxonomy compact and predictable.
    names = re.findall(r'^- name: "([^"]+)"', content, flags=re.MULTILINE)
    assert names == REQUIRED_LABELS


def test_issue_forms_route_work_to_issues_and_discussions() -> None:
    for filename in ISSUE_FORMS:
        assert (ISSUE_TEMPLATE_DIR / filename).exists(), filename

    bug = _read(ISSUE_TEMPLATE_DIR / "bug_report.yml")
    feature = _read(ISSUE_TEMPLATE_DIR / "feature_request.yml")
    docs = _read(ISSUE_TEMPLATE_DIR / "docs_issue.yml")
    integration = _read(ISSUE_TEMPLATE_DIR / "integration_request.yml")
    ci = _read(ISSUE_TEMPLATE_DIR / "ci_failure.yml")
    config = _read(ISSUE_TEMPLATE_DIR / "config.yml")

    assert '"type: bug"' in bug
    assert '"status: needs-triage"' in bug
    assert "Redact secrets" in bug
    assert "Questions and architecture discussions belong" in bug
    assert '"type: feature"' in feature
    assert "proposal/review/snapshot" in feature
    assert '"type: docs"' in docs
    assert '"area: docs"' in docs
    assert '"type: integration"' in integration
    assert "Elasticsearch" in integration
    assert '"area: ci"' in ci
    assert "GitHub Actions" in ci or "CI run" in ci
    assert "blank_issues_enabled: false" in config
    assert "/discussions/categories/q-a" in config
    assert "/discussions/categories/architecture-rfc" in config
    assert "/discussions/categories/integrations" in config


def test_discussion_and_label_docs_explain_repository_community_flow() -> None:
    discussions = _read(DISCUSSIONS_DOC)
    labels_doc = _read(LABELS_DOC)

    for category in (
        "Announcements",
        "Q&A",
        "Ideas",
        "Architecture / RFC",
        "Integrations",
        "Show and tell",
    ):
        assert category in discussions

    assert "Issues vs Discussions" in discussions
    assert "Maintainer workflow" in discussions
    assert "release conversations" in discussions
    assert "GitHub Release notes" in discussions
    assert "v0.10.0-beta.1" not in discussions
    assert "Pinned discussion drafts" not in discussions
    assert "```markdown" not in discussions

    for label in REQUIRED_LABELS:
        assert label in labels_doc

    assert ".github/labels.yml" in labels_doc
    assert "source of truth" in labels_doc
    assert "gh label create" not in labels_doc
    assert "--force" not in labels_doc


def test_readme_docs_and_contributing_link_community_guidance() -> None:
    readme = _read(ROOT_README)
    docs_readme = _read(DOCS_README)
    contributing = _read(CONTRIBUTING)
    pr_template = _read(PR_TEMPLATE)

    assert "docs/community/discussions.md" in readme
    assert "docs/community/github-labels.md" in readme
    assert "community/discussions.md" in docs_readme
    assert "community/github-labels.md" in docs_readme
    assert "Issues and Discussions" in contributing
    assert "status: needs-triage" in contributing
    assert "Architecture / RFC" in contributing
    assert "type:*" in pr_template
    assert "area:*" in pr_template
    assert "priority:*" in pr_template
