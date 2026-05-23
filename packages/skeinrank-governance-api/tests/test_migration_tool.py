from __future__ import annotations

import json
from urllib.error import HTTPError

import pytest
from skeinrank_governance_api import migration_tool
from skeinrank_governance_api.migration_tool import (
    DictionaryMigrationClient,
    MigrationToolError,
    main,
)
from skeinrank_governance_api.runtime_snapshots import (
    runtime_snapshot_artifact_checksum,
)


class _FakeResponse:
    def __init__(self, payload: dict):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class _FakeHttpError(HTTPError):
    def __init__(self):
        super().__init__(
            url="http://example.test/v1/console/dictionary/import",
            code=422,
            msg="Unprocessable Entity",
            hdrs=None,
            fp=None,
        )

    def read(self) -> bytes:
        return b'{"detail":"invalid"}'


def test_dictionary_migration_client_validates_payload(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["method"] = request.get_method()
        captured["timeout"] = timeout
        captured["headers"] = dict(request.header_items())
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return _FakeResponse({"status": "valid"})

    monkeypatch.setattr(migration_tool, "urlopen", fake_urlopen)
    client = DictionaryMigrationClient(
        "http://api.example.test/",
        token="secret-token",
        timeout=9,
    )

    result = client.validate_dictionary({"profile_name": "infra", "terms": []})

    assert result == {"status": "valid"}
    assert captured["url"] == "http://api.example.test/v1/console/dictionary/validate"
    assert captured["method"] == "POST"
    assert captured["timeout"] == 9
    assert captured["headers"]["Authorization"] == "Bearer secret-token"
    assert captured["headers"]["Content-type"] == "application/json"
    assert captured["body"] == {"profile_name": "infra", "terms": []}


def test_dictionary_migration_client_exports_profile(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["method"] = request.get_method()
        return _FakeResponse({"profile_name": "infra", "terms": []})

    monkeypatch.setattr(migration_tool, "urlopen", fake_urlopen)
    client = DictionaryMigrationClient("http://api.example.test")

    result = client.export_dictionary("infra incidents", include_global_stop_list=False)

    assert result == {"profile_name": "infra", "terms": []}
    assert captured["method"] == "GET"
    assert captured["url"] == (
        "http://api.example.test/v1/console/dictionary/export?"
        "profile_name=infra+incidents&include_global_stop_list=false"
    )


def test_dictionary_migration_client_raises_for_http_errors(monkeypatch):
    def fake_urlopen(request, timeout):
        raise _FakeHttpError()

    monkeypatch.setattr(migration_tool, "urlopen", fake_urlopen)
    client = DictionaryMigrationClient("http://api.example.test")

    with pytest.raises(MigrationToolError) as exc_info:
        client.import_dictionary({"profile_name": "infra"})

    assert exc_info.value.status_code == 422
    assert "HTTP 422" in str(exc_info.value)
    assert exc_info.value.response_body == '{"detail":"invalid"}'


def test_migration_tool_validate_command_writes_report(tmp_path, monkeypatch, capsys):
    input_path = tmp_path / "dictionary.json"
    output_path = tmp_path / "report.json"
    input_path.write_text('{"profile_name":"infra","terms":[]}', encoding="utf-8")

    def fake_validate(self, payload):
        assert payload == {"profile_name": "infra", "terms": []}
        return {"status": "valid", "summary": {"terms_total": 0}}

    monkeypatch.setattr(DictionaryMigrationClient, "validate_dictionary", fake_validate)

    exit_code = main(["validate", str(input_path), "--output", str(output_path)])

    assert exit_code == 0
    assert capsys.readouterr().out == ""
    assert json.loads(output_path.read_text(encoding="utf-8")) == {
        "status": "valid",
        "summary": {"terms_total": 0},
    }


def test_migration_tool_validate_returns_nonzero_for_invalid_report(
    tmp_path,
    monkeypatch,
    capsys,
):
    input_path = tmp_path / "dictionary.json"
    input_path.write_text('{"profile_name":"infra","terms":[]}', encoding="utf-8")

    def fake_validate(self, payload):
        return {"status": "invalid", "errors": [{"code": "alias_collision"}]}

    monkeypatch.setattr(DictionaryMigrationClient, "validate_dictionary", fake_validate)

    exit_code = main(["validate", str(input_path)])

    assert exit_code == 2
    assert '"status": "invalid"' in capsys.readouterr().out


def test_migration_tool_apply_command_prints_import_report(
    tmp_path, monkeypatch, capsys
):
    input_path = tmp_path / "dictionary.json"
    input_path.write_text('{"profile_name":"infra","terms":[]}', encoding="utf-8")

    def fake_import(self, payload):
        return {"status": "applied", "summary": {"created_terms": 0}}

    monkeypatch.setattr(DictionaryMigrationClient, "import_dictionary", fake_import)

    exit_code = main(["apply", str(input_path), "--compact"])

    assert exit_code == 0
    assert capsys.readouterr().out == (
        '{"status":"applied","summary":{"created_terms":0}}\n'
    )


def test_migration_tool_export_command_writes_dictionary(tmp_path, monkeypatch):
    output_path = tmp_path / "export.json"

    def fake_export(self, profile_name, *, include_global_stop_list=True):
        assert profile_name == "infra"
        assert include_global_stop_list is False
        return {"profile_name": "infra", "terms": []}

    monkeypatch.setattr(DictionaryMigrationClient, "export_dictionary", fake_export)

    exit_code = main(
        [
            "export",
            "--profile-name",
            "infra",
            "--no-global-stop-list",
            "--output",
            str(output_path),
        ]
    )

    assert exit_code == 0
    assert json.loads(output_path.read_text(encoding="utf-8")) == {
        "profile_name": "infra",
        "terms": [],
    }


def test_migration_tool_validate_command_reads_yaml(tmp_path, monkeypatch, capsys):
    pytest.importorskip("yaml")
    input_path = tmp_path / "dictionary.yaml"
    input_path.write_text(
        "schema_version: skeinrank.dictionary.v1\n"
        "profile_name: infra\n"
        "terms:\n"
        "  - canonical_value: kubernetes\n"
        "    slot: TOOL\n"
        "    aliases:\n"
        "      - k8s\n",
        encoding="utf-8",
    )

    def fake_validate(self, payload):
        assert payload == {
            "schema_version": "skeinrank.dictionary.v1",
            "profile_name": "infra",
            "terms": [
                {
                    "canonical_value": "kubernetes",
                    "slot": "TOOL",
                    "aliases": ["k8s"],
                }
            ],
        }
        return {"status": "valid"}

    monkeypatch.setattr(DictionaryMigrationClient, "validate_dictionary", fake_validate)

    exit_code = main(["validate", str(input_path), "--compact"])

    assert exit_code == 0
    assert capsys.readouterr().out == '{"status":"valid"}\n'


def test_dictionary_migration_client_exports_snapshot_artifact(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["method"] = request.get_method()
        return _FakeResponse(
            {"schema_version": "skeinrank.runtime_snapshot_artifact.v1"}
        )

    monkeypatch.setattr(migration_tool, "urlopen", fake_urlopen)
    client = DictionaryMigrationClient("http://api.example.test")

    result = client.export_snapshot_artifact(
        7,
        source="runtime",
        snapshot_version="platform_ops@v1",
        description="release candidate",
    )

    assert result == {"schema_version": "skeinrank.runtime_snapshot_artifact.v1"}
    assert captured["method"] == "GET"
    assert captured["url"] == (
        "http://api.example.test/v1/headless/snapshots/export?"
        "binding_id=7&source=runtime&snapshot_version=platform_ops%40v1&"
        "description=release+candidate"
    )


def test_migration_tool_snapshot_export_command_writes_artifact(tmp_path, monkeypatch):
    output_path = tmp_path / "runtime-snapshot.json"

    def fake_export_snapshot_artifact(
        self,
        binding_id,
        *,
        source="latest",
        snapshot_version=None,
        description=None,
    ):
        assert binding_id == 7
        assert source == "latest"
        assert snapshot_version == "platform_ops@v1"
        assert description == "release candidate"
        return {
            "schema_version": "skeinrank.runtime_snapshot_artifact.v1",
            "binding": {"id": 7},
        }

    monkeypatch.setattr(
        DictionaryMigrationClient,
        "export_snapshot_artifact",
        fake_export_snapshot_artifact,
    )

    exit_code = main(
        [
            "snapshot-export",
            "--binding-id",
            "7",
            "--snapshot-version",
            "platform_ops@v1",
            "--description",
            "release candidate",
            "--output",
            str(output_path),
        ]
    )

    assert exit_code == 0
    assert json.loads(output_path.read_text(encoding="utf-8")) == {
        "schema_version": "skeinrank.runtime_snapshot_artifact.v1",
        "binding": {"id": 7},
    }


def test_migration_tool_snapshot_inspect_command_summarizes_local_artifact(
    tmp_path, capsys
):
    artifact = {
        "schema_version": "skeinrank.runtime_snapshot_artifact.v1",
        "artifact_type": "runtime_snapshot",
        "binding": {
            "id": 7,
            "name": "platform knowledge base",
            "index_name": "platform_kb",
            "text_fields": ["title", "body"],
            "target_field": "skeinrank",
        },
        "profile": {"id": 3, "name": "platform_ops"},
        "runtime_snapshot": {
            "version": "platform_ops@v1",
            "checksum": "runtime-checksum",
            "alias_entries": [
                {
                    "alias_value": "k8s",
                    "normalized_alias": "k8s",
                    "canonical_value": "kubernetes",
                    "normalized_canonical": "kubernetes",
                    "slot": "TOOL",
                    "confidence": 1.0,
                }
            ],
        },
    }
    artifact["manifest"] = {
        "checksum": runtime_snapshot_artifact_checksum(artifact),
        "runtime_checksum": "runtime-checksum",
        "snapshot_source": "latest_profile",
        "snapshot_version": "platform_ops@v1",
        "alias_entries_total": 1,
    }
    artifact_path = tmp_path / "runtime-snapshot.json"
    artifact_path.write_text(json.dumps(artifact), encoding="utf-8")

    exit_code = main(["snapshot-inspect", str(artifact_path), "--compact"])

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out) == {
        "schema_version": "skeinrank.runtime_snapshot_artifact.v1",
        "artifact_type": "runtime_snapshot",
        "path": str(artifact_path.resolve()),
        "binding_id": 7,
        "binding_name": "platform knowledge base",
        "profile_name": "platform_ops",
        "snapshot_version": "platform_ops@v1",
        "checksum": artifact["manifest"]["checksum"],
        "runtime_checksum": "runtime-checksum",
        "snapshot_source": "latest_profile",
        "alias_entries_total": 1,
        "text_fields": ["title", "body"],
        "target_field": "skeinrank",
        "index_name": "platform_kb",
    }
