"""Dependency-free lexical scorer used by the core reranking API.

Scoring strategy: normalized token overlap (cosine on binary term sets).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from ..domain.types import Candidate

_WORD_RE = re.compile(r"[\w]+", re.UNICODE)


def _tokens(text: str) -> set[str]:
    return {t.lower() for t in _WORD_RE.findall(text)}


@dataclass
class BuiltinLexicalScorer:
    """Simple lexical scorer."""

    def score(
        self, query: str, candidates: list[Candidate], *, batch_size: int | None = None
    ) -> dict[str, float]:
        q = _tokens(query)
        if not q:
            return {c.id: 0.0 for c in candidates}

        q_norm = math.sqrt(len(q))
        out: dict[str, float] = {}
        for c in candidates:
            d = _tokens(c.text)
            if not d:
                out[c.id] = 0.0
                continue
            overlap = len(q.intersection(d))
            d_norm = math.sqrt(len(d))
            out[c.id] = float(overlap) / float(q_norm * d_norm)
        return out
