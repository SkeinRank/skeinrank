import json
from pathlib import Path

import pytest
from skeinrank import DictionaryDraft, DraftCandidate, import_dictionary
from skeinrank.drafts import DRAFT_SCHEMA_VERSION


def test_dictionary_draft_from_import_is_reviewable_not_runtime_by_default(
    tmp_path: Path,
):
    source = tmp_path / "terms.csv"
    source.write_text(
        "canonical,alias,slot\n"
        "kubernetes,k8s,TECHNOLOGY\n"
        "postgresql,pg,DATABASE\n",
        encoding="utf-8",
    )

    result = import_dictionary(source, name="platform_ops")
    draft = result.to_draft()

    assert draft.schema_version == DRAFT_SCHEMA_VERSION
    assert draft.profile_name == "platform_ops"
    assert draft.source_format == "csv"
    assert draft.candidate_count == 2
    assert draft.proposed_count == 2
    assert draft.accepted_count == 0
    assert {candidate.status for candidate in draft.candidates} == {"proposed"}
    assert any(
        finding.code == "validate.risky_short_alias" for finding in draft.findings
    )

    with pytest.raises(ValueError, match="no accepted candidates"):
        draft.to_dictionary()

    reviewed = draft.accept_all()
    dictionary = reviewed.to_dictionary()

    assert dictionary.profile_name == "platform_ops"
    assert [term.canonical_value for term in dictionary.terms] == [
        "kubernetes",
        "postgresql",
    ]


def test_dictionary_draft_can_save_and_load_review_artifact(tmp_path: Path):
    draft = DictionaryDraft(
        profile_name="company_terms",
        source_path="terms.json",
        source_format="json",
        candidates=[
            DraftCandidate(
                canonical_value="kubernetes",
                aliases=["k8s", "kube", "k8s"],
                slot="TECHNOLOGY",
            )
        ],
    )

    path = tmp_path / "company_terms.dictionary-draft.json"
    draft.save(path)

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == DRAFT_SCHEMA_VERSION
    assert payload["candidates"][0]["aliases"] == ["k8s", "kube"]

    loaded = DictionaryDraft.from_file(path)
    assert loaded.profile_name == "company_terms"
    assert loaded.candidates[0].canonical_value == "kubernetes"


def test_dictionary_draft_review_markdown_summarizes_candidates_and_findings(
    tmp_path: Path,
):
    source = tmp_path / "synonyms.txt"
    source.write_text("pg => postgresql\n", encoding="utf-8")

    result = import_dictionary(source, fmt="es-synonyms", name="company_terms")
    markdown = result.to_draft().review_markdown()

    assert "# Dictionary draft review" in markdown
    assert "- Profile: `company_terms`" in markdown
    assert "| Severity | Source | Code | Line | Message |" in markdown
    assert "validate.risky_short_alias" in markdown
    assert "| proposed | `postgresql` | `TERM` | `pg` |" in markdown


def test_dictionary_draft_can_reject_candidates_before_export(tmp_path: Path):
    source = tmp_path / "terms.json"
    source.write_text(
        json.dumps(
            {
                "kubernetes": ["k8s", "kube"],
                "postgresql": ["pg", "postgres"],
            }
        ),
        encoding="utf-8",
    )

    draft = import_dictionary(source, name="company_terms").to_draft()
    reviewed = draft.accept_all().reject("postgresql")
    dictionary = reviewed.to_dictionary()

    assert [term.canonical_value for term in dictionary.terms] == ["kubernetes"]


def test_import_dictionary_cli_can_write_reviewable_draft(tmp_path: Path, capsys):
    from skeinrank.cli import main

    source = tmp_path / "terms.csv"
    source.write_text("canonical,alias\nkubernetes,k8s\n", encoding="utf-8")
    draft_path = tmp_path / "terms.dictionary-draft.json"

    exit_code = main(
        [
            "import-dictionary",
            str(source),
            "--name",
            "company_terms",
            "--draft-out",
            str(draft_path),
        ]
    )

    assert exit_code == 0
    assert f"Wrote {draft_path}" in capsys.readouterr().out

    draft = DictionaryDraft.from_file(draft_path)
    assert draft.profile_name == "company_terms"
    assert draft.candidates[0].status == "proposed"
