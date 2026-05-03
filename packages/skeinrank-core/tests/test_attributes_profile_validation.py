import json

from skeinrank import build_attribute_profile, validate_attribute_profile
from skeinrank.attributes.cli import validate_profile_main


def test_validate_attribute_profile_accepts_clean_profile():
    profile = build_attribute_profile(
        profile_id="company_terms",
        aliases={
            "kubernetes": ["k8s", "kube"],
            "postgresql": ["postgres", "psql"],
        },
        slots={
            "kubernetes": "TOOL",
            "postgresql": "DB",
        },
        snapshot_version="company_terms@v1",
    )

    report = validate_attribute_profile(profile)

    assert report.ok is True
    assert report.error_count == 0
    assert report.warning_count == 0


def test_validate_attribute_profile_reports_alias_collision():
    profile = {
        "profile_id": "company_terms",
        "aliases": [
            {"slot": "DB", "canonical": "postgresql", "alias": "pg"},
            {"slot": "COMPONENT", "canonical": "payment-gateway", "alias": "pg"},
        ],
        "rules": [],
    }

    report = validate_attribute_profile(profile)

    assert report.ok is False
    assert report.error_count == 1
    issue = next(item for item in report.issues if item.code == "alias_collision")
    assert issue.alias == "pg"
    assert {target["canonical"] for target in issue.details["targets"]} == {
        "postgresql",
        "payment-gateway",
    }


def test_validate_attribute_profile_warns_about_generic_and_short_aliases():
    profile = {
        "profile_id": "company_terms",
        "aliases": [
            {"slot": "COMPONENT", "canonical": "api-server", "alias": "api"},
            {"slot": "DB", "canonical": "postgresql", "alias": "pg"},
        ],
        "rules": [],
    }

    report = validate_attribute_profile(profile)

    assert report.ok is True
    assert report.error_count == 0
    codes = {issue.code for issue in report.issues}
    assert "generic_alias" in codes
    assert "short_alias" in codes


def test_validate_attribute_profile_accepts_grouped_aliases():
    profile = {
        "profile_id": "company_terms",
        "aliases": [
            {
                "slot": "TOOL",
                "canonical": "kubernetes",
                "aliases": ["k8s", "kube", "kuber"],
            }
        ],
        "rules": [],
    }

    report = validate_attribute_profile(profile)

    assert report.ok is True
    assert report.error_count == 0


def test_validate_profile_cli_outputs_json_report(tmp_path, capsys):
    profile_path = tmp_path / "company_terms.json"
    profile_path.write_text(
        json.dumps(
            {
                "profile_id": "company_terms",
                "aliases": [{"slot": "DB", "canonical": "postgresql", "alias": "pg"}],
                "rules": [],
            }
        ),
        encoding="utf-8",
    )

    exit_code = validate_profile_main([str(profile_path), "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["profile_id"] == "company_terms"
    assert payload["ok"] is True
    assert payload["warning_count"] == 1
    assert payload["issues"][0]["code"] == "short_alias"


def test_validate_profile_cli_strict_fails_on_warnings(tmp_path):
    profile_path = tmp_path / "company_terms.json"
    profile_path.write_text(
        json.dumps(
            {
                "profile_id": "company_terms",
                "aliases": [{"slot": "DB", "canonical": "postgresql", "alias": "pg"}],
                "rules": [],
            }
        ),
        encoding="utf-8",
    )

    assert validate_profile_main([str(profile_path), "--strict"]) == 1
