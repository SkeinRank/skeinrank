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
