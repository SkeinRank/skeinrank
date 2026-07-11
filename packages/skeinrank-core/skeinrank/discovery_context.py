"""Deterministic line-context signals for local candidate discovery.

The classifier is intentionally small and dependency-free. It does not parse
source code; it tags each non-empty line with a coarse context so discovery can
prefer terminology that appears in human-facing prose as well as code while
still retaining code-only candidates for review.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum

LINE_CONTEXT_VERSION = "context-v1"


class LineContext(str, Enum):
    """Coarse context in which a scanned line appears."""

    PROSE = "prose"
    COMMENT = "comment"
    DOCSTRING = "docstring"
    DECORATOR = "decorator"
    STRING = "string"
    CODE = "code"


PROSE_CONTEXTS = frozenset(
    {LineContext.PROSE, LineContext.COMMENT, LineContext.DOCSTRING}
)

_PROSE_SUFFIXES = (".md", ".markdown", ".rst", ".txt", ".adoc")
_PYTHON_SUFFIXES = (".py", ".pyi")

_TRIPLE_QUOTE_PATTERN = re.compile(r'("""|\'\'\')')
_DECORATOR_PATTERN = re.compile(r"^@\w[\w.]*")
_LINE_COMMENT_PATTERN = re.compile(r"^(#|//|--\s|<!--)")
_BLOCK_COMMENT_OPEN_PATTERN = re.compile(r"^/\*")
_BLOCK_COMMENT_INNER_PATTERN = re.compile(r"^\*($|[^/])|^\*/")
_STRING_LINE_PATTERN = re.compile(r"""^(?:[frbu]{0,2})?["'](?!"")""", re.IGNORECASE)


def _is_prose_document(source: str) -> bool:
    return source.casefold().endswith(_PROSE_SUFFIXES)


def _is_python_document(source: str) -> bool:
    return source.casefold().endswith(_PYTHON_SUFFIXES)


@dataclass(slots=True)
class DocumentContextClassifier:
    """Classify stripped lines from one document.

    State is retained only for Python triple-quoted docstrings and C-style block
    comments. The result is deterministic and does not depend on a parser or the
    surrounding repository.
    """

    source: str
    _is_prose: bool = field(init=False)
    _is_python: bool = field(init=False)
    _in_docstring: bool = field(init=False, default=False)
    _in_block_comment: bool = field(init=False, default=False)

    def __post_init__(self) -> None:
        self._is_prose = _is_prose_document(self.source)
        self._is_python = _is_python_document(self.source)

    def classify(self, stripped_line: str) -> LineContext:
        """Return the context for one stripped, non-empty line."""

        if self._is_prose:
            return LineContext.PROSE

        if self._in_block_comment:
            if "*/" in stripped_line:
                self._in_block_comment = False
            return LineContext.COMMENT

        if self._is_python and self._in_docstring:
            if _TRIPLE_QUOTE_PATTERN.search(stripped_line):
                self._in_docstring = False
            return LineContext.DOCSTRING

        if self._is_python:
            triple_quotes = _TRIPLE_QUOTE_PATTERN.findall(stripped_line)
            if stripped_line.startswith(('"""', "'''", 'r"""', "r'''")):
                if len(triple_quotes) % 2 == 1:
                    self._in_docstring = True
                return LineContext.DOCSTRING

        if _LINE_COMMENT_PATTERN.match(stripped_line):
            return LineContext.COMMENT
        if _BLOCK_COMMENT_OPEN_PATTERN.match(stripped_line):
            if "*/" not in stripped_line:
                self._in_block_comment = True
            return LineContext.COMMENT
        if _BLOCK_COMMENT_INNER_PATTERN.match(stripped_line):
            return LineContext.COMMENT
        if _DECORATOR_PATTERN.match(stripped_line):
            return LineContext.DECORATOR
        if _STRING_LINE_PATTERN.match(stripped_line):
            return LineContext.STRING
        return LineContext.CODE
