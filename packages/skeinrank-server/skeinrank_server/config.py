from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List


def _split_csv(s: str) -> List[str]:
    return [x.strip() for x in (s or "").split(",") if x.strip()]


@dataclass(frozen=True)
class ServerConfig:
    es_url: str
    es_default_index: str
    es_text_field: str
    es_query_fields: List[str]
    es_timeout_s: float

    default_profile: str
    default_attribute_profile: str
    default_passport: str  # "summary" | "debug" | "off"
    telemetry: str  # "jsonl" | "off"

    @classmethod
    def from_env(cls) -> "ServerConfig":
        # Prefer SkeinRank-prefixed env vars, but keep backward compatible aliases.
        es_url = (os.getenv("SKEINRANK_ES_URL") or os.getenv("ES_URL") or "").strip()
        es_default_index = (
            os.getenv("SKEINRANK_ES_INDEX") or os.getenv("ES_DEFAULT_INDEX") or "kb"
        )
        return cls(
            es_url=es_url,
            es_default_index=str(es_default_index),
            es_text_field=(
                os.getenv("SKEINRANK_ES_TEXT_FIELD")
                or os.getenv("ES_TEXT_FIELD")
                or "text"
            ),
            es_query_fields=_split_csv(
                os.getenv("SKEINRANK_ES_QUERY_FIELDS")
                or os.getenv("ES_QUERY_FIELDS")
                or "text,title"
            )
            or ["text"],
            es_timeout_s=float(
                os.getenv("SKEINRANK_ES_TIMEOUT_S") or os.getenv("ES_TIMEOUT_S") or "5"
            ),
            default_profile=os.getenv("SKEINRANK_DEFAULT_PROFILE", "rerank_auto"),
            default_attribute_profile=os.getenv(
                "SKEINRANK_DEFAULT_ATTRIBUTE_PROFILE", "default_it"
            ),
            default_passport=os.getenv("SKEINRANK_DEFAULT_PASSPORT", "summary"),
            telemetry=os.getenv("SKEINRANK_TELEMETRY", "jsonl"),
        )
