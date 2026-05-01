from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from skeinrank import Candidate


@dataclass(frozen=True)
class ElasticsearchProviderConfig:
    """Configuration for retrieving candidates from Elasticsearch.

    Notes:
        - This provider is intentionally small: it only does BM25 retrieval and
          Candidate conversion.
        - You own index mappings and analyzers.
    """

    index: str
    text_fields: Tuple[str, ...] = ("text",)
    id_field: str = "_id"  # special-cased if using ES hit "_id"
    size: int = 100


class ElasticsearchProvider:
    """Fetches BM25 candidates from Elasticsearch and converts to SkeinRank Candidates."""

    def __init__(
        self,
        *,
        client: Any,
        index: str,
        text_fields: Sequence[str] = ("text",),
        id_field: str = "_id",
        size: int = 100,
    ) -> None:
        self.client = client
        self.cfg = ElasticsearchProviderConfig(
            index=index,
            text_fields=tuple(text_fields),
            id_field=id_field,
            size=size,
        )

    def build_query(self, query: str) -> Dict[str, Any]:
        """Build a simple BM25-ish query.

        Uses `multi_match` over configured `text_fields`.
        """
        return {
            "query": {
                "multi_match": {
                    "query": query,
                    "fields": list(self.cfg.text_fields),
                    "type": "best_fields",
                }
            }
        }

    def retrieve(
        self,
        query: str,
        *,
        size: Optional[int] = None,
        extra_body: Optional[Dict[str, Any]] = None,
        source_includes: Optional[Sequence[str]] = None,
    ) -> Tuple[List[Candidate], List[Dict[str, Any]]]:
        """Retrieve candidates.

        Returns:
            (candidates, hits)
        """
        body = self.build_query(query)
        if extra_body:
            # shallow merge
            body.update(extra_body)

        resp = self.client.search(
            index=self.cfg.index,
            size=int(size or self.cfg.size),
            body=body,
            _source_includes=list(source_includes) if source_includes else None,
        )

        hits = list((resp or {}).get("hits", {}).get("hits", []) or [])
        return self._hits_to_candidates(hits), hits

    def _hits_to_candidates(self, hits: Iterable[Dict[str, Any]]) -> List[Candidate]:
        cands: List[Candidate] = []
        for h in hits:
            cand_id = self._get_hit_id(h)
            text = self._get_hit_text(h)
            if text is None:
                # skip empty docs rather than creating garbage candidates
                continue
            cands.append(Candidate(id=str(cand_id), text=text))
        return cands

    def _get_hit_id(self, hit: Dict[str, Any]) -> Any:
        if self.cfg.id_field == "_id":
            return hit.get("_id")
        src = hit.get("_source", {}) or {}
        return src.get(self.cfg.id_field)

    def _get_hit_text(self, hit: Dict[str, Any]) -> Optional[str]:
        src = hit.get("_source", {}) or {}
        parts: List[str] = []
        for f in self.cfg.text_fields:
            v = src.get(f)
            if v is None:
                continue
            if isinstance(v, list):
                parts.extend([str(x) for x in v if x is not None])
            else:
                parts.append(str(v))
        if not parts:
            return None
        # Keep it simple: join with newline.
        return "\n".join(parts)
