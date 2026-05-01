from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional, Tuple

import httpx


@dataclass
class ESClient:
    base_url: str
    timeout_s: float = 5.0

    def _client(self) -> httpx.Client:
        return httpx.Client(base_url=self.base_url, timeout=self.timeout_s)

    def ping(self) -> Tuple[bool, Optional[str]]:
        if not self.base_url:
            return False, "ES_URL is not set"
        try:
            with self._client() as c:
                r = c.get("/")
            if 200 <= r.status_code < 300:
                return True, None
            return False, f"status={r.status_code}"
        except Exception as e:
            return False, f"{type(e).__name__}: {e}"

    def search(
        self,
        *,
        index: str,
        query: str,
        k: int,
        query_fields: List[str],
        text_field: str,
        fetch_fields: Optional[List[str]] = None,
    ) -> list[dict[str, Any]]:
        if not self.base_url:
            raise RuntimeError("ES_URL is not set")
        fetch_fields = fetch_fields or [text_field]
        body = {
            "size": int(k),
            "_source": fetch_fields,
            "query": {
                "multi_match": {
                    "query": query,
                    "fields": query_fields,
                    "type": "best_fields",
                }
            },
        }
        path = f"/{index}/_search"
        with self._client() as c:
            r = c.post(path, json=body)
        if r.status_code < 200 or r.status_code >= 300:
            raise RuntimeError(
                f"ES search failed status={r.status_code} body={r.text[:500]}"
            )
        data = r.json()
        hits = data.get("hits", {}).get("hits", []) or []
        out: list[dict[str, Any]] = []
        for h in hits:
            _id = str(h.get("_id", ""))
            src = h.get("_source") or {}
            text = src.get(text_field, "")
            out.append(
                {
                    "id": _id,
                    "text": text if isinstance(text, str) else str(text),
                    "score": float(h.get("_score") or 0.0),
                    "source": src,
                }
            )
        return out
