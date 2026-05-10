"""Background execution helpers for Elasticsearch enrichment jobs."""

from __future__ import annotations

import math
from typing import Any

from skeinrank_governance.models import ElasticsearchEnrichmentJob, utc_now
from sqlalchemy import select

from .config import GovernanceApiConfig
from .dependencies import create_engine_for_config
from .elasticsearch import (
    ElasticsearchDiscoveryClient,
    ElasticsearchDiscoveryError,
    compose_source_text,
)

CHUNK_RESULT_STATUS_SUCCEEDED = "succeeded"
CHUNK_RESULT_STATUS_FAILED = "failed"


def run_elasticsearch_enrichment_job(
    *, job_id: int, config: GovernanceApiConfig | None = None
) -> dict[str, Any]:
    """Prepare one queued Elasticsearch enrichment job for background chunks.

    In Celery mode this function is the coordinator task. It creates the target
    index/reindexes documents when needed, records chunk metadata in the job
    JSON, and dispatches bounded chunk tasks so multiple workers can process the
    same enrichment job in parallel.

    If it is invoked in a non-Celery environment, it processes the chunks
    sequentially as a safe fallback. The HTTP API still uses the existing sync
    path by default, so local development without RabbitMQ remains unchanged.
    """

    config = config or GovernanceApiConfig.from_env()
    engine = create_engine_for_config(config)
    try:
        from skeinrank_governance import create_session_factory

        session_factory = create_session_factory(engine)
        chunk_specs: list[dict[str, int]] = []
        with session_factory() as session:
            job = session.scalar(
                select(ElasticsearchEnrichmentJob).where(
                    ElasticsearchEnrichmentJob.id == job_id
                )
            )
            if job is None:
                raise ElasticsearchDiscoveryError(
                    f"Elasticsearch enrichment job not found: {job_id}"
                )
            if job.status not in {"queued", "running"}:
                return {
                    "job_id": job_id,
                    "status": job.status,
                    "skipped": True,
                    "reason": "Job is no longer queued or running.",
                }

            job.status = "running"
            if job.started_at is None:
                job.started_at = utc_now()
            session.commit()
            session.refresh(job)

            try:
                client = ElasticsearchDiscoveryClient(config)
                if not client.is_configured:
                    raise ElasticsearchDiscoveryError(
                        "Elasticsearch URL is not configured."
                    )

                reindex_result, update_index = _prepare_chunked_enrichment(
                    client=client,
                    job=job,
                )
                max_documents = _job_max_documents(job)
                chunk_size = _job_chunk_size(job, config)
                chunk_specs = _build_chunk_specs(
                    max_documents=max_documents, chunk_size=chunk_size
                )
                job.result_json = _initial_chunked_result_json(
                    job=job,
                    max_documents=max_documents,
                    chunk_size=chunk_size,
                    update_index=update_index,
                    chunks_total=len(chunk_specs),
                    reindex_result=reindex_result,
                    backend=config.enrichment_jobs_backend,
                )
                session.commit()
            except ElasticsearchDiscoveryError as exc:
                job.status = "failed"
                job.error_message = str(exc)
                job.finished_at = utc_now()
                session.commit()
                session.refresh(job)
                return {"job_id": job_id, "status": "failed", "error": str(exc)}

        if config.enrichment_jobs_backend == "celery":
            from .worker_queue import enqueue_elasticsearch_enrichment_chunk

            queued_chunks = []
            try:
                for spec in chunk_specs:
                    queued_task = enqueue_elasticsearch_enrichment_chunk(
                        config=config,
                        job_id=job_id,
                        chunk_index=spec["chunk_index"],
                        offset=spec["offset"],
                        limit=spec["limit"],
                    )
                    queued_chunks.append(
                        {
                            "chunk_index": spec["chunk_index"],
                            "task_id": queued_task.task_id,
                            "queue": queued_task.queue,
                        }
                    )
                _record_queued_chunks(
                    config=config,
                    job_id=job_id,
                    queued_chunks=queued_chunks,
                )
                return {
                    "job_id": job_id,
                    "status": "running",
                    "chunks_queued": len(queued_chunks),
                }
            except Exception as exc:  # pragma: no cover - defensive queue failure path
                _mark_job_failed(config=config, job_id=job_id, error=str(exc))
                return {"job_id": job_id, "status": "failed", "error": str(exc)}

        # Non-Celery fallback for direct worker execution tests/dev utilities.
        results = []
        for spec in chunk_specs:
            results.append(
                run_elasticsearch_enrichment_chunk(
                    job_id=job_id,
                    chunk_index=spec["chunk_index"],
                    offset=spec["offset"],
                    limit=spec["limit"],
                    config=config,
                )
            )
        return {"job_id": job_id, "status": "succeeded", "chunks": results}
    finally:
        engine.dispose()


