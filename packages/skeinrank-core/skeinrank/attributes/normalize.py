from __future__ import annotations

import re

_SPACE_RE = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    cleaned = (
        text.lower()
        .replace("\u2011", "-")
        .replace("\u2013", "-")
        .replace("\u2014", "-")
    )
    cleaned = cleaned.replace("_", " ")
    cleaned = _SPACE_RE.sub(" ", cleaned)
    return cleaned.strip()


def normalize_value(value: str) -> str:
    return normalize_text(value)
