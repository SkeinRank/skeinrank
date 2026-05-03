from __future__ import annotations

import json

from skeinrank import build_attribute_profile
from skeinrank_provider_elasticsearch.enrich_cli import run


class FakeElasticsearchClient:
    def search(self, *, index, body):
        return {
            "hits": {
                "hits": [
                    {
                        "_id": "1",
                        "_index": index,
                        "_source": {"body": "кубер timeout on pg"},
                    }
                ]
            }
        }


def test_elasticsearch_cli_accepts_profile_file(tmp_path, capsys):
    profile = build_attribute_profile(
        profile_id="company_terms",
        aliases={"kubernetes": ["кубер"], "postgresql": ["pg"]},
        slots={"kubernetes": "TOOL", "postgresql": "DB"},
        snapshot_version="company_terms@v1",
    )
    profile_path = tmp_path / "company_terms.json"
    profile_path.write_text(json.dumps(profile), encoding="utf-8")

    report = run(
        [
            "--index",
            "docs",
            "--text-field",
            "body",
            "--profile-file",
            str(profile_path),
            "--dry-run",
        ],
        client=FakeElasticsearchClient(),
    )

    captured = capsys.readouterr()
    assert '"profile": "company_terms"' in captured.out
    payload = report["previews"][0]["doc"]["skeinrank"]
    assert payload["snapshot_version"] == "company_terms@v1"
    assert "kubernetes" in payload["canonical_values"]
    assert "postgresql" in payload["canonical_values"]