def run_elasticsearch_enrichment_chunk(
    *,
    job_id: int,
    chunk_index: int,
    offset: int,
    limit: int,
    config: GovernanceApiConfig | None = None,
) -> dict[str, Any]:
    """Process one bounded enrichment chunk and update aggregate job status."""

    config = config or GovernanceApiConfig.from_env()
    engine = create_engine_for_config(config)
    try:
        from skeinrank_governance import create_session_factory

        session_factory = create_session_factory(engine)
        with session_factory() as session:
            job = session.scalar(
                select(ElasticsearchEnrichmentJob).where(
                    ElasticsearchEnrichmentJob.id == job_id
                )
            )
            if job is None:
                raise ElasticsearchDiscoveryError(
                    f"Elasticsearch enrichment job not found: {job_id}"
                )
            if job.status != "running":
                return {
                    "job_id": job_id,
                    "chunk_index": chunk_index,
                    "status": job.status,
                    "skipped": True,
                }

            try:
                result = _execute_enrichment_chunk(
                    config=config,
                    session=session,
                    job=job,
                    chunk_index=chunk_index,
                    offset=offset,
                    limit=limit,
                )
            except ElasticsearchDiscoveryError as exc:
                result = {
                    "chunk_index": chunk_index,
                    "offset": offset,
                    "limit": limit,
                    "status": CHUNK_RESULT_STATUS_FAILED,
                    "documents_seen": 0,
                    "documents_enriched": 0,
                    "documents_failed": 0,
                    "updated_document_ids": [],
                    "error": str(exc),
                }
                _apply_chunk_result(job=job, chunk_result=result)
                job.status = "failed"
                job.error_message = str(exc)
                job.finished_at = utc_now()
                session.commit()
                session.refresh(job)
                return {"job_id": job_id, "status": "failed", "chunk": result}

            _apply_chunk_result(job=job, chunk_result=result)
            _maybe_finalize_chunked_job(config=config, session=session, job=job)
            session.commit()
            session.refresh(job)
            return {"job_id": job_id, "status": job.status, "chunk": result}
    finally:
        engine.dispose()


def _prepare_chunked_enrichment(
    *, client: ElasticsearchDiscoveryClient, job: ElasticsearchEnrichmentJob
) -> tuple[dict[str, Any] | None, str]:
    binding = job.binding
    if binding.write_strategy == "reindex_alias_swap":
        if not job.target_index:
            raise ElasticsearchDiscoveryError(
                "Target index is required for reindex jobs"
            )
        client.create_reindex_target_index(
            source_index=binding.index_name,
            target_index=job.target_index,
        )
        reindex_result = client.reindex_documents(
            source_index=binding.index_name,
            target_index=job.target_index,
            filter_field=binding.filter_field,
            filter_value=binding.filter_value,
            timestamp_field=binding.timestamp_field,
            time_window_days=binding.time_window_days,
        )
        return reindex_result, job.target_index
    if binding.write_strategy == "in_place":
        return None, binding.index_name
    raise ElasticsearchDiscoveryError(
        f"Unsupported write strategy: {binding.write_strategy}"
    )


