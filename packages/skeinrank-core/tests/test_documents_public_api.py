import zipfile
from pathlib import Path

import pytest
from skeinrank import (
    DocumentExtractionError,
    DocumentExtractionResult,
    DocumentText,
    extract_document_text,
    extract_terms_from_document,
    load_document_text,
)


def _dictionary_payload():
    return {
        "profile_name": "infra_incidents",
        "terms": [
            {
                "canonical_value": "kubernetes",
                "slot": "TOOL",
                "aliases": ["k8s", "kube"],
            },
            {
                "canonical_value": "postgresql",
                "slot": "DATABASE",
                "aliases": ["pg", "postgres"],
            },
        ],
    }


def _write_minimal_docx(path: Path, paragraphs: list[str]) -> None:
    paragraph_xml = "".join(
        f"<w:p><w:r><w:t>{text}</w:t></w:r></w:p>" for text in paragraphs
    )
    document_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>{paragraph_xml}</w:body>
</w:document>
"""
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", document_xml)


def test_document_symbols_are_exported_from_public_api():
    assert DocumentText is not None
    assert DocumentExtractionResult is not None
    assert DocumentExtractionError is not None
    assert callable(load_document_text)
    assert callable(extract_document_text)
    assert callable(extract_terms_from_document)


def test_load_document_text_reads_text_like_files(tmp_path: Path):
    path = tmp_path / "incident.md"
    path.write_text("Deploy 500 k8s servers\nBacked by pg", encoding="utf-8")

    document = extract_document_text(path)

    assert document.file_name == "incident.md"
    assert document.suffix == ".md"
    assert document.metadata["extractor"] == "text"
    assert document.char_count == len(document.text)
    assert document.line_count == 2
    assert load_document_text(path) == "Deploy 500 k8s servers\nBacked by pg"


def test_extract_document_text_strips_html_and_ignores_script_style(tmp_path: Path):
    path = tmp_path / "incident.html"
    path.write_text(
        """
        <html><head><style>.hidden{display:none}</style></head>
        <body><h1>K8s outage</h1><p>Postgres latency spike</p><script>ignore()</script></body></html>
        """,
        encoding="utf-8",
    )

    text = load_document_text(path)

    assert "K8s outage" in text
    assert "Postgres latency spike" in text
    assert "ignore" not in text
    assert "hidden" not in text


def test_extract_document_text_reads_docx_with_stdlib(tmp_path: Path):
    path = tmp_path / "runbook.docx"
    _write_minimal_docx(path, ["K8s rollout", "pg database checklist"])

    document = extract_document_text(path)

    assert document.text == "K8s rollout\npg database checklist"
    assert document.metadata["extractor"] == "docx-stdlib"
    assert document.metadata["paragraph_count"] == 2


def test_extract_terms_from_document_returns_document_and_matches(tmp_path: Path):
    path = tmp_path / "incident.txt"
    path.write_text("k8s rollout uses pg database", encoding="utf-8")

    result = extract_terms_from_document(path, dictionary=_dictionary_payload())

    assert result.document.file_name == "incident.txt"
    assert result.extraction.canonical_values == ["kubernetes", "postgresql"]
    assert result.match_count == 2
    assert "<mark>k8s</mark>" in result.extraction.matches[0].highlighted_fragment


def test_extract_document_text_rejects_unknown_extension(tmp_path: Path):
    path = tmp_path / "incident.bin"
    path.write_bytes(b"k8s")

    with pytest.raises(DocumentExtractionError, match="Unsupported document type"):
        extract_document_text(path)


def test_extract_document_text_reports_missing_pdf_dependency(
    tmp_path: Path, monkeypatch
):
    path = tmp_path / "incident.pdf"
    path.write_bytes(b"%PDF-1.4\n")

    def _missing_pypdf(name: str):
        if name == "pypdf":
            raise ModuleNotFoundError(name)
        raise AssertionError(name)

    monkeypatch.setattr("skeinrank.documents.import_module", _missing_pypdf)

    with pytest.raises(DocumentExtractionError, match="requires the optional 'pypdf'"):
        extract_document_text(path)
