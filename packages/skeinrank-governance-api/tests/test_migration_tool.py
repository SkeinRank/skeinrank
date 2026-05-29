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
        "tags_total": 0,
        "tags": [],
        "text_fields": ["title", "body"],
        "target_field": "skeinrank",
        "index_name": "platform_kb",
        "binding_policy_status": None,
    }


def test_migration_tool_snapshot_eval_command_writes_report(tmp_path):
    before = {
        "schema_version": "skeinrank.runtime_snapshot_artifact.v1",
        "artifact_type": "runtime_snapshot",
        "binding": {"id": 7, "name": "platform", "index_name": "docs"},
        "profile": {"id": 3, "name": "platform_ops"},
        "runtime_snapshot": {
            "version": "before",
            "checksum": "runtime-before",
            "alias_entries": [
                {
                    "alias_value": "pg",
                    "normalized_alias": "pg",
                    "canonical_value": "page",
                    "normalized_canonical": "page",
                    "slot": "DOCUMENT_COMPONENT",
                    "confidence": 1.0,
                }
            ],
        },
    }
    before["manifest"] = {
        "checksum": runtime_snapshot_artifact_checksum(before),
        "runtime_checksum": "runtime-before",
        "snapshot_source": "latest_profile",
        "snapshot_version": "before",
        "alias_entries_total": 1,
    }
    after = {
        "schema_version": "skeinrank.runtime_snapshot_artifact.v1",
        "artifact_type": "runtime_snapshot",
        "binding": {"id": 7, "name": "platform", "index_name": "docs"},
        "profile": {"id": 3, "name": "platform_ops"},
        "runtime_snapshot": {
            "version": "after",
            "checksum": "runtime-after",
            "alias_entries": [
                {
                    "alias_value": "pg",
                    "normalized_alias": "pg",
                    "canonical_value": "postgresql",
                    "normalized_canonical": "postgresql",
                    "slot": "DATABASE",
                    "confidence": 1.0,
                    "tags": ["backend"],
                }
            ],
        },
    }
    after["manifest"] = {
        "checksum": runtime_snapshot_artifact_checksum(after),
        "runtime_checksum": "runtime-after",
        "snapshot_source": "latest_profile",
        "snapshot_version": "after",
        "alias_entries_total": 1,
    }
    before_path = tmp_path / "before.json"
    after_path = tmp_path / "after.json"
    output_path = tmp_path / "eval.json"
    before_path.write_text(json.dumps(before), encoding="utf-8")
    after_path.write_text(json.dumps(after), encoding="utf-8")

    exit_code = main(
        [
            "snapshot-eval",
            "--before",
            str(before_path),
            "--after",
            str(after_path),
            "--output",
            str(output_path),
            "--compact",
        ]
    )

    assert exit_code == 0
    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert report["schema_version"] == "skeinrank.snapshot_evaluation.v1"
    assert report["aliases"]["changed_total"] == 1
    assert report["queries"]["total"] == 0


