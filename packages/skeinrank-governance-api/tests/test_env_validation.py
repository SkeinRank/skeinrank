from __future__ import annotations

from pathlib import Path

from skeinrank_governance_api.env_validation import (
    load_env_file,
    main,
    validate_env_file,
    validate_env_values,
)


def _valid_values() -> dict[str, str]:
    return {
        "POSTGRES_DB": "skeinrank",
        "POSTGRES_USER": "skeinrank",
        "POSTGRES_PASSWORD": "strong-postgres-password-123",
        "RABBITMQ_DEFAULT_USER": "skeinrank",
        "RABBITMQ_DEFAULT_PASS": "strong-rabbit-password-123",
        "SKEINRANK_ENV": "production",
        "SKEINRANK_GOVERNANCE_API_ENV": "production",
        "SKEINRANK_GOVERNANCE_API_AUTH_ENABLED": "true",
        "SKEINRANK_GOVERNANCE_API_PRODUCTION_SECURITY_ENABLED": "true",
        "SKEINRANK_GOVERNANCE_API_ADMIN_PASSWORD": "strong-admin-password-123",
        "SKEINRANK_GOVERNANCE_API_CORS_ORIGINS": "https://skeinrank.company.test",
        "VITE_SKEINRANK_GOVERNANCE_API_URL": "https://skeinrank-api.company.test",
        "GRAFANA_ADMIN_PASSWORD": "strong-grafana-password-123",
        "SKEINRANK_GOVERNANCE_API_LOG_FORMAT": "json",
    }


def test_env_validation_accepts_first_bootstrap_without_elasticsearch() -> None:
    report = validate_env_values(_valid_values())

    assert report["status"] == "warning"
    assert report["summary"]["errors"] == 0
    assert report["summary"]["warnings"] == 1
    assert report["summary"]["elasticsearch_configured"] is False
    assert report["warnings"][0]["key"] == "SKEINRANK_GOVERNANCE_API_ELASTICSEARCH_URL"


def test_env_validation_strict_fails_on_warnings() -> None:
    report = validate_env_values(_valid_values(), strict=True)

    assert report["status"] == "failed"
    assert report["summary"]["errors"] == 0
    assert report["summary"]["warnings"] == 1


def test_env_validation_rejects_placeholders_and_example_elasticsearch_url() -> None:
    values = _valid_values()
    values["POSTGRES_PASSWORD"] = "CHANGE_ME_STRONG_POSTGRES_PASSWORD"
    values["SKEINRANK_GOVERNANCE_API_ELASTICSEARCH_URL"] = (
        "https://elasticsearch.example.com:9200"
    )

    report = validate_env_values(values)

    assert report["status"] == "failed"
    error_keys = {item["key"] for item in report["errors"]}
    assert "POSTGRES_PASSWORD" in error_keys
    assert "SKEINRANK_GOVERNANCE_API_ELASTICSEARCH_URL" in error_keys


def test_env_validation_rejects_missing_required_values() -> None:
    values = _valid_values()
    values.pop("POSTGRES_PASSWORD")
    values["SKEINRANK_GOVERNANCE_API_CORS_ORIGINS"] = "*"

    report = validate_env_values(values)

    assert report["status"] == "failed"
    messages = "\n".join(item["message"] for item in report["errors"])
    assert "required production Compose setting" in messages
    assert "wildcard CORS" in messages


def test_env_file_parser_supports_comments_export_and_quotes(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            (
                "# comment",
                "export POSTGRES_DB=skeinrank",
                "POSTGRES_USER='skeinrank'",
                'POSTGRES_PASSWORD="strong-postgres-password-123"',
            )
        ),
        encoding="utf-8",
    )

    values = load_env_file(env_path)

    assert values == {
        "POSTGRES_DB": "skeinrank",
        "POSTGRES_USER": "skeinrank",
        "POSTGRES_PASSWORD": "strong-postgres-password-123",
    }


def test_env_validation_cli_returns_nonzero_for_example_file() -> None:
    repo_root = Path(__file__).resolve().parents[3]

    exit_code = main(["validate", "--file", str(repo_root / ".env.production.example")])

    assert exit_code == 1


def test_env_validation_file_reports_source(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(f"{key}={value}" for key, value in _valid_values().items()),
        encoding="utf-8",
    )

    report = validate_env_file(env_path)

    assert report["source"] == str(env_path)
    assert report["format_version"] == "skeinrank.env_validation.v1"
