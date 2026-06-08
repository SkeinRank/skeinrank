import json
from pathlib import Path

import pytest
from skeinrank import (
    DRIFT_REPORT_SCHEMA_VERSION,
    DriftEvidence,
    DriftFinding,
    DriftFindingType,
    DriftSeverity,
    TerminologyDriftReport,
)


def _sample_report() -> TerminologyDriftReport:
    return TerminologyDriftReport(
        profile_name="infra_incidents",
        binding_id="infra_incidents_prod",
        dictionary_schema_version="skeinrank.dictionary.v1",
        pinned_snapshot_version="S42",
        latest_snapshot_version="S47",
        document_count=12,
        source_count=2,
        metrics={"unknown_alias_rate": 0.118, "new_candidate_count": 2},
        findings=[
            DriftFinding(
                finding_type=DriftFindingType.ALIAS_DRIFT,
                severity=DriftSeverity.WARN,
                title="New candidate alias detected",
                value="kubelet oom",
                metrics={"mentions": 42, "document_count": 9},
                evidence=[
                    DriftEvidence(
                        source="incident-1.md",
                        line=7,
                        text="Kubelet OOM after the node pool upgrade.",
                        score=0.91,
                    )
                ],
                recommended_action="Review as a candidate alias before publishing a new snapshot.",
            ),
            DriftFinding(
                finding_type=DriftFindingType.BINDING_LAG,
                severity=DriftSeverity.INFO,
                title="Binding is behind the latest approved snapshot",
                value="infra_incidents_prod",
                pinned_snapshot_version="S42",
                latest_snapshot_version="S47",
                metrics={"snapshot_lag": 5},
            ),
        ],
        notes=["Local report only; no runtime state was changed."],
    )


def test_drift_report_schema_exports_versioned_json(tmp_path: Path):
    report = _sample_report()

    payload = json.loads(report.to_json())

    assert payload["schema_version"] == DRIFT_REPORT_SCHEMA_VERSION
    assert payload["profile_name"] == "infra_incidents"
    assert payload["binding_id"] == "infra_incidents_prod"
    assert payload["findings"][0]["finding_type"] == "alias_drift"
    assert payload["findings"][0]["evidence"][0]["source"] == "incident-1.md"

    path = tmp_path / "drift-report.json"
    report.save(path)
    loaded = TerminologyDriftReport.from_file(path)

    assert loaded.schema_version == DRIFT_REPORT_SCHEMA_VERSION
    assert loaded.findings[0].normalized_value == "kubelet oom"
    assert loaded.findings[0].binding_id == "infra_incidents_prod"


def test_drift_report_summary_and_filters_are_computed():
    report = _sample_report()

    summary = report.summary()

    assert summary.finding_count == 2
    assert summary.warn_count == 1
    assert summary.info_count == 1
    assert summary.alias_drift_count == 1
    assert summary.binding_lag_count == 1
    assert summary.unknown_alias_rate == pytest.approx(0.118)
    assert report.findings_by_type("alias_drift")[0].value == "kubelet oom"
    assert report.findings_by_severity(DriftSeverity.INFO)[0].finding_type == (
        DriftFindingType.BINDING_LAG
    )


def test_drift_report_markdown_is_reviewable_and_not_a_monitor_claim():
    markdown = _sample_report().to_markdown()

    assert "# Terminology drift report" in markdown
    assert "infra_incidents_prod" in markdown
    assert "Unknown alias rate" in markdown
    assert "kubelet oom" in markdown
    assert "Drift Monitor" not in markdown


def test_drift_finding_rejects_empty_required_text():
    with pytest.raises(ValueError):
        DriftEvidence(source="", text="valid evidence")

    with pytest.raises(ValueError):
        DriftFinding(
            finding_type=DriftFindingType.ALIAS_DRIFT,
            title=" ",
        )
