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


def test_validate_attribute_profile_strict_elevates_governance_warnings():
    profile = {
        "profile_id": "company_terms",
        "aliases": [{"slot": "DB", "canonical": "postgresql", "alias": "pg"}],
        "rules": [],
    }

    report = validate_attribute_profile(profile, strict=True)

    assert report.ok is False
    assert report.publishable is False
    assert report.strict is True
    assert report.error_count == 1
    issue = report.issues[0]
    assert issue.code == "short_alias"
    assert issue.severity == "error"
    assert issue.details["strict_elevated"] is True


def test_validate_attribute_profile_reports_non_active_alias_status_without_collision():
    profile = {
        "profile_id": "company_terms",
        "aliases": [
            {
                "slot": "TOOL",
                "canonical": "kubernetes",
                "aliases": ["k8s", "kube"],
            },
            {
                "slot": "DB",
                "canonical": "postgresql",
                "aliases": [{"value": "pg", "status": "ambiguous"}],
            },
            {
                "slot": "COMPONENT",
                "canonical": "payment-gateway",
                "aliases": [{"value": "pg", "status": "ambiguous"}],
            },
        ],
        "rules": [],
    }

    report = validate_attribute_profile(profile)

    assert report.ok is True
    codes = {issue.code for issue in report.issues}
    assert "ambiguous_alias_status" in codes
    assert "alias_collision" not in codes


def test_validate_attribute_profile_strict_blocks_pending_aliases():
    profile = {
        "profile_id": "company_terms",
        "aliases": [
            {
                "slot": "TOOL",
                "canonical": "kubernetes",
                "aliases": ["k8s", {"value": "kub", "status": "pending"}],
            }
        ],
        "rules": [],
    }

    report = validate_attribute_profile(profile, strict=True)

    assert report.ok is False
    assert any(issue.code == "pending_alias_status" for issue in report.issues)


def test_validate_attribute_profile_rejects_unknown_alias_status():
    profile = {
        "profile_id": "company_terms",
        "aliases": [
            {
                "slot": "TOOL",
                "canonical": "kubernetes",
                "aliases": [{"value": "k8s", "status": "ready"}],
            }
        ],
        "rules": [],
    }

    report = validate_attribute_profile(profile)

    assert report.ok is False
    issue = next(item for item in report.issues if item.code == "invalid_alias_status")
    assert issue.details["status"] == "ready"


def test_validate_profile_cli_json_strict_reports_elevated_error(tmp_path, capsys):
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

    exit_code = validate_profile_main([str(profile_path), "--json", "--strict"])

    assert exit_code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["strict"] is True
    assert payload["ok"] is False
    assert payload["error_count"] == 1
    assert payload["issues"][0]["details"]["strict_elevated"] is True


def test_validate_attribute_profile_rejects_invalid_alias_value():
    profile = {
        "profile_id": "company_terms",
        "aliases": [
            {"slot": "TOOL", "canonical": "kubernetes", "alias": "!!!"},
        ],
        "rules": [],
    }

    report = validate_attribute_profile(profile)

    assert report.ok is False
    assert any(issue.code == "invalid_alias_value" for issue in report.issues)
