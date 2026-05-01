import json

from skeinrank import write_jsonl
from skeinrank.attributes.cli import enrich_jsonl_main, eval_demo_main, extract_main


def test_extract_cli_prints_compact_attribute_payload(capsys):
    exit_code = extract_main(
        ["--text", "kube api timeout after k8s upgrade", "--compact"]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["profile_id"] == "default_it"
    assert payload["snapshot_version"] == "default_it@2026-04-29-v1"
    assert payload["alias_matcher_backend"] == "aho_corasick"
    assert "kubernetes" in payload["canonical_values"]
    assert payload["slots"]["TOOL"] == ["kubernetes"]


def test_extract_cli_debug_includes_passport_without_inactive_model_stages(capsys):
    exit_code = extract_main(["--text", "k8s timeout", "--debug"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert "passport" in payload
    assert payload["passport"]["alias_matcher_backend"] == "aho_corasick"
    assert "stage_status" not in payload["passport"]


def test_enrich_jsonl_cli_writes_output(tmp_path, capsys):
    input_path = tmp_path / "docs.jsonl"
    output_path = tmp_path / "enriched.jsonl"
    write_jsonl(
        input_path,
        [
            {
                "id": "doc_001",
                "title": "Kubernetes timeout",
                "text": "k8s timeout on api-server after upgrade to 1.28",
            }
        ],
    )

    exit_code = enrich_jsonl_main([str(input_path), str(output_path), "--no-debug"])

    assert exit_code == 0
    assert "enriched_documents=1" in capsys.readouterr().out
    row = json.loads(output_path.read_text(encoding="utf-8").strip())
    assert "kubernetes" in row["canonical_values"]
    assert row["passport"] is None


def test_eval_demo_cli_writes_report(tmp_path, capsys):
    docs_path = tmp_path / "docs.jsonl"
    enriched_path = tmp_path / "enriched.jsonl"
    queries_path = tmp_path / "queries.jsonl"
    report_path = tmp_path / "report.json"

    write_jsonl(
        docs_path,
        [
            {
                "id": "doc_001",
                "title": "Kubernetes api-server timeout",
                "text": "k8s timeout after upgrade to 1.28",
            }
        ],
    )
    assert enrich_jsonl_main([str(docs_path), str(enriched_path), "--no-debug"]) == 0
    capsys.readouterr()
    write_jsonl(
        queries_path, [{"id": "q_001", "text": "kube timeout", "relevant": ["doc_001"]}]
    )

    exit_code = eval_demo_main(
        [str(queries_path), str(enriched_path), "--out", str(report_path), "--compact"]
    )

    assert exit_code == 0
    stdout = capsys.readouterr().out
    summary = json.loads(stdout.splitlines()[0])
    assert summary["total_queries"] == 1
    assert report_path.exists()
