import json
from pathlib import Path

from skeinrank import (
    BindingLagMetadata,
    DriftFindingType,
    DriftScanConfig,
    DriftSeverity,
    TerminologyDriftReport,
    load_binding_metadata,
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
    assert report.summary().binding_lag_count == 1
    assert report.metrics["binding_snapshot_lag"] == 5
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
    assert payload["metrics"]["binding_lag_count"] == 1
    assert payload["metrics"]["binding_snapshot_lag"] == 5
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


def _dictionary_with_stale_term():
    payload = _dictionary_payload()
    payload["terms"].append(
        {
            "canonical_value": "mesos",
            "slot": "TOOL",
            "aliases": ["mesos cluster"],
        }
    )
    return payload


def test_scan_dictionary_drift_emits_stale_term_findings():
    report = scan_dictionary_drift_from_documents(
        dictionary=_dictionary_with_stale_term(),
        documents=[
            {
                "source": "incident.md",
                "text": "k8s pg KubeletOOM KubeletOOM",
            }
        ],
        config={"discovery": {"min_frequency": 2}},
    )

    stale_findings = report.findings_by_type(DriftFindingType.STALE_TERM)
    assert report.summary().stale_term_count == 1
    assert report.metrics["stale_term_count"] == 1
    assert stale_findings[0].value == "mesos"
    assert stale_findings[0].metrics["mention_count"] == 0
    assert stale_findings[0].metrics["alias_count"] == 1
    assert stale_findings[0].recommended_action


def test_scan_dictionary_drift_can_disable_stale_term_findings():
    report = scan_dictionary_drift_from_documents(
        dictionary=_dictionary_with_stale_term(),
        documents=[
            {
                "source": "incident.md",
                "text": "k8s pg KubeletOOM KubeletOOM",
            }
        ],
        config={
            "include_stale_terms": False,
            "discovery": {"min_frequency": 2},
        },
    )

    assert report.summary().stale_term_count == 0
    assert not report.findings_by_type(DriftFindingType.STALE_TERM)
    assert report.metrics["stale_term_count"] == 0


def test_drift_scan_cli_can_disable_stale_terms(tmp_path: Path, capsys):
    dictionary = tmp_path / "company.dictionary.json"
    dictionary.write_text(json.dumps(_dictionary_with_stale_term()), encoding="utf-8")
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
            "--no-stale-terms",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["metrics"]["stale_term_count"] == 0
    assert all(
        finding["finding_type"] != "stale_term" for finding in payload["findings"]
    )


def test_scan_dictionary_drift_does_not_emit_binding_lag_when_snapshots_match():
    report = scan_dictionary_drift_from_documents(
        dictionary=_dictionary_payload(),
        documents=[
            {
                "source": "incident.md",
                "text": "k8s pg KubeletOOM KubeletOOM",
            }
        ],
        config={
            "binding_id": "infra_incidents_prod",
            "pinned_snapshot_version": "S47",
            "latest_snapshot_version": "S47",
            "discovery": {"min_frequency": 2},
        },
    )

    assert report.summary().binding_lag_count == 0
    assert report.metrics["binding_lag_count"] == 0
    assert report.metrics["binding_snapshot_lag"] == 0
    assert not report.findings_by_type(DriftFindingType.BINDING_LAG)


def test_binding_metadata_file_can_fill_drift_scan_context(tmp_path: Path, capsys):
    dictionary = _write_dictionary(tmp_path)
    docs = _write_docs(tmp_path)
    metadata = tmp_path / "binding-metadata.json"
    metadata.write_text(
        json.dumps(
            {
                "binding_id": "infra_incidents_prod",
                "pinned_snapshot": "S42",
                "latest_snapshot": "S47",
            }
        ),
        encoding="utf-8",
    )

    loaded = load_binding_metadata(metadata)
    assert isinstance(loaded, BindingLagMetadata)
    assert loaded.binding_id == "infra_incidents_prod"
    assert loaded.pinned_snapshot_version == "S42"
    assert loaded.latest_snapshot_version == "S47"

    exit_code = main(
        [
            "drift",
            "scan",
            "--dictionary",
            str(dictionary),
            "--docs",
            str(docs),
            "--binding-metadata",
            str(metadata),
            "--min-frequency",
            "2",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["binding_id"] == "infra_incidents_prod"
    assert payload["pinned_snapshot_version"] == "S42"
    assert payload["latest_snapshot_version"] == "S47"
    assert payload["metrics"]["binding_lag_count"] == 1
    assert payload["metrics"]["binding_snapshot_lag"] == 5
    binding_findings = [
        finding
        for finding in payload["findings"]
        if finding["finding_type"] == "binding_lag"
    ]
    assert binding_findings
    assert binding_findings[0]["severity"] == DriftSeverity.CRITICAL.value


def test_drift_scan_cli_can_disable_binding_lag(tmp_path: Path, capsys):
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
            "--binding-id",
            "infra_incidents_prod",
            "--pinned-snapshot",
            "S42",
            "--latest-snapshot",
            "S47",
            "--no-binding-lag",
            "--min-frequency",
            "2",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["metrics"]["binding_lag_count"] == 0
    assert all(
        finding["finding_type"] != "binding_lag" for finding in payload["findings"]
    )


def _dictionary_with_ambiguous_alias_context():
    return {
        "profile_name": "product_search",
        "terms": [
            {
                "canonical_value": "postgresql",
                "slot": "DATABASE",
                "description": "Database connection timeout migration query planner.",
                "tags": ["database", "storage"],
                "aliases": ["pg", "postgres"],
            }
        ],
    }


def test_scan_dictionary_drift_emits_ambiguity_signal_for_unfamiliar_alias_contexts():
    report = scan_dictionary_drift_from_documents(
        dictionary=_dictionary_with_ambiguous_alias_context(),
        documents=[
            {
                "source": "product-doc.md",
                "text": (
                    "The pg layout render broke the product dashboard.\n"
                    "The pg layout caused a broken dashboard widget."
                ),
            }
        ],
        config={
            "include_stale_terms": False,
            "discovery": {"min_frequency": 3},
            "ambiguity_min_mentions": 2,
            "ambiguity_min_context_terms": 2,
        },
    )

    findings = report.findings_by_type(DriftFindingType.AMBIGUITY_SIGNAL)
    assert report.summary().ambiguity_signal_count == 1
    assert report.metrics["ambiguity_signal_count"] == 1
    assert findings[0].value == "pg"
    assert findings[0].canonical_value == "postgresql"
    assert findings[0].details["slot"] == "DATABASE"
    assert "layout" in findings[0].details["novel_context_terms"]
    assert "dashboard" in findings[0].details["novel_context_terms"]
    assert "did not infer a new meaning" in findings[0].description
    assert findings[0].recommended_action


def test_drift_scan_cli_can_disable_ambiguity_signals(tmp_path: Path, capsys):
    dictionary = tmp_path / "company.dictionary.json"
    dictionary.write_text(
        json.dumps(_dictionary_with_ambiguous_alias_context()),
        encoding="utf-8",
    )
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "product-doc.md").write_text(
        "The pg layout render broke the dashboard. The pg layout broke the dashboard.",
        encoding="utf-8",
    )

    exit_code = main(
        [
            "drift",
            "scan",
            "--dictionary",
            str(dictionary),
            "--docs",
            str(docs),
            "--min-frequency",
            "3",
            "--no-stale-terms",
            "--no-ambiguity-signals",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["metrics"]["ambiguity_signal_count"] == 0
    assert all(
        finding["finding_type"] != "ambiguity_signal" for finding in payload["findings"]
    )
