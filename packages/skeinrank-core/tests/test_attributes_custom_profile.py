import json

from skeinrank import (
    build_attribute_profile,
    extract_attributes,
    load_attribute_profile,
)
from skeinrank.attributes.cli import enrich_jsonl_main, extract_main
from skeinrank.attributes.demo import write_jsonl


def _company_profile():
    return build_attribute_profile(
        profile_id="company_terms",
        aliases={
            "kubernetes": ["k8s", "kube", "кубер"],
            "postgresql": ["pg", "postgres"],
        },
        slots={
            "kubernetes": "TOOL",
            "postgresql": "DB",
        },
        snapshot_version="company_terms@v1",
    )


def test_build_attribute_profile_can_be_used_directly_with_extract_attributes():
    profile = _company_profile()

    pack = extract_attributes("кубер timeout on pg", profile=profile, debug=True)

    assert pack.profile_id == "company_terms"
    assert pack.snapshot is not None
    assert pack.snapshot.version == "company_terms@v1"
    assert pack.alias_matcher_backend == "aho_corasick"
    values = {item.value for item in pack.attributes}
    assert {"kubernetes", "postgresql"}.issubset(values)


def test_load_attribute_profile_reads_custom_json_snapshot(tmp_path):
    profile_path = tmp_path / "company_terms.json"
    profile_path.write_text(json.dumps(_company_profile()), encoding="utf-8")

    profile = load_attribute_profile(profile_path)
    pack = extract_attributes("kube and postgres", profile=profile)

    assert pack.profile_id == "company_terms"
    assert {item.value for item in pack.attributes} == {"kubernetes", "postgresql"}


def test_extract_cli_accepts_profile_file(tmp_path, capsys):
    profile_path = tmp_path / "company_terms.json"
    profile_path.write_text(json.dumps(_company_profile()), encoding="utf-8")

    exit_code = extract_main(
        [
            "--text",
            "кубер timeout on pg",
            "--profile-file",
            str(profile_path),
            "--compact",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["profile_id"] == "company_terms"
    assert payload["snapshot_version"] == "company_terms@v1"
    assert "kubernetes" in payload["canonical_values"]
    assert "postgresql" in payload["canonical_values"]


def test_enrich_jsonl_cli_accepts_profile_file(tmp_path):
    profile_path = tmp_path / "company_terms.json"
    input_path = tmp_path / "docs.jsonl"
    output_path = tmp_path / "enriched.jsonl"
    profile_path.write_text(json.dumps(_company_profile()), encoding="utf-8")
    write_jsonl(input_path, [{"id": "doc_1", "text": "кубер timeout on pg"}])

    exit_code = enrich_jsonl_main(
        [
            str(input_path),
            str(output_path),
            "--profile-file",
            str(profile_path),
            "--no-debug",
        ]
    )

    assert exit_code == 0
    row = json.loads(output_path.read_text(encoding="utf-8").strip())
    assert row["snapshot"]["version"] == "company_terms@v1"
    assert "kubernetes" in row["canonical_values"]
    assert "postgresql" in row["canonical_values"]


def test_load_attribute_profile_accepts_grouped_alias_json_snapshot(tmp_path):
    profile_path = tmp_path / "company_terms_grouped.json"
    profile_path.write_text(
        json.dumps(
            {
                "profile_id": "company_terms",
                "snapshot": {
                    "version": "company_terms@grouped-v1",
                    "source": "file",
                },
                "aliases": [
                    {
                        "slot": "TOOL",
                        "canonical": "kubernetes",
                        "aliases": ["k8s", "kube", "кубер"],
                    },
                    {
                        "slot": "DB",
                        "canonical": "postgresql",
                        "confidence": 0.91,
                        "aliases": [
                            "pg",
                            {"value": "postgres", "confidence": 0.96},
                        ],
                    },
                ],
                "rules": [],
            }
        ),
        encoding="utf-8",
    )

    profile = load_attribute_profile(profile_path)
    pack = extract_attributes("кубер timeout on pg", profile=profile)

    assert pack.profile_id == "company_terms"
    assert pack.snapshot is not None
    assert pack.snapshot.version == "company_terms@grouped-v1"
    values = {item.value for item in pack.attributes}
    assert {"kubernetes", "postgresql"}.issubset(values)
