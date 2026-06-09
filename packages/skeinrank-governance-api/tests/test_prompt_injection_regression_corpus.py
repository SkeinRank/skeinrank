from __future__ import annotations

import json
from pathlib import Path

from skeinrank_governance_api.prompt_injection import (
    PROMPT_INJECTION_REGRESSION_CASE_SCHEMA_VERSION,
    evaluate_prompt_injection_regression_case,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
CORPUS_PATH = REPO_ROOT / "examples/security/prompt_injection_corpus.jsonl"
CORPUS_DOC = REPO_ROOT / "docs/security/prompt-injection-regression-corpus.md"
ROOT_README = REPO_ROOT / "README.md"
DOCS_README = REPO_ROOT / "docs/README.md"
PROMPT_INJECTION_DOC = REPO_ROOT / "docs/security/prompt-injection.md"
PROMPT_LIKE_DETECTOR_DOC = REPO_ROOT / "docs/security/prompt-like-detector.md"
DEPLOYMENT_SECURITY_DOC = REPO_ROOT / "docs/deployment/security.md"
MCP_KIT_DOC = REPO_ROOT / "docs/deployment/mcp-integration-kit.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _load_corpus() -> list[dict]:
    records: list[dict] = []
    for line_number, line in enumerate(_read(CORPUS_PATH).splitlines(), start=1):
        line = line.strip()
        assert line, f"empty JSONL line at {line_number}"
        records.append(json.loads(line))
    return records


def test_prompt_injection_regression_corpus_exists_and_uses_stable_schema() -> None:
    assert CORPUS_PATH.exists()
    records = _load_corpus()
    assert len(records) >= 8

    case_ids = [record["id"] for record in records]
    assert len(case_ids) == len(set(case_ids))

    for record in records:
        assert (
            record["schema_version"] == PROMPT_INJECTION_REGRESSION_CASE_SCHEMA_VERSION
        )
        assert record["surface"]
        assert record["expected_status"] in {"clear", "review_required"}
        assert isinstance(record.get("expected_risk_codes"), list)
        assert "text" in record or "payload" in record


def test_prompt_injection_regression_corpus_matches_detector_contract() -> None:
    failures: list[dict] = []
    for record in _load_corpus():
        result = evaluate_prompt_injection_regression_case(record)
        if not result["passed"]:
            failures.append(result)

    assert failures == []


def test_prompt_injection_regression_corpus_covers_key_risk_families() -> None:
    records = _load_corpus()
    expected_codes = {
        code for record in records for code in record.get("expected_risk_codes", [])
    }

    assert {
        "prompt_like_instruction",
        "hidden_prompt_request",
        "secret_exfiltration_request",
        "tool_injection_request",
        "destructive_action_request",
        "html_instruction_comment",
    }.issubset(expected_codes)
    assert any(record["expected_status"] == "clear" for record in records)
    assert any(record["surface"] == "dictionary_import" for record in records)
    assert any("payload" in record for record in records)


def test_prompt_injection_regression_corpus_docs_are_product_facing() -> None:
    assert CORPUS_DOC.exists()
    content = _read(CORPUS_DOC)

    for fragment in (
        "Prompt injection regression corpus",
        "examples/security/prompt_injection_corpus.jsonl",
        "skeinrank.prompt_injection_regression_case.v1",
        "User query",
        "Retrieved document",
        "Dictionary import",
        "Agent proposal",
        "Benign terminology",
        "expected_risk_codes",
        "poetry run python -m pytest tests/test_prompt_injection_regression_corpus.py -q",
    ):
        assert fragment in content

    assert "Patch" not in content


def test_prompt_injection_regression_corpus_is_linked_from_security_docs() -> None:
    expected_refs = (
        "docs/security/prompt-injection-regression-corpus.md",
        "security/prompt-injection-regression-corpus.md",
        "prompt-injection-regression-corpus.md",
        "../security/prompt-injection-regression-corpus.md",
    )

    assert expected_refs[1] in _read(DOCS_README)
    assert expected_refs[2] in _read(PROMPT_INJECTION_DOC)
    assert expected_refs[2] in _read(PROMPT_LIKE_DETECTOR_DOC)
    assert expected_refs[3] in _read(DEPLOYMENT_SECURITY_DOC)
    assert expected_refs[3] in _read(MCP_KIT_DOC)
