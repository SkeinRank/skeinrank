from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable

from .pipeline import extract_attributes

_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9\.-]*")


def load_jsonl(path: str | Path) -> list[dict[str, Any]]:
    path = Path(path)
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:  # pragma: no cover - defensive
                raise ValueError(f"Invalid JSONL at {path}:{lineno}") from exc
            if not isinstance(payload, dict):  # pragma: no cover - defensive
                raise ValueError(f"Expected JSON object at {path}:{lineno}")
            rows.append(payload)
    return rows


def write_jsonl(path: str | Path, rows: Iterable[dict[str, Any]]) -> int:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            count += 1
    return count


def _compose_document_text(
    record: dict[str, Any], *, title_field: str, text_field: str
) -> str:
    title = str(record.get(title_field, "") or "").strip()
    text = str(record.get(text_field, "") or "").strip()
    if title and text:
        return f"{title}\n{text}"
    return title or text


def _tokenize(text: str) -> set[str]:
    return set(_TOKEN_RE.findall(text.lower()))


def enrich_documents(
    records: Iterable[dict[str, Any]],
    *,
    profile: str = "default_it",
    debug: bool = True,
    title_field: str = "title",
    text_field: str = "text",
) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for record in records:
        base = dict(record)
        composed_text = _compose_document_text(
            base, title_field=title_field, text_field=text_field
        )
        pack = extract_attributes(composed_text, profile=profile, debug=debug)
        attributes = [item.model_dump(mode="json") for item in pack.attributes]
        canonical_values = sorted({item["value"] for item in attributes})
        passport = (
            pack.passport.model_dump(mode="json") if pack.passport is not None else None
        )
        if passport is not None and not passport.get("stage_status"):
            passport.pop("stage_status", None)
        base.update(
            {
                "original_text": str(record.get(text_field, "") or ""),
                "snapshot": pack.snapshot.model_dump(mode="json")
                if pack.snapshot is not None
                else None,
                "alias_matcher_backend": pack.alias_matcher_backend,
                "extracted_attributes": attributes,
                "canonical_values": canonical_values,
                "passport": passport,
            }
        )
        enriched.append(base)
    return enriched


def enrich_jsonl(
    input_path: str | Path,
    output_path: str | Path,
    *,
    profile: str = "default_it",
    debug: bool = True,
    title_field: str = "title",
    text_field: str = "text",
) -> int:
    rows = load_jsonl(input_path)
    enriched = enrich_documents(
        rows,
        profile=profile,
        debug=debug,
        title_field=title_field,
        text_field=text_field,
    )
    return write_jsonl(output_path, enriched)


def _baseline_score(
    query_text: str, document: dict[str, Any], *, title_field: str, text_field: str
) -> int:
    query_tokens = _tokenize(query_text)
    doc_tokens = _tokenize(
        f"{document.get(title_field, '')} {document.get(text_field, '')}"
    )
    return len(query_tokens & doc_tokens)


def _normalized_score(
    query_text: str,
    query_values: set[str],
    document: dict[str, Any],
    *,
    title_field: str,
    text_field: str,
) -> int:
    score = _baseline_score(
        query_text, document, title_field=title_field, text_field=text_field
    )
    doc_values = set(document.get("canonical_values", []))
    score += 3 * len(query_values & doc_values)

    searchable_text = (
        f"{document.get(title_field, '')} {document.get(text_field, '')}".lower()
    )
    for value in query_values:
        if value.lower() in searchable_text:
            score += 1
    return score


def _rank_documents(
    query_text: str,
    query_values: set[str],
    documents: list[dict[str, Any]],
    *,
    title_field: str,
    text_field: str,
    mode: str,
) -> list[dict[str, Any]]:
    scored: list[dict[str, Any]] = []
    for document in documents:
        if mode == "baseline":
            score = _baseline_score(
                query_text, document, title_field=title_field, text_field=text_field
            )
        elif mode == "normalized":
            score = _normalized_score(
                query_text,
                query_values,
                document,
                title_field=title_field,
                text_field=text_field,
            )
        else:  # pragma: no cover - defensive
            raise ValueError(f"Unknown ranking mode: {mode}")
        scored.append({"id": str(document["id"]), "score": int(score)})
    return sorted(scored, key=lambda item: (-item["score"], item["id"]))


