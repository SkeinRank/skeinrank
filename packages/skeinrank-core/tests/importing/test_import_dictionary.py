import json
from pathlib import Path

import pytest
from skeinrank import import_dictionary
from skeinrank.importing import (
    CsvDictionaryParser,
    EsSynonymsParser,
    JsonDictionaryParser,
    detect_format,
)


def test_detect_format_uses_extension_override_and_es_heuristic():
    assert detect_format("terms.json", "{}") == "json"
    assert detect_format("terms.csv", "canonical,alias") == "csv"
    assert detect_format("synonyms.txt", "k8s, kube => kubernetes") == "es-synonyms"
    assert detect_format("terms.data", "a,b=>c") == "es-synonyms"
    assert detect_format("terms.data", "", override="csv") == "csv"

    with pytest.raises(ValueError, match="Cannot detect"):
        detect_format("terms.data", "not enough")


def test_json_parser_accepts_simple_mapping():
    result = JsonDictionaryParser().parse(
        json.dumps(
            {
                "kubernetes": ["k8s", "kube"],
                "postgresql": {"aliases": ["pg"], "slot": "DATABASE"},
            }
        )
    )

    assert [(item.canonical, item.alias, item.slot) for item in result.mappings] == [
        ("kubernetes", "k8s", None),
        ("kubernetes", "kube", None),
        ("postgresql", "pg", "DATABASE"),
    ]
    assert result.warnings == []


def test_json_parser_accepts_skeinrank_terms_payload():
    payload = {
        "profile_name": "infra",
        "terms": [
            {
                "canonical_value": "kubernetes",
                "slot": "TOOL",
                "aliases": ["k8s", {"value": "kube"}],
            }
        ],
    }

    result = JsonDictionaryParser().parse(json.dumps(payload))

    assert [(item.canonical, item.alias, item.slot) for item in result.mappings] == [
        ("kubernetes", "k8s", "TOOL"),
        ("kubernetes", "kube", "TOOL"),
    ]


def test_csv_parser_accepts_canonical_alias_and_slot_columns():
    result = CsvDictionaryParser().parse(
        "canonical,alias,slot\n"
        "kubernetes,k8s,TOOL\n"
        "postgresql,pg|postgres,DATABASE\n"
    )

    assert [(item.canonical, item.alias, item.slot) for item in result.mappings] == [
        ("kubernetes", "k8s", "TOOL"),
        ("postgresql", "pg", "DATABASE"),
        ("postgresql", "postgres", "DATABASE"),
    ]
    assert result.warnings == []


def test_csv_parser_reports_missing_columns():
    result = CsvDictionaryParser().parse("name,value\nkubernetes,k8s\n")

    assert result.mappings == []
    assert result.warnings[0].severity.value == "fatal"
    assert result.warnings[0].code == "csv.missing_columns"


def test_es_synonyms_parser_handles_explicit_and_equivalent_sets():
    result = EsSynonymsParser().parse(
        "# comments are ignored\n"
        "k8s, kube => kubernetes\n"
        "postgres, psql, postgresql\n"
        "lonely\n"
    )

    assert [
        (item.canonical, item.alias, item.source_line) for item in result.mappings
    ] == [
        ("kubernetes", "k8s", 2),
        ("kubernetes", "kube", 2),
        ("postgres", "psql", 3),
        ("postgres", "postgresql", 3),
    ]
    assert [warning.code for warning in result.warnings] == [
        "es.canonical_guessed",
        "es.single_term_skipped",
    ]


def test_import_dictionary_writes_candidate_dictionary_and_report(tmp_path: Path):
    source = tmp_path / "company_terms.csv"
    source.write_text(
        "canonical,alias,slot\n" "kubernetes,k8s,TOOL\n" "postgresql,pg,DATABASE\n",
        encoding="utf-8",
    )

    result = import_dictionary(source, name="company_terms")

    assert result.report.is_ok
    assert result.report.detected_format == "csv"
    assert result.report.canonical_count == 2
    assert result.report.alias_count == 2
    assert result.dictionary is not None
    assert result.dictionary.profile_name == "company_terms"
    assert result.dictionary.terms[0].canonical_value == "kubernetes"

    out = tmp_path / "company.dictionary.json"
    result.save(out)

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["profile_name"] == "company_terms"
    assert payload["terms"][0]["aliases"][0]["value"] == "k8s"


def test_import_dictionary_reports_alias_collisions_without_mutating_runtime(
    tmp_path: Path,
):
    source = tmp_path / "synonyms.txt"
    source.write_text(
        "pg => postgresql\n" "pg => page\n",
        encoding="utf-8",
    )

    result = import_dictionary(source, fmt="es-synonyms", name="company_terms")

    assert result.report.is_ok
    assert result.dictionary is not None
    assert result.report.warning_count == 1
    assert result.report.warnings[0].code == "build.alias_collision"
    assert "review" in result.report.warnings[0].message.lower()


def test_import_dictionary_save_rejects_fatal_import(tmp_path: Path):
    source = tmp_path / "bad.csv"
    source.write_text("name,value\nkubernetes,k8s\n", encoding="utf-8")

    result = import_dictionary(source, fmt="csv")

    assert not result.report.is_ok
    assert result.dictionary is None
    with pytest.raises(ValueError, match="fatal"):
        result.save(tmp_path / "out.json")


def test_import_report_markdown_contains_counts(tmp_path: Path):
    source = tmp_path / "terms.json"
    source.write_text(
        json.dumps({"kubernetes": ["k8s", "kube"]}),
        encoding="utf-8",
    )

    result = import_dictionary(source)
    markdown = result.report.to_markdown()

    assert "# Dictionary import report" in markdown
    assert "- Format: `json`" in markdown
    assert "- Canonical terms: **1**" in markdown
    assert "- Aliases: **2**" in markdown
