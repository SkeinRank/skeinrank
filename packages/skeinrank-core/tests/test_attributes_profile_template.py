import json

import pytest
from skeinrank import (
    build_attribute_profile_template,
    extract_attributes,
    load_attribute_profile,
    validate_attribute_profile,
    write_attribute_profile_template,
)
from skeinrank.attributes.cli import init_profile_main


def test_build_attribute_profile_template_returns_valid_grouped_profile():
    profile = build_attribute_profile_template(profile_id="company_terms")

    assert profile["profile_id"] == "company_terms"
    assert profile["snapshot"]["version"] == "company_terms@v1"
    assert profile["alias_matcher"]["backend"] == "aho_corasick"
    assert any(item["canonical"] == "kubernetes" for item in profile["aliases"])

    report = validate_attribute_profile(profile)
    assert report.ok is True
    # The starter profile intentionally includes pg as a useful short alias.
    assert {issue.code for issue in report.issues} <= {"short_alias"}


def test_write_attribute_profile_template_creates_usable_profile(tmp_path):
    profile_path = tmp_path / "company_terms.json"

    output = write_attribute_profile_template(profile_path)

    assert output == profile_path
    profile = load_attribute_profile(profile_path)
    assert profile["profile_id"] == "company_terms"
    pack = extract_attributes("kuber timeout on pg", profile=profile)
    values = {item.value for item in pack.attributes}
    assert {"kubernetes", "postgresql"}.issubset(values)


def test_write_attribute_profile_template_refuses_overwrite(tmp_path):
    profile_path = tmp_path / "company_terms.json"
    profile_path.write_text("{}", encoding="utf-8")

    with pytest.raises(FileExistsError):
        write_attribute_profile_template(profile_path)


def test_init_profile_cli_creates_valid_profile_file(tmp_path, capsys):
    profile_path = tmp_path / "team_terms.json"

    exit_code = init_profile_main([str(profile_path)])

    assert exit_code == 0
    stdout = capsys.readouterr().out
    assert f"created_profile={profile_path}" in stdout
    assert "profile_id=team_terms" in stdout
    assert profile_path.exists()

    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    assert profile["profile_id"] == "team_terms"
    assert profile["snapshot"]["version"] == "team_terms@v1"
    assert validate_attribute_profile(profile).ok is True


def test_init_profile_cli_supports_custom_metadata(tmp_path):
    profile_path = tmp_path / "company_terms.json"

    assert (
        init_profile_main(
            [
                str(profile_path),
                "--profile-id",
                "platform_terms",
                "--snapshot-version",
                "platform_terms@2026-05-03-v1",
                "--description",
                "Platform team terminology profile.",
            ]
        )
        == 0
    )

    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    assert profile["profile_id"] == "platform_terms"
    assert profile["description"] == "Platform team terminology profile."
    assert profile["snapshot"]["version"] == "platform_terms@2026-05-03-v1"
