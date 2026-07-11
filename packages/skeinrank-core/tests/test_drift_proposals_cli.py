import json
from pathlib import Path

from skeinrank import (
    DictionaryDraft,
    DriftEvidence,
    DriftFinding,
    DriftFindingType,
    DriftSeverity,
    TerminologyDriftReport,
    drift_report_to_dictionary_draft,
)
from skeinrank.cli import main


def _sample_report() -> TerminologyDriftReport:
    return TerminologyDriftReport(
        profile_name="infra_incidents",
        binding_id="infra_incidents_prod",
        document_count=2,
        source_count=2,
        metrics={"unknown_alias_rate": 0.42},
        findings=[
            DriftFinding(
                finding_type=DriftFindingType.ALIAS_DRIFT,
                severity=DriftSeverity.WARN,
                title="Unmatched terminology candidate: KubeletOOM",
                value="KubeletOOM",
                normalized_value="kubelet oom",
                metrics={"mention_count": 4, "document_count": 2, "confidence": 0.82},
                evidence=[
                    DriftEvidence(
                        source="incident-1.md",
                        line=3,
                        text="KubeletOOM returned after the node pool deploy.",
                        score=0.82,
                    )
                ],
            ),
            DriftFinding(
                finding_type=DriftFindingType.STALE_TERM,
                severity=DriftSeverity.INFO,
                title="Dictionary term has little or no corpus evidence: mesos",
                value="mesos",
            ),
        ],
        notes=["Local drift scan only; no runtime state was changed."],
    )


def test_drift_report_to_dictionary_draft_preserves_review_boundary():
    result = drift_report_to_dictionary_draft(_sample_report())

    draft = result.draft
    assert isinstance(draft, DictionaryDraft)
    assert draft.profile_name == "infra_incidents"
    assert draft.source_format == "terminology_drift_report"
    assert draft.candidate_count == 1
    assert draft.candidates[0].status == "proposed"
    assert draft.candidates[0].canonical_value == "kubelet oom"
    assert draft.candidates[0].aliases == ["KubeletOOM"]
    assert draft.candidates[0].source == "drift_report"
    assert draft.candidates[0].evidence[0].source == "incident-1.md"
    assert any(finding.code == "drift.stale_term" for finding in draft.findings)
    assert any(finding.code == "drift.draft_generated" for finding in draft.findings)


def test_drift_report_to_dictionary_draft_accepts_file_input(tmp_path: Path):
    report_path = tmp_path / "drift-report.json"
    _sample_report().save(report_path)

    result = drift_report_to_dictionary_draft(
        report_path,
        config={"profile_name": "reviewed_terms", "default_slot": "INCIDENT_TERM"},
    )

    assert result.draft.profile_name == "reviewed_terms"
    assert result.draft.source_path == str(report_path)
    assert result.draft.candidates[0].slot == "INCIDENT_TERM"


