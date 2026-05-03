from __future__ import annotations

import pytest
from skeinrank_provider_elasticsearch.enrich_cli import run


class FakeElasticsearchClient:
    def __init__(self):
        self.bulk_calls = []

    def search(self, *, index, body):
        return {
            "hits": {
                "hits": [
                    {
                        "_id": "1",
                        "_index": index,
                        "_source": {"title": "K8s", "body": "k8s timeout"},
                    }
                ]
            }
        }

    def bulk(self, *, operations=None, body=None):
        payload = operations if operations is not None else body
        self.bulk_calls.append(payload)
        return {"errors": False, "items": [{"update": {"_id": "1", "status": 200}}]}


def test_cli_run_requires_explicit_mode():
    with pytest.raises(SystemExit):
        run(
            ["--index", "docs", "--text-field", "body"],
            client=FakeElasticsearchClient(),
        )


def test_cli_run_outputs_compact_dry_run_report_with_fake_client(capsys):
    client = FakeElasticsearchClient()

    report = run(
        [
            "--index",
            "docs",
            "--text-field",
            "title",
            "--text-field",
            "body",
            "--target-field",
            "skeinrank",
            "--limit",
            "1",
            "--dry-run",
        ],
        client=client,
    )

    captured = capsys.readouterr()
    assert '"dry_run": true' in captured.out
    assert report["summary"]["previewed"] == 1
    payload = report["previews"][0]["doc"]["skeinrank"]
    assert payload["canonical_values"]
    assert payload["slots"]
    assert "attributes" not in payload
    assert client.bulk_calls == []


def test_cli_run_can_include_evidence(capsys):
    client = FakeElasticsearchClient()

    report = run(
        [
            "--index",
            "docs",
            "--text-field",
            "body",
            "--limit",
            "1",
            "--include-evidence",
            "--dry-run",
        ],
        client=client,
    )

    captured = capsys.readouterr()
    assert '"include_evidence": true' in captured.out
    payload = report["previews"][0]["doc"]["skeinrank"]
    assert "attributes" in payload
    assert "snapshot" in payload


def test_cli_run_outputs_write_report_with_fake_client(capsys):
    client = FakeElasticsearchClient()

    report = run(
        [
            "--index",
            "docs",
            "--text-field",
            "title",
            "--text-field",
            "body",
            "--target-field",
            "skeinrank",
            "--limit",
            "1",
            "--write",
        ],
        client=client,
    )

    captured = capsys.readouterr()
    assert '"dry_run": false' in captured.out
    assert report["summary"]["updated"] == 1
    assert len(client.bulk_calls) == 1
    payload = client.bulk_calls[0][1]["doc"]["skeinrank"]
    assert "attributes" not in payload


def test_cli_run_can_include_matched_aliases(capsys):
    client = FakeElasticsearchClient()

    report = run(
        [
            "--index",
            "docs",
            "--text-field",
            "body",
            "--limit",
            "1",
            "--include-matched-aliases",
            "--dry-run",
        ],
        client=client,
    )

    captured = capsys.readouterr()
    assert '"include_matched_aliases": true' in captured.out
    payload = report["previews"][0]["doc"]["skeinrank"]
    assert payload["matched_aliases"] == ["k8s"]
    assert payload["matched_aliases_by_value"] == {"kubernetes": ["k8s"]}
    assert "attributes" not in payload
