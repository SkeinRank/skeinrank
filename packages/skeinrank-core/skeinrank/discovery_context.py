"""Deterministic document-context signals for local candidate discovery.

The classifier is intentionally dependency-free. Source files receive coarse
line-level contexts, while Markdown and reStructuredText documents use small
state machines that distinguish prose, inline code, code blocks, and markup.
This lets discovery rank documentation language without discarding API names
that may exist primarily in examples.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum

LINE_CONTEXT_VERSION = "context-v2"


class LineContext(str, Enum):
    """Coarse context in which a scanned text segment appears."""

    PROSE = "prose"
    COMMENT = "comment"
    DOCSTRING = "docstring"
    DECORATOR = "decorator"
    STRING = "string"
    CODE = "code"
    DIRECTIVE = "directive"


PROSE_CONTEXTS = frozenset(
    {LineContext.PROSE, LineContext.COMMENT, LineContext.DOCSTRING}
)

_MARKDOWN_SUFFIXES = (".md", ".markdown")
_RST_SUFFIXES = (".rst",)
_PROSE_SUFFIXES = (*_MARKDOWN_SUFFIXES, *_RST_SUFFIXES, ".txt", ".adoc")
_PYTHON_SUFFIXES = (".py", ".pyi")

_TRIPLE_QUOTE_PATTERN = re.compile(r'("""|\'\'\')')
_DECORATOR_PATTERN = re.compile(r"^@\w[\w.]*")
_LINE_COMMENT_PATTERN = re.compile(r"^(#|//|--\s|<!--)")
_BLOCK_COMMENT_OPEN_PATTERN = re.compile(r"^/\*")
_BLOCK_COMMENT_INNER_PATTERN = re.compile(r"^\*($|[^/])|^\*/")
_STRING_LINE_PATTERN = re.compile(r"""^(?:[frbu]{0,2})?["'](?!"")""", re.IGNORECASE)
_MARKDOWN_FENCE_PATTERN = re.compile(r"^[ ]{0,3}(`{3,}|~{3,})(?:[^`~].*)?$")
_RST_CODE_DIRECTIVE_PATTERN = re.compile(
    r"^\s*\.\.\s+(?:code-block|code|sourcecode)::(?:\s+.*)?$",
    re.IGNORECASE,
)
_RST_LITERALINCLUDE_PATTERN = re.compile(
    r"^\s*\.\.\s+literalinclude::(?:\s+.*)?$", re.IGNORECASE
)
_RST_DIRECTIVE_PATTERN = re.compile(r"^\s*\.\.\s+[\w:-]+::(?:\s+.*)?$")
_RST_OPTION_PATTERN = re.compile(r"^\s*:[\w-]+:")


def _is_prose_document(source: str) -> bool:
    return source.casefold().endswith(_PROSE_SUFFIXES)


def _is_markdown_document(source: str) -> bool:
    return source.casefold().endswith(_MARKDOWN_SUFFIXES)


def _is_rst_document(source: str) -> bool:
    return source.casefold().endswith(_RST_SUFFIXES)


def _is_python_document(source: str) -> bool:
    return source.casefold().endswith(_PYTHON_SUFFIXES)


def _indent_width(line: str) -> int:
    width = 0
    for character in line:
        if character == " ":
            width += 1
        elif character == "\t":
            width += 4
        else:
            break
    return width


@dataclass(frozen=True, slots=True)
class ContextSegment:
    """One non-empty segment and the context assigned to it."""

    text: str
    context: LineContext


@dataclass(frozen=True, slots=True)
class DocumentLineContext:
    """Classification result for one physical document line."""

    segments: tuple[ContextSegment, ...] = ()
    skip_reason: str | None = None