def _execute_enrichment_chunk(
    *,
    config: GovernanceApiConfig,
    session,
    job: ElasticsearchEnrichmentJob,
    chunk_index: int,
    offset: int,
    limit: int,
) -> dict[str, Any]:
    client = ElasticsearchDiscoveryClient(config)
    if not client.is_configured:
        raise ElasticsearchDiscoveryError("Elasticsearch URL is not configured.")

    from .routes.governance import (  # lazy imports avoid router startup coupling
        _active_alias_entries_for_profile,
        _dry_run_payload,
        _match_alias_entries,
    )

    binding = job.binding
    update_index = _chunked_update_index(job)
    alias_entries = _active_alias_entries_for_profile(session, binding.profile)
    hits = client.search_documents(
        index_name=update_index,
        text_fields=list(binding.text_fields),
        limit=limit,
        offset=offset,
        filter_field=binding.filter_field,
        filter_value=binding.filter_value,
        timestamp_field=binding.timestamp_field,
        time_window_days=binding.time_window_days,
    )

    updates: list[tuple[str, dict[str, object]]] = []
    matched_documents: list[dict[str, object]] = []
    for hit in hits:
        text = compose_source_text(hit.source, list(binding.text_fields))
        matched_aliases = _match_alias_entries(text, alias_entries)
        if not matched_aliases:
            continue
        would_write_payload = _dry_run_payload(binding, matched_aliases)
        updates.append((hit.id, {binding.target_field: would_write_payload}))
        matched_documents.append(
            {
                "document_id": hit.id,
                "index_name": hit.index,
                "matched_aliases": [
                    {
                        "alias_value": match.alias_value,
                        "canonical_value": match.canonical_value,
                        "slot": match.slot,
                        "matched_text": match.matched_text,
                        "confidence": match.confidence,
                    }
                    for match in matched_aliases
                ],
                "would_write": {binding.target_field: would_write_payload},
            }
        )

    bulk_result = client.bulk_update_documents(index_name=update_index, updates=updates)
    return {
        "chunk_index": chunk_index,
        "offset": offset,
        "limit": limit,
        "status": CHUNK_RESULT_STATUS_SUCCEEDED,
        "documents_seen": len(hits),
        "documents_enriched": len(updates),
        "documents_failed": 0,
        "updated_document_ids": [document_id for document_id, _document in updates],
        "matched_documents": matched_documents,
        "bulk_result": bulk_result,
    }


def _maybe_finalize_chunked_job(
    *, config: GovernanceApiConfig, session, job: ElasticsearchEnrichmentJob
) -> None:
    result_json = job.result_json or {}
    chunked = dict(result_json.get("chunked_enrichment") or {})
    chunks = list(chunked.get("chunks") or [])
    chunks_total = int(chunked.get("chunks_total") or 0)
    completed = [
        chunk
        for chunk in chunks
        if chunk.get("status") == CHUNK_RESULT_STATUS_SUCCEEDED
    ]
    failed = [
        chunk for chunk in chunks if chunk.get("status") == CHUNK_RESULT_STATUS_FAILED
    ]

    job.documents_seen = sum(int(chunk.get("documents_seen") or 0) for chunk in chunks)
    job.documents_enriched = sum(
        int(chunk.get("documents_enriched") or 0) for chunk in chunks
    )
    job.documents_failed = sum(
        int(chunk.get("documents_failed") or 0) for chunk in chunks
    )

    if failed:
        job.status = "failed"
        job.error_message = (
            failed[0].get("error") or "One or more enrichment chunks failed."
        )
        job.finished_at = utc_now()
        return

    if (
        chunks_total
        and len(completed) >= chunks_total
        and not chunked.get("finalized_at")
    ):
        alias_result = None
        if job.write_strategy == "reindex_alias_swap":
            if not job.alias_name:
                raise ElasticsearchDiscoveryError(
                    "Alias name is required for alias-swap jobs"
                )
            client = ElasticsearchDiscoveryClient(config)
            alias_result = client.swap_alias(
                alias_name=job.alias_name,
                target_index=_chunked_update_index(job),
            )
        updated_document_ids: list[str] = []
        matched_documents: list[dict[str, object]] = []
        for chunk in chunks:
            updated_document_ids.extend(chunk.get("updated_document_ids") or [])
            matched_documents.extend(chunk.get("matched_documents") or [])
        chunked["finalized_at"] = utc_now().isoformat()
        chunked["chunks_completed"] = len(completed)
        chunked["chunks_failed"] = 0
        job.result_json = {
            **result_json,
            "documents_seen": job.documents_seen,
            "documents_enriched": job.documents_enriched,
            "documents_failed": job.documents_failed,
            "updated_document_ids": updated_document_ids,
            "matched_documents": matched_documents,
            "alias_result": alias_result,
            "chunked_enrichment": chunked,
        }
        job.status = "succeeded"
        job.error_message = None
        job.finished_at = utc_now()
    else:
        chunked["chunks_completed"] = len(completed)
        chunked["chunks_failed"] = len(failed)
        job.result_json = {**result_json, "chunked_enrichment": chunked}


