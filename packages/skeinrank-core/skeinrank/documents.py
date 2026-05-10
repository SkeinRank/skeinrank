"""Document text extraction utilities for the lightweight SkeinRank SDK.

The helpers in this module are intentionally local and dependency-light. They
support common text-like formats and DOCX using the Python standard library. PDF
support is available when ``pypdf`` is installed by the caller.
"""

from __future__ import annotations

import html
import mimetypes
import re
import zipfile
from collections.abc import Mapping
from html.parser import HTMLParser
from importlib import import_module
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from pydantic import BaseModel, Field, field_validator

from .sdk import Dictionary, ExtractionResult, extract_terms

_TEXT_SUFFIXES = frozenset(
    {
        ".txt",
        ".md",
        ".markdown",
        ".rst",
        ".log",
        ".csv",
        ".tsv",
        ".json",
        ".jsonl",
        ".yaml",
        ".yml",
    }
)
_HTML_SUFFIXES = frozenset({".html", ".htm"})
_DOCX_SUFFIXES = frozenset({".docx"})
_PDF_SUFFIXES = frozenset({".pdf"})


class DocumentExtractionError(ValueError):
    """Raised when text cannot be extracted from a document."""


class DocumentText(BaseModel):
    """Text extracted from one document file."""

    path: str
    file_name: str
    suffix: str
    media_type: str | None = None
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("suffix")
    @classmethod
    def _normalize_suffix(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized and not normalized.startswith("."):
            normalized = f".{normalized}"
        return normalized

    @property
    def char_count(self) -> int:
        """Number of characters in the extracted text."""

        return len(self.text)

    @property
    def line_count(self) -> int:
        """Number of logical lines in the extracted text."""

        if not self.text:
            return 0
        return len(self.text.splitlines()) or 1


class DocumentExtractionResult(BaseModel):
    """Dictionary extraction result attached to the source document text."""

    document: DocumentText
    extraction: ExtractionResult

    @property
    def match_count(self) -> int:
        return self.extraction.match_count


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._chunks: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        normalized = tag.lower()
        if normalized in {"script", "style", "noscript"}:
            self._skip_depth += 1
            return
        if normalized in {
            "p",
            "br",
            "div",
            "section",
            "article",
            "li",
            "tr",
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
        }:
            self._chunks.append("\n")

    def handle_endtag(self, tag: str) -> None:
        normalized = tag.lower()
        if normalized in {"script", "style", "noscript"} and self._skip_depth:
            self._skip_depth -= 1
            return
        if normalized in {"p", "div", "section", "article", "li", "tr"}:
            self._chunks.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        self._chunks.append(data)

    def text(self) -> str:
        return _normalize_extracted_text("".join(self._chunks))


def load_document_text(path: str | Path, *, encoding: str = "utf-8") -> str:
    """Return extracted plain text for a supported document file.

    This convenience function returns only the extracted text. Use
    :func:`extract_document_text` when file metadata is also needed.
    """

    return extract_document_text(path, encoding=encoding).text


def extract_document_text(path: str | Path, *, encoding: str = "utf-8") -> DocumentText:
    """Extract plain text from a local document file.

    Supported without extra dependencies:

    - text-like files: TXT, Markdown, RST, logs, CSV/TSV, JSON/JSONL/YAML
    - HTML/HTM via the Python standard library
    - DOCX via the Python standard library ZIP/XML reader

    PDF files are supported when ``pypdf`` is installed in the environment. The
    core package does not require it by default to keep the public SDK light.
    """

    document_path = Path(path)
    if not document_path.exists():
        raise DocumentExtractionError(f"Document does not exist: {document_path}")
    if not document_path.is_file():
        raise DocumentExtractionError(f"Document path is not a file: {document_path}")

    suffix = document_path.suffix.lower()
    media_type = mimetypes.guess_type(document_path.name)[0]
    text: str
    metadata: dict[str, Any] = {}

    if suffix in _TEXT_SUFFIXES:
        text = _read_text_file(document_path, encoding=encoding)
        metadata["extractor"] = "text"
    elif suffix in _HTML_SUFFIXES:
        text = _extract_html_text(_read_text_file(document_path, encoding=encoding))
        metadata["extractor"] = "html"
    elif suffix in _DOCX_SUFFIXES:
        text, metadata = _extract_docx_text(document_path)
    elif suffix in _PDF_SUFFIXES:
        text, metadata = _extract_pdf_text(document_path)
    else:
        raise DocumentExtractionError(
            "Unsupported document type: "
            f"{suffix or '<no extension>'}. Supported extensions include "
            "txt, md, html, docx, and pdf when pypdf is installed."
        )

    return DocumentText(
        path=str(document_path),
        file_name=document_path.name,
        suffix=suffix,
        media_type=media_type,
        text=text,
        metadata=metadata,
    )


def extract_terms_from_document(
    path: str | Path,
    *,
    dictionary: str | Path | Mapping[str, Any] | Dictionary,
    encoding: str = "utf-8",
    max_matches: int | None = None,
    context_chars: int = 48,
) -> DocumentExtractionResult:
    """Extract dictionary matches from a supported local document file."""

    document = extract_document_text(path, encoding=encoding)
    extraction = extract_terms(
        document.text,
        dictionary=dictionary,
        max_matches=max_matches,
        context_chars=context_chars,
    )
    return DocumentExtractionResult(document=document, extraction=extraction)


def _read_text_file(path: Path, *, encoding: str) -> str:
    return path.read_text(encoding=encoding)


def _extract_html_text(raw_html: str) -> str:
    parser = _HTMLTextExtractor()
    parser.feed(raw_html)
    parser.close()
    return parser.text()


def _extract_docx_text(path: Path) -> tuple[str, dict[str, Any]]:
    try:
        with zipfile.ZipFile(path) as archive:
            document_xml = archive.read("word/document.xml")
    except KeyError as exc:
        raise DocumentExtractionError(
            f"DOCX file does not contain word/document.xml: {path}"
        ) from exc
    except zipfile.BadZipFile as exc:
        raise DocumentExtractionError(f"Invalid DOCX file: {path}") from exc

    try:
        root = ElementTree.fromstring(document_xml)
    except ElementTree.ParseError as exc:
        raise DocumentExtractionError(f"Invalid DOCX XML content: {path}") from exc

    paragraphs: list[str] = []
    for element in root.iter():
        if _xml_local_name(element.tag) != "p":
            continue
        paragraph = _docx_paragraph_text(element).strip()
        if paragraph:
            paragraphs.append(paragraph)

    return "\n".join(paragraphs), {
        "extractor": "docx-stdlib",
        "paragraph_count": len(paragraphs),
    }


def _docx_paragraph_text(paragraph: ElementTree.Element) -> str:
    chunks: list[str] = []
    for element in paragraph.iter():
        local_name = _xml_local_name(element.tag)
        if local_name == "t" and element.text:
            chunks.append(element.text)
        elif local_name == "tab":
            chunks.append("\t")
        elif local_name in {"br", "cr"}:
            chunks.append("\n")
    return "".join(chunks)


def _extract_pdf_text(path: Path) -> tuple[str, dict[str, Any]]:
    try:
        pypdf = import_module("pypdf")
    except ModuleNotFoundError as exc:
        raise DocumentExtractionError(
            "PDF extraction requires the optional 'pypdf' package. "
            "Install it separately, for example: python -m pip install pypdf"
        ) from exc

    try:
        reader = pypdf.PdfReader(str(path))
        pages_text = [(page.extract_text() or "") for page in reader.pages]
    except Exception as exc:  # pragma: no cover - depends on optional parser internals.
        raise DocumentExtractionError(
            f"Could not extract text from PDF: {path}"
        ) from exc

    return _normalize_extracted_text("\n".join(pages_text)), {
        "extractor": "pypdf",
        "page_count": len(pages_text),
    }


def _xml_local_name(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag


def _normalize_extracted_text(text: str) -> str:
    decoded = html.unescape(text)
    normalized_lines = [
        re.sub(r"[ \t\r\f\v]+", " ", line).strip() for line in decoded.splitlines()
    ]
    compact_lines = [line for line in normalized_lines if line]
    return "\n".join(compact_lines)
