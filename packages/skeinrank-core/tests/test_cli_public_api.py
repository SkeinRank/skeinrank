import json
from pathlib import Path

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
    path = tmp_path / "dictionary.json"
    path.write_text(json.dumps(_dictionary_payload()), encoding="utf-8")
    return path


def test_cli_validate_dictionary_prints_human_report(tmp_path: Path, capsys):
    dictionary_path = _write_dictionary(tmp_path)

    exit_code = main(["validate-dictionary", str(dictionary_path)])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Dictionary: infra_incidents" in output
    assert "Status: valid" in output
    assert "Errors: 0" in output


def test_cli_validate_dictionary_json_reports_invalid_payload(tmp_path: Path, capsys):
    dictionary_path = tmp_path / "bad.json"
    dictionary_path.write_text('{"terms":"not-a-list"}', encoding="utf-8")

    exit_code = main(["validate-dictionary", str(dictionary_path), "--json"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert payload["ok"] is False
    assert payload["issues"][0]["code"] == "invalid_dictionary"


def test_cli_extract_from_raw_text_outputs_json(tmp_path: Path, capsys):
    dictionary_path = _write_dictionary(tmp_path)

    exit_code = main(
        [
            "extract",
            "k8s rollout uses pg database",
            "--text",
            "--dictionary",
            str(dictionary_path),
            "--compact",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["canonical_values"] == ["kubernetes", "postgresql"]
    assert payload["matches"][0]["matched_text"] == "k8s"
    assert "<mark>k8s</mark>" in payload["matches"][0]["highlighted_fragment"]


def test_cli_extract_from_document_includes_document_metadata(tmp_path: Path, capsys):
    dictionary_path = _write_dictionary(tmp_path)
    document_path = tmp_path / "incident.md"
    document_path.write_text("kube incident with postgres", encoding="utf-8")

    exit_code = main(
        [
            "extract",
            str(document_path),
            "--dictionary",
            str(dictionary_path),
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["document"]["file_name"] == "incident.md"
    assert payload["extraction"]["canonical_values"] == [
        "kubernetes",
        "postgresql",
    ]


def test_cli_canonicalize_raw_text_prints_text(tmp_path: Path, capsys):
    dictionary_path = _write_dictionary(tmp_path)

    exit_code = main(
        [
            "canonicalize",
            "k8s rollout uses pg database",
            "--text",
            "--dictionary",
            str(dictionary_path),
        ]
    )

    assert exit_code == 0
    assert capsys.readouterr().out.strip() == (
        "kubernetes rollout uses postgresql database"
    )


def test_cli_canonicalize_json_can_write_to_file(tmp_path: Path, capsys):
    dictionary_path = _write_dictionary(tmp_path)
    output_path = tmp_path / "canonicalized.json"

    exit_code = main(
        [
            "canonicalize",
            "k8s rollout",
            "--text",
            "--dictionary",
            str(dictionary_path),
            "--json",
            "--output",
            str(output_path),
        ]
    )

    assert exit_code == 0
    assert capsys.readouterr().out == ""
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["text"] == "kubernetes rollout"
    assert payload["replacements"][0]["alias"] == "k8s"


def test_cli_document_text_extracts_plain_text(tmp_path: Path, capsys):
    document_path = tmp_path / "incident.html"
    document_path.write_text(
        "<html><body><h1>K8s outage</h1><script>ignore()</script></body></html>",
        encoding="utf-8",
    )

    exit_code = main(["document-text", str(document_path)])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "K8s outage" in output
    assert "ignore" not in output


def test_cli_returns_error_for_missing_document(tmp_path: Path, capsys):
    dictionary_path = _write_dictionary(tmp_path)

    exit_code = main(
        [
            "extract",
            str(tmp_path / "missing.md"),
            "--dictionary",
            str(dictionary_path),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Document does not exist" in captured.err


def test_cli_extract_can_use_builtin_demo_dictionary(capsys):
    exit_code = main(
        [
            "extract",
            "k8s pg timeout",
            "--text",
            "--compact",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["canonical_values"] == ["kubernetes", "postgresql", "timeout"]


def test_cli_canonicalize_can_use_builtin_demo_dictionary(capsys):
    exit_code = main(["canonicalize", "k8s pg timeout", "--text"])

    assert exit_code == 0
    assert capsys.readouterr().out.strip() == "kubernetes postgresql timeout"


def test_cli_demo_dictionary_prints_builtin_payload(capsys, tmp_path: Path):
    exit_code = main(["demo-dictionary", "--compact"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["profile_name"] == "platform_ops_demo"
    assert len(payload["terms"]) >= 30

    output_path = tmp_path / "platform_ops_demo.dictionary.json"
    exit_code = main(["demo-dictionary", "--output", str(output_path)])

    assert exit_code == 0
    written = json.loads(output_path.read_text(encoding="utf-8"))
    assert written["profile_name"] == "platform_ops_demo"
    assert len(written["terms"]) >= 30


def test_cli_import_dictionary_from_es_synonyms_writes_candidate(
    tmp_path: Path, capsys
):
    source = tmp_path / "synonyms.txt"
    source.write_text(
        "k8s, kube => kubernetes\n" "pg => postgresql\n",
        encoding="utf-8",
    )
    out = tmp_path / "company.dictionary.json"

    exit_code = main(
        [
            "import-dictionary",
            str(source),
            "--format",
            "es-synonyms",
            "--name",
            "company_terms",
            "--out",
            str(out),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Dictionary import report" in captured.out
    assert f"Wrote {out}" in captured.out

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["profile_name"] == "company_terms"
    assert payload["terms"][0]["canonical_value"] == "kubernetes"


def test_cli_import_dictionary_json_report_can_write_report_file(
    tmp_path: Path, capsys
):
    source = tmp_path / "terms.json"
    source.write_text(
        json.dumps({"kubernetes": ["k8s"], "postgresql": ["pg"]}),
        encoding="utf-8",
    )
    report_path = tmp_path / "report.json"

    exit_code = main(
        [
            "import-dictionary",
            str(source),
            "--json-report",
            "--compact",
            "--report",
            str(report_path),
        ]
    )

    assert exit_code == 0
    assert capsys.readouterr().out == ""
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["detected_format"] == "json"
    assert payload["canonical_count"] == 2
    assert payload["alias_count"] == 2


def test_cli_import_dictionary_returns_nonzero_for_fatal_input(tmp_path: Path, capsys):
    source = tmp_path / "bad.csv"
    source.write_text("name,value\nkubernetes,k8s\n", encoding="utf-8")

    exit_code = main(["import-dictionary", str(source), "--format", "csv"])

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "csv.missing_columns" in output


def test_cli_import_dictionary_no_validate_skips_validator_findings(
    tmp_path: Path, capsys
):
    source = tmp_path / "terms.json"
    source.write_text(json.dumps({"postgresql": ["pg"]}), encoding="utf-8")

    exit_code = main(["import-dictionary", str(source), "--no-validate"])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "validate.risky_short_alias" not in output
    assert "No issues found" in output


def test_cli_import_dictionary_strict_validate_blocks_runtime_collisions(
    tmp_path: Path, capsys
):
    source = tmp_path / "synonyms.txt"
    source.write_text("pg => postgresql\npg => page\n", encoding="utf-8")

    exit_code = main(
        [
            "import-dictionary",
            str(source),
            "--format",
            "es-synonyms",
            "--strict-validate",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "validate.alias_collision" in output
    assert "fatal" in output


def test_cli_import_dictionary_can_write_reviewable_draft(tmp_path: Path, capsys):
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
    payload = json.loads(draft_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "skeinrank.dictionary_draft.v1"
    assert payload["candidates"][0]["status"] == "proposed"