def _initial_chunked_result_json(
    *,
    job: ElasticsearchEnrichmentJob,
    max_documents: int,
    chunk_size: int,
    update_index: str,
    chunks_total: int,
    reindex_result: dict[str, Any] | None,
    backend: str,
) -> dict[str, Any]:
    result_json = job.result_json or {}
    return {
        **result_json,
        "job_backend": backend,
        "execution_mode": "chunked",
        "write_strategy": job.write_strategy,
        "source_index": job.source_index,
        "target_index": update_index,
        "alias_name": job.alias_name,
        "timestamp_field": job.binding.timestamp_field,
        "time_window_days": job.binding.time_window_days,
        "max_documents": max_documents,
        "chunk_size": chunk_size,
        "reindex_result": reindex_result,
        "chunked_enrichment": {
            "update_index": update_index,
            "chunks_total": chunks_total,
            "chunks_completed": 0,
            "chunks_failed": 0,
            "chunks": [],
            "queued_chunks": [],
            "started_at": utc_now().isoformat(),
        },
    }


def _apply_chunk_result(
    *, job: ElasticsearchEnrichmentJob, chunk_result: dict[str, Any]
) -> None:
    result_json = dict(job.result_json or {})
    chunked = dict(result_json.get("chunked_enrichment") or {})
    chunks = [dict(item) for item in chunked.get("chunks") or []]
    chunks = [
        chunk
        for chunk in chunks
        if int(chunk.get("chunk_index", -1)) != int(chunk_result["chunk_index"])
    ]
    chunks.append(chunk_result)
    chunks.sort(key=lambda chunk: int(chunk.get("chunk_index", 0)))
    chunked["chunks"] = chunks
    result_json["chunked_enrichment"] = chunked
    job.result_json = result_json


def _record_queued_chunks(
    *, config: GovernanceApiConfig, job_id: int, queued_chunks: list[dict[str, Any]]
) -> None:
    engine = create_engine_for_config(config)
    try:
        from skeinrank_governance import create_session_factory

        session_factory = create_session_factory(engine)
        with session_factory() as session:
            job = session.scalar(
                select(ElasticsearchEnrichmentJob).where(
                    ElasticsearchEnrichmentJob.id == job_id
                )
            )
            if job is None:
                return
            result_json = dict(job.result_json or {})
            chunked = dict(result_json.get("chunked_enrichment") or {})
            chunked["queued_chunks"] = queued_chunks
            result_json["chunked_enrichment"] = chunked
            job.result_json = result_json
            session.commit()
    finally:
        engine.dispose()


def _mark_job_failed(*, config: GovernanceApiConfig, job_id: int, error: str) -> None:
    engine = create_engine_for_config(config)
    try:
        from skeinrank_governance import create_session_factory

        session_factory = create_session_factory(engine)
        with session_factory() as session:
            job = session.scalar(
                select(ElasticsearchEnrichmentJob).where(
                    ElasticsearchEnrichmentJob.id == job_id
                )
            )
            if job is None:
                return
            job.status = "failed"
            job.error_message = error
            job.finished_at = utc_now()
            session.commit()
    finally:
        engine.dispose()


def _build_chunk_specs(*, max_documents: int, chunk_size: int) -> list[dict[str, int]]:
    chunks_total = max(1, math.ceil(max_documents / chunk_size))
    specs: list[dict[str, int]] = []
    for chunk_index in range(chunks_total):
        offset = chunk_index * chunk_size
        limit = min(chunk_size, max_documents - offset)
        if limit <= 0:
            break
        specs.append({"chunk_index": chunk_index, "offset": offset, "limit": limit})
    return specs


def _chunked_update_index(job: ElasticsearchEnrichmentJob) -> str:
    result_json = job.result_json or {}
    chunked = result_json.get("chunked_enrichment") or {}
    update_index = chunked.get("update_index")
    if isinstance(update_index, str) and update_index:
        return update_index
    if job.write_strategy == "reindex_alias_swap" and job.target_index:
        return job.target_index
    return job.source_index


def _job_max_documents(job: ElasticsearchEnrichmentJob) -> int:
    result_json = job.result_json or {}
    max_documents = result_json.get("max_documents")
    if isinstance(max_documents, int) and max_documents > 0:
        return max_documents
    return 1000


def _job_chunk_size(
    job: ElasticsearchEnrichmentJob, config: GovernanceApiConfig
) -> int:
    result_json = job.result_json or {}
    chunk_size = result_json.get("chunk_size")
    if isinstance(chunk_size, int) and chunk_size > 0:
        return chunk_size
    return max(1, min(config.enrichment_chunk_size, _job_max_documents(job)))