@dataclass(slots=True)
class DocumentContextClassifier:
    """Classify source and documentation text without external parsers.

    Markdown fences and reStructuredText literal blocks retain state across
    physical lines. Inline code is emitted as a separate segment so one line can
    contribute both prose and code evidence without conflating the two.
    """

    source: str
    _is_prose: bool = field(init=False)
    _is_markdown: bool = field(init=False)
    _is_rst: bool = field(init=False)
    _is_python: bool = field(init=False)
    _in_docstring: bool = field(init=False, default=False)
    _in_block_comment: bool = field(init=False, default=False)
    _markdown_fence_character: str | None = field(init=False, default=None)
    _markdown_fence_length: int = field(init=False, default=0)
    _rst_waiting_for_literal: bool = field(init=False, default=False)
    _rst_literal_base_indent: int = field(init=False, default=0)
    _rst_literal_indent: int | None = field(init=False, default=None)

    def __post_init__(self) -> None:
        self._is_prose = _is_prose_document(self.source)
        self._is_markdown = _is_markdown_document(self.source)
        self._is_rst = _is_rst_document(self.source)
        self._is_python = _is_python_document(self.source)

    def classify_line(self, raw_line: str) -> DocumentLineContext:
        """Return deterministic context segments for one physical line."""

        if self._is_markdown:
            return self._classify_markdown(raw_line)
        if self._is_rst:
            return self._classify_rst(raw_line)
        if self._is_prose:
            return DocumentLineContext(
                segments=_split_backtick_segments(raw_line.strip(), minimum_run=1)
            )
        return self._classify_source(raw_line)

    def classify(self, stripped_line: str) -> LineContext:
        """Return one coarse context for backward-compatible internal callers."""

        result = self.classify_line(stripped_line)
        if result.segments:
            return result.segments[0].context
        return LineContext.DIRECTIVE if result.skip_reason else LineContext.PROSE

    def _classify_markdown(self, raw_line: str) -> DocumentLineContext:
        stripped = raw_line.strip()
        fence_match = _MARKDOWN_FENCE_PATTERN.match(raw_line)

        if self._markdown_fence_character is not None:
            closing_fence = stripped
            if (
                closing_fence
                and set(closing_fence) == {self._markdown_fence_character}
                and len(closing_fence) >= self._markdown_fence_length
            ):
                self._markdown_fence_character = None
                self._markdown_fence_length = 0
                return DocumentLineContext(skip_reason="markdown_fence")
            if not stripped:
                return DocumentLineContext()
            return DocumentLineContext(
                segments=(ContextSegment(stripped, LineContext.CODE),)
            )

        if fence_match:
            fence = fence_match.group(1)
            self._markdown_fence_character = fence[0]
            self._markdown_fence_length = len(fence)
            return DocumentLineContext(skip_reason="markdown_fence")

        if not stripped:
            return DocumentLineContext()
        if raw_line.startswith("\t") or raw_line.startswith("    "):
            return DocumentLineContext(
                segments=(ContextSegment(stripped, LineContext.CODE),)
            )
        return DocumentLineContext(
            segments=_split_backtick_segments(stripped, minimum_run=1)
        )

    def _classify_rst(self, raw_line: str) -> DocumentLineContext:
        stripped = raw_line.strip()
        indent = _indent_width(raw_line)

        if self._rst_literal_indent is not None:
            if not stripped:
                return DocumentLineContext()
            if indent >= self._rst_literal_indent:
                return DocumentLineContext(
                    segments=(ContextSegment(stripped, LineContext.CODE),)
                )
            self._rst_literal_indent = None

        if self._rst_waiting_for_literal:
            if not stripped:
                return DocumentLineContext()
            if _RST_OPTION_PATTERN.match(raw_line):
                return DocumentLineContext(
                    segments=(ContextSegment(stripped, LineContext.DIRECTIVE),),
                    skip_reason="rst_option",
                )
            if indent > self._rst_literal_base_indent:
                self._rst_literal_indent = indent
                self._rst_waiting_for_literal = False
                return DocumentLineContext(
                    segments=(ContextSegment(stripped, LineContext.CODE),)
                )
            self._rst_waiting_for_literal = False

        if not stripped:
            return DocumentLineContext()

        if _RST_CODE_DIRECTIVE_PATTERN.match(raw_line):
            self._rst_waiting_for_literal = True
            self._rst_literal_base_indent = indent
            return DocumentLineContext(
                segments=(ContextSegment(stripped, LineContext.DIRECTIVE),),
                skip_reason="rst_directive",
            )
        if _RST_LITERALINCLUDE_PATTERN.match(raw_line):
            return DocumentLineContext(
                segments=(ContextSegment(stripped, LineContext.DIRECTIVE),),
                skip_reason="rst_directive",
            )
        if _RST_DIRECTIVE_PATTERN.match(raw_line):
            return DocumentLineContext(
                segments=(ContextSegment(stripped, LineContext.DIRECTIVE),),
                skip_reason="rst_directive",
            )
        if _RST_OPTION_PATTERN.match(raw_line):
            return DocumentLineContext(
                segments=(ContextSegment(stripped, LineContext.DIRECTIVE),),
                skip_reason="rst_option",
            )

        text = stripped
        if stripped == "::":
            self._rst_waiting_for_literal = True
            self._rst_literal_base_indent = indent
            return DocumentLineContext(skip_reason="rst_literal_marker")
        if stripped.endswith("::"):
            self._rst_waiting_for_literal = True
            self._rst_literal_base_indent = indent
            text = stripped[:-1].rstrip()

        return DocumentLineContext(
            segments=_split_backtick_segments(text, minimum_run=2)
        )

    def _classify_source(self, raw_line: str) -> DocumentLineContext:
        stripped_line = raw_line.strip()
        if not stripped_line:
            return DocumentLineContext()

        if self._in_block_comment:
            if "*/" in stripped_line:
                self._in_block_comment = False
            return DocumentLineContext(
                segments=(ContextSegment(stripped_line, LineContext.COMMENT),)
            )

        if self._is_python and self._in_docstring:
            if _TRIPLE_QUOTE_PATTERN.search(stripped_line):
                self._in_docstring = False
            return DocumentLineContext(
                segments=(ContextSegment(stripped_line, LineContext.DOCSTRING),)
            )

        if self._is_python:
            triple_quotes = _TRIPLE_QUOTE_PATTERN.findall(stripped_line)
            if stripped_line.startswith(('"""', "'''", 'r"""', "r'''")):
                if len(triple_quotes) % 2 == 1:
                    self._in_docstring = True
                return DocumentLineContext(
                    segments=(ContextSegment(stripped_line, LineContext.DOCSTRING),)
                )

        if _LINE_COMMENT_PATTERN.match(stripped_line):
            context = LineContext.COMMENT
        elif _BLOCK_COMMENT_OPEN_PATTERN.match(stripped_line):
            if "*/" not in stripped_line:
                self._in_block_comment = True
            context = LineContext.COMMENT
        elif _BLOCK_COMMENT_INNER_PATTERN.match(stripped_line):
            context = LineContext.COMMENT
        elif _DECORATOR_PATTERN.match(stripped_line):
            context = LineContext.DECORATOR
        elif _STRING_LINE_PATTERN.match(stripped_line):
            context = LineContext.STRING
        else:
            context = LineContext.CODE
        return DocumentLineContext(segments=(ContextSegment(stripped_line, context),))


def _split_backtick_segments(
    text: str,
    *,
    minimum_run: int,
) -> tuple[ContextSegment, ...]:
    """Split prose and matching inline-code spans without parsing Markdown/RST."""

    if not text:
        return ()

    segments: list[ContextSegment] = []
    cursor = 0
    search_from = 0
    while search_from < len(text):
        opening = re.search(rf"`{{{minimum_run},}}", text[search_from:])
        if opening is None:
            break
        opening_start = search_from + opening.start()
        opening_run = opening.group(0)
        if minimum_run == 2 and len(opening_run) != 2:
            search_from = opening_start + len(opening_run)
            continue
        closing_start = text.find(opening_run, opening_start + len(opening_run))
        if closing_start < 0:
            break

        prose = text[cursor:opening_start].strip()
        if prose:
            segments.append(ContextSegment(prose, LineContext.PROSE))
        code = text[opening_start + len(opening_run) : closing_start].strip()
        if code:
            segments.append(ContextSegment(code, LineContext.CODE))
        cursor = closing_start + len(opening_run)
        search_from = cursor

    tail = text[cursor:].strip()
    if tail:
        segments.append(ContextSegment(tail, LineContext.PROSE))
    return tuple(segments)
