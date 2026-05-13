"""Runtime query planning and search endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from skeinrank_governance.models import ElasticsearchBinding, normalize_profile_name
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import AuthContext, require_roles
from ..dependencies import get_session
from ..elasticsearch import ElasticsearchDiscoveryClient, ElasticsearchDiscoveryError
from ..runtime_snapshots import (
    active_runtime_alias_entries,
    alias_entries_from_snapshot,
    build_runtime_snapshot_payload,
)
from ..schemas import (
    QueryPlanRequest,
    QueryPlanResponse,
    SearchHitResponse,
    SearchRequest,
    SearchResponse,
    TextCanonicalizeEvidence,
)
from .text import (
    _find_alias_matches,
    _get_profile_or_404,
    _match_response,
    _replace_matches,
    _select_non_overlapping_matches,
    _slots_for_matches,
)

router = APIRouter(prefix="/v1", tags=["runtime"])


@router.post("/query/plan", response_model=QueryPlanResponse)
def build_query_plan(
    request: QueryPlanRequest,
    _current_user: AuthContext = Depends(
        require_roles("admin", "moderator", "contributor")
    ),
    session: Session = Depends(get_session),
) -> QueryPlanResponse:
    """Build a query understanding payload and Elasticsearch DSL without executing it."""

    plan = _build_runtime_plan(
        session=session,
        profile_name=request.profile_name,
        binding_id=request.binding_id,
        query_text=request.query,
        text_fields=request.text_fields,
        target_field=request.target_field,
        size=request.size,
        canonical_boost=request.canonical_boost,
        include_evidence=request.include_evidence,
        max_matches=request.max_matches,
    )
    return QueryPlanResponse(**plan)


@router.post("/search", response_model=SearchResponse)
def search_documents(
    request: SearchRequest,
    http_request: Request,
    _current_user: AuthContext = Depends(
        require_roles("admin", "moderator", "contributor")
    ),
    session: Session = Depends(get_session),
) -> SearchResponse:
    """Execute runtime search against Elasticsearch using canonical attributes."""

    plan = _build_runtime_plan(
        session=session,
        profile_name=request.profile_name,
        binding_id=request.binding_id,
        query_text=request.query,
        text_fields=request.text_fields,
        target_field=request.target_field,
        size=request.size,
        canonical_boost=request.canonical_boost,
        include_evidence=request.include_evidence,
        max_matches=request.max_matches,
    )
    search_body = dict(plan["elasticsearch"])
    source_filter = _source_filter(
        include_source=request.include_source,
        source_fields=request.source_fields,
    )
    if source_filter is not None:
        search_body["_source"] = source_filter

    client = ElasticsearchDiscoveryClient(http_request.app.state.config)
    if not client.is_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Elasticsearch URL is not configured.",
        )
    try:
        payload = client.execute_search(index_name=request.index_name, body=search_body)
    except ElasticsearchDiscoveryError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    hits_root = payload.get("hits") if isinstance(payload, dict) else None
    hits_payload = hits_root.get("hits", []) if isinstance(hits_root, dict) else []
    total = hits_root.get("total") if isinstance(hits_root, dict) else None
    hits = [_search_hit_response(item, request.target_field) for item in hits_payload]

    return SearchResponse(
        profile_name=plan["profile_name"],
        normalized_profile_name=plan["normalized_profile_name"],
        index_name=request.index_name,
        query=plan["query"],
        canonical_query=plan["canonical_query"],
        changed=plan["changed"],
        binding_id=plan["binding_id"],
        snapshot_version=plan["snapshot_version"],
        snapshot_source=plan["snapshot_source"],
        canonical_values=plan["canonical_values"],
        slots=plan["slots"],
        matched_aliases=plan["matched_aliases"],
        replacements=plan["replacements"],
        evidence=plan["evidence"],
        elasticsearch=search_body,
        total=total,
        hits=hits,
        warnings=plan["warnings"],
    )


def _build_runtime_plan(
    *,
    session: Session,
    profile_name: str,
    binding_id: int | None,
    query_text: str,
    text_fields: list[str],
    target_field: str,
    size: int,
    canonical_boost: float,
    include_evidence: bool,
    max_matches: int,
) -> dict[str, Any]:
    profile = _get_profile_or_404(session, profile_name)
    binding = _runtime_binding_or_none(
        session=session, profile_name=profile_name, binding_id=binding_id
    )
    if binding is not None and binding.profile_id != profile.id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Binding does not belong to the requested profile.",
        )
    alias_entries, snapshot_version, snapshot_source = _runtime_alias_entries(
        session=session, profile=profile, binding=binding
    )
    candidate_matches = _find_alias_matches(query_text, alias_entries)
    matches = _select_non_overlapping_matches(candidate_matches, max_matches)

    canonical_query = _replace_matches(query_text, matches)
    canonical_values = sorted({match.canonical_value for match in matches})
    slots = _slots_for_matches(matches)
    matched_aliases = sorted({match.alias_value for match in matches})
    replacements = [_match_response(match) for match in matches]
    evidence = (
        [
            TextCanonicalizeEvidence(
                reason="Alias matched active canonical term",
                alias_value=match.alias_value,
                canonical_value=match.canonical_value,
                slot=match.slot,
                matched_text=match.matched_text,
                start=match.start,
                end=match.end,
                confidence=match.confidence,
                source="alias",
            )
            for match in matches
        ]
        if include_evidence
        else []
    )

    warnings: list[str] = []
    if candidate_matches and len(matches) < len(candidate_matches):
        warnings.append(
            "Some overlapping or extra matches were omitted from query planning."
        )
    if not alias_entries:
        warnings.append("No active aliases are available for this profile.")
    if not matches:
        warnings.append("No active aliases matched the query.")

    return {
        "profile_name": profile.name,
        "normalized_profile_name": profile.normalized_name,
        "query": query_text,
        "canonical_query": canonical_query,
        "changed": canonical_query != query_text,
        "text_fields": _normalize_text_fields(text_fields),
        "target_field": target_field,
        "binding_id": binding.id if binding is not None else None,
        "snapshot_version": snapshot_version,
        "snapshot_source": snapshot_source,
        "canonical_values": canonical_values,
        "slots": slots,
        "matched_aliases": matched_aliases,
        "replacements": replacements,
        "evidence": evidence,
        "elasticsearch": _build_elasticsearch_query(
            query_text=query_text,
            canonical_values=canonical_values,
            text_fields=_normalize_text_fields(text_fields),
            target_field=target_field,
            size=size,
            canonical_boost=canonical_boost,
        ),
        "warnings": warnings,
    }


def _runtime_binding_or_none(
    *, session: Session, profile_name: str, binding_id: int | None
) -> ElasticsearchBinding | None:
    if binding_id is None:
        return None
    binding = session.scalar(
        select(ElasticsearchBinding).where(ElasticsearchBinding.id == binding_id)
    )
    if binding is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Elasticsearch binding not found: {binding_id}",
        )
    if binding.profile.normalized_name != normalize_profile_name(profile_name):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Binding does not belong to the requested profile.",
        )
    return binding


def _runtime_alias_entries(
    *,
    session: Session,
    profile,
    binding: ElasticsearchBinding | None,
):
    if binding is not None and isinstance(binding.runtime_snapshot_json, dict):
        alias_entries = alias_entries_from_snapshot(binding.runtime_snapshot_json)
        if alias_entries:
            return (
                alias_entries,
                binding.last_successful_snapshot_version,
                "binding_runtime_snapshot",
            )
    latest_snapshot = build_runtime_snapshot_payload(session, profile)
    return (
        active_runtime_alias_entries(session, profile),
        str(latest_snapshot["version"]),
        "latest_profile",
    )


def _build_elasticsearch_query(
    *,
    query_text: str,
    canonical_values: list[str],
    text_fields: list[str],
    target_field: str,
    size: int,
    canonical_boost: float,
) -> dict[str, Any]:
    text_match = {
        "multi_match": {
            "query": query_text,
            "fields": text_fields,
            "type": "best_fields",
        }
    }
    if not canonical_values:
        query: dict[str, Any] = text_match
    else:
        should: list[dict[str, Any]] = [text_match]
        if canonical_boost > 0:
            should.append(
                {
                    "terms": {
                        f"{target_field}.canonical_values": canonical_values,
                        "boost": canonical_boost,
                    }
                }
            )
        query = {"bool": {"should": should, "minimum_should_match": 1}}
    return {
        "query": query,
        "size": size,
        "track_total_hits": True,
    }


def _normalize_text_fields(text_fields: list[str]) -> list[str]:
    normalized: list[str] = []
    for field in text_fields:
        value = str(field).strip()
        if value and value not in normalized:
            normalized.append(value)
    if not normalized:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="At least one text field is required.",
        )
    return normalized


def _source_filter(
    *, include_source: bool, source_fields: list[str] | None
) -> bool | list[str] | None:
    if not include_source:
        return False
    if source_fields is None:
        return None
    normalized = [str(field).strip() for field in source_fields if str(field).strip()]
    return normalized if normalized else None


def _search_hit_response(item: Any, target_field: str) -> SearchHitResponse:
    if not isinstance(item, dict):
        return SearchHitResponse(id="", index="", source={})
    source = item.get("_source")
    source_dict = source if isinstance(source, dict) else {}
    skeinrank_payload = source_dict.get(target_field)
    return SearchHitResponse(
        id=str(item.get("_id") or ""),
        index=str(item.get("_index") or ""),
        score=_optional_float(item.get("_score")),
        source=source_dict,
        skeinrank=skeinrank_payload if isinstance(skeinrank_payload, dict) else None,
    )


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