def test_migration_tool_lint_command_detects_local_collisions(tmp_path, capsys):
    input_path = tmp_path / "dictionary.json"
    input_path.write_text(
        json.dumps(
            {
                "schema_version": "skeinrank.dictionary.v1",
                "profile_name": "Infra Ops",
                "mode": "upsert",
                "terms": [
                    {
                        "canonical_value": "postgresql",
                        "slot": "database",
                        "aliases": ["pg", "postgresql"],
                    },
                    {
                        "canonical_value": "page",
                        "slot": "document_component",
                        "aliases": ["pg"],
                    },
                ],
                "profile_stop_list": [
                    {"value": "tmp", "target": "alias"},
                    {"value": "tmp", "target": "alias"},
                ],
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(["lint", str(input_path), "--compact"])

    assert exit_code == 2
    report = json.loads(capsys.readouterr().out)
    assert report["schema_version"] == "skeinrank.dictionary_lint.v1"
    assert report["status"] == "invalid"
    assert report["normalized_profile_name"] == "infra_ops"
    assert report["checks"] == {
        "local_only": True,
        "server_state_checked": False,
        "safe_for_apply_decision": False,
    }
    assert report["summary"]["terms_total"] == 2
    assert report["summary"]["aliases_total"] == 3
    assert {issue["code"] for issue in report["errors"]} == {"alias_payload_collision"}
    assert {issue["code"] for issue in report["warnings"]} == {
        "alias_matches_canonical",
        "duplicate_stop_list_entry",
    }


def test_migration_tool_plan_command_writes_server_backed_apply_plan(
    tmp_path, monkeypatch, capsys
):
    input_path = tmp_path / "dictionary.json"
    output_path = tmp_path / "plan.json"
    input_path.write_text(
        json.dumps(
            {
                "schema_version": "skeinrank.dictionary.v1",
                "profile_name": "infra",
                "create_profile": True,
                "terms": [{"canonical_value": "kubernetes", "slot": "tool"}],
            }
        ),
        encoding="utf-8",
    )

    def fake_validate(self, payload):
        assert payload["profile_name"] == "infra"
        return {
            "status": "valid",
            "schema_version": "skeinrank.dictionary.v1",
            "profile_name": "infra",
            "normalized_profile_name": "infra",
            "profile_exists": False,
            "mode": "upsert",
            "summary": {
                "would_create_terms": 1,
                "would_update_terms": 0,
                "would_create_aliases": 0,
                "would_update_aliases": 0,
            },
            "errors": [],
            "warnings": [],
        }

    monkeypatch.setattr(DictionaryMigrationClient, "validate_dictionary", fake_validate)
    monkeypatch.setattr(
        DictionaryMigrationClient,
        "import_dictionary",
        lambda self, payload: pytest.fail("plan must not call import"),
    )

    exit_code = main(["plan", str(input_path), "--output", str(output_path)])

    assert exit_code == 0
    assert capsys.readouterr().out == ""
    plan = json.loads(output_path.read_text(encoding="utf-8"))
    assert plan["schema_version"] == "skeinrank.dictionary_apply_plan.v1"
    assert plan["status"] == "ready"
    assert plan["safe_to_apply"] is True
    assert plan["profile_exists"] is False
    assert plan["operations"] == [
        {
            "action": "create_profile",
            "count": 1,
            "description": "Create the target terminology profile before importing terms.",
        },
        {
            "action": "create_terms",
            "count": 1,
            "description": "Create canonical terms.",
        },
    ]
    assert plan["validation"]["status"] == "valid"


def test_migration_tool_apply_plan_output_validates_before_import(
    tmp_path, monkeypatch, capsys
):
    input_path = tmp_path / "dictionary.json"
    plan_path = tmp_path / "plan.json"
    input_path.write_text('{"profile_name":"infra","terms":[]}', encoding="utf-8")
    calls = []

    def fake_validate(self, payload):
        calls.append("validate")
        return {
            "status": "valid",
            "profile_name": "infra",
            "normalized_profile_name": "infra",
            "profile_exists": True,
            "mode": "upsert",
            "summary": {"would_update_terms": 1},
            "errors": [],
            "warnings": [],
        }

    def fake_import(self, payload):
        calls.append("import")
        return {"status": "applied", "summary": {"updated_terms": 1}}

    monkeypatch.setattr(DictionaryMigrationClient, "validate_dictionary", fake_validate)
    monkeypatch.setattr(DictionaryMigrationClient, "import_dictionary", fake_import)

    exit_code = main(
        [
            "apply",
            str(input_path),
            "--plan-output",
            str(plan_path),
            "--compact",
        ]
    )

    assert exit_code == 0
    assert calls == ["validate", "import"]
    assert json.loads(plan_path.read_text(encoding="utf-8"))["operations"] == [
        {
            "action": "update_terms",
            "count": 1,
            "description": "Update existing canonical terms.",
        }
    ]
    assert capsys.readouterr().out == (
        '{"status":"applied","summary":{"updated_terms":1}}\n'
    )


def test_migration_tool_apply_plan_output_blocks_import_when_plan_invalid(
    tmp_path, monkeypatch, capsys
):
    input_path = tmp_path / "dictionary.json"
    plan_path = tmp_path / "plan.json"
    input_path.write_text('{"profile_name":"infra","terms":[]}', encoding="utf-8")

    def fake_validate(self, payload):
        return {
            "status": "invalid",
            "profile_name": "infra",
            "normalized_profile_name": "infra",
            "profile_exists": True,
            "mode": "upsert",
            "summary": {"errors": 1},
            "errors": [{"code": "alias_existing_collision"}],
            "warnings": [],
        }

    monkeypatch.setattr(DictionaryMigrationClient, "validate_dictionary", fake_validate)
    monkeypatch.setattr(
        DictionaryMigrationClient,
        "import_dictionary",
        lambda self, payload: pytest.fail("blocked apply must not call import"),
    )

    exit_code = main(["apply", str(input_path), "--plan-output", str(plan_path)])

    assert exit_code == 2
    assert capsys.readouterr().out == ""
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    assert plan["status"] == "blocked"
    assert plan["safe_to_apply"] is False
    assert plan["validation"]["errors"] == [{"code": "alias_existing_collision"}]
