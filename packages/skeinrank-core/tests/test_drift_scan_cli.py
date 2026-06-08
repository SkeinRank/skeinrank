import json
from pathlib import Path

from skeinrank import (
    DriftFindingType,
    DriftScanConfig,
    TerminologyDriftReport,
    scan_dictionary_drift,
    scan_dictionary_drift_from_documents,
)
from skeinrank.cli import main


def _dictionary_payload():
    return {
        "profile_name": "infra_incidents",
        "terms": [
            {
                "canonical_value": "kubernetes",
                "slot": "TOOL",
                "aliases": ["k8s", "kube"],
            },
            {
                "canonical_value": "postgresql",
                "slot": "DATABASE",
                "aliases": ["pg", "postgres"],
            },
        ],
    }


def _write_dictionary(tmp_path: Path) -> Path:
    path = tmp_path / "company.dictionary.json"
    path.write_text(json.dumps(_dictionary_payload()), encoding="utf-8")
    return path


def _write_docs(tmp_path: Path) -> Path:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "incident-1.md").write_text(
        "KubeletOOM appeared during k8s deploy. KubeletOOM returned after pg migration.",
        encoding="utf-8",
    )
    (docs / "incident-2.md").write_text(
        "RedisEvict repeated after pg failover. KubeletOOM stayed active.",
        encoding="utf-8",
    )
    return docs


def test_scan_dictionary_drift_emits_alias_drift_report(tmp_path: Path):
    dictionary = _write_dictionary(tmp_path)
    docs = _write_docs(tmp_path)

    report = scan_dictionary_drift(
        dictionary=dictionary,
        docs=[docs],
        config=DriftScanConfig(
            min_frequency=2,
            binding_id="infra_incidents_prod",
            pinned_snapshot_version="S42",
            latest_snapshot_version="S47",
        ),
    )

    assert isinstance(report, TerminologyDriftReport)
    assert report.profile_name == "infra_incidents"
    assert report.binding_id == "infra_incidents_prod"
    assert report.pinned_snapshot_version == "S42"
    assert report.latest_snapshot_version == "S47"
    assert report.metrics["unknown_candidate_count"] >= 1
    assert report.summary().alias_drift_count >= 1
    assert 0 < report.summary().unknown_alias_rate <= 1
    assert any(finding.value == "KubeletOOM" for finding in report.findings)
    first = report.findings_by_type(DriftFindingType.ALIAS_DRIFT)[0]
    assert first.recommended_action
    assert first.evidence[0].source.endswith(".md")
    assert "runtime state was changed" in " ".join(report.notes)


def test_scan_dictionary_drift_from_documents_filters_known_aliases():
    report = scan_dictionary_drift_from_documents(
        dictionary=_dictionary_payload(),
        documents=[
            {
                "source": "incident.md",
                "text": "k8s pg KubeletOOM KubeletOOM",
            }
        ],
        config={"discovery": {"min_frequency": 2}},
    )

    values = {finding.value for finding in report.findings}
    assert "KubeletOOM" in values
    assert "k8s" not in values
    assert "pg" not in values
    assert report.metrics["known_dictionary_match_count"] == 2


def test_drift_scan_cli_writes_json_and_markdown(tmp_path: Path, capsys):
    dictionary = _write_dictionary(tmp_path)
    docs = _write_docs(tmp_path)
    out = tmp_path / "drift-report.json"
    markdown = tmp_path / "drift-report.md"

    exit_code = main(
        [
            "drift",
            "scan",
            "--dictionary",
            str(dictionary),
            "--docs",
            str(docs),
            "--binding-id",
            "infra_incidents_prod",
            "--pinned-snapshot",
            "S42",
            "--latest-snapshot",
            "S47",
            "--min-frequency",
            "2",
            "--out",
            str(out),
            "--markdown",
            str(markdown),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert f"Wrote {out}" in captured.out
    assert f"Wrote {markdown}" in captured.out

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "skeinrank.terminology_drift_report.v1"
    assert payload["binding_id"] == "infra_incidents_prod"
    assert payload["findings"][0]["finding_type"] == "alias_drift"
    assert "Terminology drift report" in markdown.read_text(encoding="utf-8")


def test_drift_scan_cli_can_print_compact_json(tmp_path: Path, capsys):
    dictionary = _write_dictionary(tmp_path)
    docs = _write_docs(tmp_path)

    exit_code = main(
        [
            "drift",
            "scan",
            "--dictionary",
            str(dictionary),
            "--docs",
            str(docs),
            "--min-frequency",
            "2",
            "--json",
            "--compact",
        ]
    )

    assert exit_code == 0
    output = capsys.readouterr().out.strip()
    assert "\n" not in output
    payload = json.loads(output)
    assert payload["metrics"]["unknown_candidate_count"] >= 1


def test_drift_scan_cli_prints_markdown_by_default(tmp_path: Path, capsys):
    dictionary = _write_dictionary(tmp_path)
    docs = _write_docs(tmp_path)

    exit_code = main(
        [
            "drift",
            "scan",
            "--dictionary",
            str(dictionary),
            "--docs",
            str(docs),
            "--min-frequency",
            "2",
        ]
    )

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "# Terminology drift report" in output
    assert "Unknown alias rate" in output
    assert "Drift Monitor" not in output