def test_drift_export_draft_cli_writes_draft_and_review(tmp_path: Path, capsys):
    report_path = tmp_path / "drift-report.json"
    draft_path = tmp_path / "drift.dictionary-draft.json"
    review_path = tmp_path / "drift.review.md"
    _sample_report().save(report_path)

    exit_code = main(
        [
            "drift",
            "export-draft",
            str(report_path),
            "--profile-name",
            "reviewed_terms",
            "--slot",
            "INCIDENT_TERM",
            "--out",
            str(draft_path),
            "--review",
            str(review_path),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert f"Wrote {draft_path}" in captured.out
    assert f"Wrote {review_path}" in captured.out

    draft = DictionaryDraft.from_file(draft_path)
    assert draft.profile_name == "reviewed_terms"
    assert draft.candidates[0].canonical_value == "kubelet oom"
    assert draft.candidates[0].slot == "INCIDENT_TERM"
    assert "Dictionary draft review" in review_path.read_text(encoding="utf-8")


def test_drift_export_draft_cli_can_print_compact_json(tmp_path: Path, capsys):
    report_path = tmp_path / "drift-report.json"
    _sample_report().save(report_path)

    exit_code = main(
        [
            "drift",
            "export-draft",
            str(report_path),
            "--json",
            "--compact",
            "--no-report-findings",
        ]
    )

    assert exit_code == 0
    output = capsys.readouterr().out.strip()
    assert "\n" not in output
    payload = json.loads(output)
    assert payload["source_format"] == "terminology_drift_report"
    assert payload["candidates"][0]["aliases"] == ["KubeletOOM"]
    assert all(finding["code"] != "drift.stale_term" for finding in payload["findings"])


def test_conversion_summary_explains_non_convertible_findings():
    report = TerminologyDriftReport(
        profile_name="infra_incidents",
        document_count=2,
        source_count=2,
        findings=[
            DriftFinding(
                finding_type=DriftFindingType.STALE_TERM,
                severity=DriftSeverity.INFO,
                title=f"Stale term {index}",
                value=f"term-{index}",
            )
            for index in range(6)
        ],
    )

    result = drift_report_to_dictionary_draft(report)

    assert result.draft.candidate_count == 0
    assert result.summary.status == "no_convertible_findings"
    assert result.summary.source_finding_count == 6
    assert result.summary.alias_drift_finding_count == 0
    assert result.summary.candidate_count == 0
    assert result.summary.skipped_finding_count == 6
    assert result.summary.skipped_findings_by_type == {"stale_term": 6}
    assert result.summary.message == (
        "No dictionary candidates were created because the report contains no "
        "alias_drift findings. 6 non-convertible finding(s) remain available for "
        "review (stale_term=6)."
    )
    assert any(
        finding.code == "drift.conversion_summary"
        and finding.message == result.summary.message
        for finding in result.draft.findings
    )
    markdown = result.review_markdown()
    assert "## Conversion summary" in markdown
    assert "`stale_term`=6" in markdown


def test_conversion_summary_reports_successful_alias_conversion():
    result = drift_report_to_dictionary_draft(_sample_report())

    assert result.summary.status == "completed"
    assert result.summary.source_finding_count == 2
    assert result.summary.alias_drift_finding_count == 1
    assert result.summary.candidate_source_finding_count == 1
    assert result.summary.candidate_count == 1
    assert result.summary.preserved_finding_count == 2
    assert result.summary.skipped_findings_by_type == {"stale_term": 1}


def test_conversion_summary_explains_disabled_alias_conversion():
    result = drift_report_to_dictionary_draft(
        _sample_report(),
        config={"include_alias_drift": False},
    )

    assert result.draft.candidate_count == 0
    assert result.summary.status == "alias_conversion_disabled"
    assert result.summary.alias_drift_finding_count == 1
    assert result.summary.candidate_source_finding_count == 0
    assert result.summary.skipped_findings_by_type == {
        "alias_drift": 1,
        "stale_term": 1,
    }
    assert "alias-drift conversion is disabled" in result.summary.message


def test_drift_export_draft_cli_writes_conversion_summary(tmp_path: Path, capsys):
    report_path = tmp_path / "drift-report.json"
    summary_path = tmp_path / "drift-conversion-summary.json"
    _sample_report().save(report_path)

    exit_code = main(
        [
            "drift",
            "export-draft",
            str(report_path),
            "--summary",
            str(summary_path),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert f"Wrote {summary_path}" in captured.out
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    assert payload["status"] == "completed"
    assert payload["candidate_count"] == 1
    assert payload["skipped_findings_by_type"] == {"stale_term": 1}


def test_drift_export_draft_cli_prints_precise_empty_candidate_reason(
    tmp_path: Path, capsys
):
    report_path = tmp_path / "stale-only-report.json"
    draft_path = tmp_path / "stale-only-draft.json"
    TerminologyDriftReport(
        profile_name="infra_incidents",
        document_count=1,
        source_count=1,
        findings=[
            DriftFinding(
                finding_type=DriftFindingType.STALE_TERM,
                severity=DriftSeverity.INFO,
                title="Stale term",
                value="mesos",
            )
        ],
    ).save(report_path)

    exit_code = main(
        [
            "drift",
            "export-draft",
            str(report_path),
            "--out",
            str(draft_path),
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "report contains no alias_drift findings" in output
    assert "stale_term=1" in output