def _reciprocal_rank(results: list[dict[str, Any]], relevant: set[str]) -> float:
    for idx, item in enumerate(results, start=1):
        if item["id"] in relevant:
            return 1.0 / idx
    return 0.0


def evaluate_demo_queries(
    queries: Iterable[dict[str, Any]],
    enriched_documents: list[dict[str, Any]],
    *,
    profile: str = "default_it",
    top_k: int = 3,
    title_field: str = "title",
    text_field: str = "text",
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    baseline_hits = 0
    normalized_hits = 0
    baseline_rr_total = 0.0
    normalized_rr_total = 0.0

    query_list = list(queries)
    for query in query_list:
        query_pack = extract_attributes(str(query["text"]), profile=profile, debug=True)
        query_values = {item.value for item in query_pack.attributes}
        relevant = {str(x) for x in query.get("relevant", [])}

        baseline_ranked = _rank_documents(
            str(query["text"]),
            query_values,
            enriched_documents,
            title_field=title_field,
            text_field=text_field,
            mode="baseline",
        )
        normalized_ranked = _rank_documents(
            str(query["text"]),
            query_values,
            enriched_documents,
            title_field=title_field,
            text_field=text_field,
            mode="normalized",
        )

        baseline_top = baseline_ranked[0]["id"] if baseline_ranked else None
        baseline_top_score = baseline_ranked[0]["score"] if baseline_ranked else None
        normalized_top = normalized_ranked[0]["id"] if normalized_ranked else None
        normalized_top_score = (
            normalized_ranked[0]["score"] if normalized_ranked else None
        )
        baseline_hit = baseline_top in relevant if baseline_top is not None else False
        normalized_hit = (
            normalized_top in relevant if normalized_top is not None else False
        )

        baseline_hits += int(baseline_hit)
        normalized_hits += int(normalized_hit)
        baseline_rr_total += _reciprocal_rank(baseline_ranked, relevant)
        normalized_rr_total += _reciprocal_rank(normalized_ranked, relevant)

        top_doc_by_id = {doc["id"]: doc for doc in enriched_documents}
        matched_values = []
        if normalized_top is not None:
            matched_values = sorted(
                query_values
                & set(top_doc_by_id[normalized_top].get("canonical_values", []))
            )

        rows.append(
            {
                "query_id": str(query["id"]),
                "query_text": str(query["text"]),
                "relevant": sorted(relevant),
                "query_canonical_values": sorted(query_values),
                "baseline_top1": baseline_top,
                "baseline_top1_score": baseline_top_score,
                "normalized_top1": normalized_top,
                "normalized_top1_score": normalized_top_score,
                "baseline_hit": baseline_hit,
                "normalized_hit": normalized_hit,
                "matched_canonical_values": matched_values,
                "baseline_topk": baseline_ranked[:top_k],
                "normalized_topk": normalized_ranked[:top_k],
            }
        )

    total_queries = len(query_list)
    summary = {
        "total_queries": total_queries,
        "queries_with_canonical_values": sum(
            1 for row in rows if row["query_canonical_values"]
        ),
        "baseline_top1_hits": baseline_hits,
        "normalized_top1_hits": normalized_hits,
        "baseline_top1_accuracy": round(baseline_hits / total_queries, 4)
        if total_queries
        else 0.0,
        "normalized_top1_accuracy": round(normalized_hits / total_queries, 4)
        if total_queries
        else 0.0,
        "baseline_mrr": round(baseline_rr_total / total_queries, 4)
        if total_queries
        else 0.0,
        "normalized_mrr": round(normalized_rr_total / total_queries, 4)
        if total_queries
        else 0.0,
    }
    return {"summary": summary, "rows": rows}
