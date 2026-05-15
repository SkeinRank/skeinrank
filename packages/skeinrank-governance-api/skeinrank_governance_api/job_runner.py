"""Background execution helpers for Elasticsearch enrichment jobs."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from skeinrank_governance.models import ElasticsearchEnrichmentJob, utc_now
from sqlalchemy import select

from .config import GovernanceApiConfig
from .dependencies import create_engine_for_config
from .elasticsearch import (
    ElasticsearchDiscoveryClient,
    ElasticsearchDiscoveryError,
    ElasticsearchDocumentRef,
    compose_source_text,
)
from .observability import start_span
from .observability.metrics import record_enrichment_job
from .runtime_snapshots import (
    alias_tuples_from_snapshot,
    clear_binding_pending_snapshot,
    mark_binding_snapshot_success,
)

CHUNK_RESULT_STATUS_SUCCEEDED = "succeeded"
CHUNK_RESULT_STATUS_FAILED = "failed"
CHUNK_RESULT_STATUS_CANCELLED = "cancelled"
JOB_STATUS_CANCEL_REQUESTED = "cancel_requested"
JOB_STATUS_CANCELLED = "cancelled"
TERMINAL_JOB_STATUSES = {"succeeded", "failed", JOB_STATUS_CANCELLED}
logger = logging.getLogger("skeinrank_governance_api.jobs")


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
        chunk_specs: list[dict[str, Any]] = []
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
            if job.status == JOB_STATUS_CANCEL_REQUESTED:
                _mark_job_cancelled_in_session(
                    job=job, reason="Cancellation was requested before worker startup."
                )
                session.commit()
                session.refresh(job)
                return {"job_id": job_id, "status": job.status, "cancelled": True}
            if job.status in TERMINAL_JOB_STATUSES:
                return {
                    "job_id": job_id,
                    "status": job.status,
                    "skipped": True,
                    "reason": "Job is already in a terminal state.",
                }
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
            logger.info(
                "Elasticsearch enrichment job started",
                extra={
                    "job_id": job.id,
                    "binding_id": job.binding_id,
                    "profile_id": job.profile_id,
                    "job_status": job.status,
                    "write_strategy": job.write_strategy,
                    "snapshot_version": job.snapshot_version,
                    "source_index": job.source_index,
                    "target_index": job.target_index,
                    "alias_name": job.alias_name,
                },
            )

            try:
                span_attrs = {
                    "skeinrank.job_id": job.id,
                    "skeinrank.binding_id": job.binding_id,
                    "skeinrank.profile_id": job.profile_id,
                    "skeinrank.write_strategy": job.write_strategy,
                    "skeinrank.snapshot_version": job.snapshot_version,
                    "skeinrank.source_index": job.source_index,
                    "skeinrank.target_index": job.target_index,
                    "skeinrank.alias_name": job.alias_name,
                }
                with start_span("enrichment.coordinator.prepare", span_attrs):
                    client = ElasticsearchDiscoveryClient(config)
                if not client.is_configured:
                    raise ElasticsearchDiscoveryError(
                        "Elasticsearch URL is not configured."
                    )

                reindex_result, update_index, rollout_metadata = (
                    _prepare_chunked_enrichment(
                        client=client,
                        job=job,
                    )
                )
                max_documents = _job_max_documents(job)
                chunk_size = _job_chunk_size(job, config)
                candidate_refs = _collect_candidate_document_refs(
                    client=client,
                    job=job,
                    update_index=update_index,
                    max_documents=max_documents,
                )
                chunk_specs = _build_chunk_specs(
                    document_refs=candidate_refs, chunk_size=chunk_size
                )
                job.result_json = _initial_chunked_result_json(
                    job=job,
                    max_documents=max_documents,
                    chunk_size=chunk_size,
                    update_index=update_index,
                    chunks_total=len(chunk_specs),
                    reindex_result=reindex_result,
                    rollout_metadata=rollout_metadata,
                    backend=config.enrichment_jobs_backend,
                    chunk_specs=chunk_specs,
                )
                if not chunk_specs:
                    _finalize_empty_chunked_job(job)
                session.commit()
                session.refresh(job)
                if job.status == JOB_STATUS_CANCEL_REQUESTED:
                    _mark_job_cancelled_in_session(
                        job=job,
                        reason="Cancellation was requested before chunks were queued.",
                    )
                    session.commit()
                    session.refresh(job)
                    return {"job_id": job_id, "status": job.status, "cancelled": True}
                if job.status == "succeeded" and not chunk_specs:
                    return {
                        "job_id": job_id,
                        "status": "succeeded",
                        "chunks_queued": 0,
                    }
            except ElasticsearchDiscoveryError as exc:
                job.status = "failed"
                job.error_message = str(exc)
                job.finished_at = utc_now()
                clear_binding_pending_snapshot(job.binding)
                _record_job_metrics(job, status="failed")
                session.commit()
                session.refresh(job)
                logger.warning(
                    "Elasticsearch enrichment job failed during preparation",
                    extra={
                        "job_id": job.id,
                        "binding_id": job.binding_id,
                        "profile_id": job.profile_id,
                        "job_status": job.status,
                        "write_strategy": job.write_strategy,
                        "snapshot_version": job.snapshot_version,
                        "error": str(exc),
                    },
                )
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
                logger.info(
                    "Elasticsearch enrichment chunks queued",
                    extra={
                        "job_id": job_id,
                        "chunks_queued": len(queued_chunks),
                        "queue": config.celery_task_queue,
                    },
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
            if job.status == JOB_STATUS_CANCEL_REQUESTED:
                result = _cancelled_chunk_result(
                    chunk_index=chunk_index,
                    offset=offset,
                    limit=limit,
                    reason="Cancellation requested before chunk execution.",
                )
                _apply_chunk_result(job=job, chunk_result=result)
                _mark_job_cancelled_in_session(
                    job=job, reason="Cancellation requested before chunk execution."
                )
                session.commit()
                session.refresh(job)
                return {"job_id": job_id, "status": job.status, "chunk": result}
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
                clear_binding_pending_snapshot(job.binding)
                session.commit()
                session.refresh(job)
                return {"job_id": job_id, "status": "failed", "chunk": result}

            session.refresh(job)
            _apply_chunk_result(job=job, chunk_result=result)
            if job.status == JOB_STATUS_CANCEL_REQUESTED:
                _mark_job_cancelled_in_session(
                    job=job, reason="Cancellation requested after chunk execution."
                )
            else:
                _maybe_finalize_chunked_job(config=config, session=session, job=job)
            session.commit()
            session.refresh(job)
            return {"job_id": job_id, "status": job.status, "chunk": result}
    finally:
        engine.dispose()


def _cancelled_chunk_result(
    *, chunk_index: int, offset: int, limit: int, reason: str
) -> dict[str, Any]:
    return {
        "chunk_index": chunk_index,
        "offset": offset,
        "limit": limit,
        "status": CHUNK_RESULT_STATUS_CANCELLED,
        "documents_seen": 0,
        "documents_enriched": 0,
        "documents_failed": 0,
        "updated_document_ids": [],
        "matched_documents": [],
        "cancelled": True,
        "reason": reason,
    }


def _mark_job_cancelled_in_session(
    *, job: ElasticsearchEnrichmentJob, reason: str | None = None
) -> None:
    now = utc_now()
    result_json = dict(job.result_json or {})
    cancellation = dict(result_json.get("cancellation") or {})
    cancellation.setdefault("requested_at", now.isoformat())
    cancellation["cancelled_at"] = now.isoformat()
    if reason:
        cancellation.setdefault("reason", reason)
    result_json["cancellation"] = cancellation

    chunked = dict(result_json.get("chunked_enrichment") or {})
    if chunked:
        chunks = list(chunked.get("chunks") or [])
        chunked["chunks_cancelled"] = len(
            [
                chunk
                for chunk in chunks
                if chunk.get("status") == CHUNK_RESULT_STATUS_CANCELLED
            ]
        )
        chunked.setdefault("cancelled_at", now.isoformat())
        result_json["chunked_enrichment"] = chunked

    job.status = JOB_STATUS_CANCELLED
    clear_binding_pending_snapshot(job.binding)
    job.error_message = None
    if job.finished_at is None:
        job.finished_at = now
    job.result_json = result_json


def _prepare_chunked_enrichment(
    *, client: ElasticsearchDiscoveryClient, job: ElasticsearchEnrichmentJob
) -> tuple[dict[str, Any] | None, str, dict[str, Any] | None]:
    binding = job.binding
    if binding.write_strategy == "reindex_alias_swap":
        if not job.target_index:
            raise ElasticsearchDiscoveryError(
                "Target index is required for reindex jobs"
            )
        if not job.alias_name:
            raise ElasticsearchDiscoveryError(
                "Alias name is required for alias-swap jobs"
            )
        previous_alias_indices = client.alias_indices(alias_name=job.alias_name)
        rollout_metadata = _build_reindex_rollout_metadata(
            alias_name=job.alias_name,
            source_index=binding.index_name,
            target_index=job.target_index,
            previous_alias_indices=previous_alias_indices,
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
        return reindex_result, job.target_index, rollout_metadata
    if binding.write_strategy == "in_place":
        return None, binding.index_name, None
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
    alias_entries = alias_tuples_from_snapshot(job.snapshot_json)
    if not alias_entries:
        alias_entries = _active_alias_entries_for_profile(session, binding.profile)
    document_refs = _document_refs_for_chunk(job=job, chunk_index=chunk_index)
    if document_refs is None:
        # Backward-compatible fallback for jobs queued by an older coordinator.
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
    else:
        hits = client.get_documents_by_refs(
            document_refs=document_refs,
            text_fields=list(binding.text_fields),
            filter_field=binding.filter_field,
            timestamp_field=binding.timestamp_field,
        )

    updates: list[tuple[str, dict[str, object]]] = []
    matched_documents: list[dict[str, object]] = []
    for hit in hits:
        text = compose_source_text(hit.source, list(binding.text_fields))
        matched_aliases = _match_alias_entries(text, alias_entries)
        if not matched_aliases:
            continue
        would_write_payload = _dry_run_payload(
            binding, matched_aliases, snapshot_version=job.snapshot_version
        )
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
    if job.status == JOB_STATUS_CANCEL_REQUESTED:
        _mark_job_cancelled_in_session(
            job=job, reason="Cancellation requested before chunked job finalization."
        )
        return

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
    cancelled = [
        chunk
        for chunk in chunks
        if chunk.get("status") == CHUNK_RESULT_STATUS_CANCELLED
    ]

    job.documents_seen = sum(int(chunk.get("documents_seen") or 0) for chunk in chunks)
    job.documents_enriched = sum(
        int(chunk.get("documents_enriched") or 0) for chunk in chunks
    )
    job.documents_failed = sum(
        int(chunk.get("documents_failed") or 0) for chunk in chunks
    )

    if cancelled:
        _mark_job_cancelled_in_session(
            job=job,
            reason=cancelled[0].get("reason")
            or "One or more enrichment chunks were cancelled.",
        )
        return

    if failed:
        job.status = "failed"
        job.error_message = (
            failed[0].get("error") or "One or more enrichment chunks failed."
        )
        clear_binding_pending_snapshot(job.binding)
        job.finished_at = utc_now()
        _record_job_metrics(job, status="failed")
        return

    if (
        chunks_total
        and len(completed) >= chunks_total
        and not chunked.get("finalized_at")
    ):
        alias_result = None
        rollout_metadata = result_json.get("rollout")
        if job.write_strategy == "reindex_alias_swap":
            if not job.alias_name:
                raise ElasticsearchDiscoveryError(
                    "Alias name is required for alias-swap jobs"
                )
            client = ElasticsearchDiscoveryClient(config)
            if not isinstance(rollout_metadata, dict):
                rollout_metadata = _build_reindex_rollout_metadata(
                    alias_name=job.alias_name,
                    source_index=job.source_index,
                    target_index=_chunked_update_index(job),
                    previous_alias_indices=client.alias_indices(
                        alias_name=job.alias_name
                    ),
                )
            alias_result = client.swap_alias(
                alias_name=job.alias_name,
                target_index=_chunked_update_index(job),
            )
            rollout_metadata = _complete_reindex_rollout_metadata(
                rollout_metadata=rollout_metadata,
                alias_result=alias_result,
                new_alias_indices=client.alias_indices(alias_name=job.alias_name),
            )
        updated_document_ids: list[str] = []
        matched_documents: list[dict[str, object]] = []
        for chunk in chunks:
            updated_document_ids.extend(chunk.get("updated_document_ids") or [])
            matched_documents.extend(chunk.get("matched_documents") or [])
        chunked["finalized_at"] = utc_now().isoformat()
        chunked["chunks_completed"] = len(completed)
        chunked["chunks_failed"] = 0
        chunked["chunks_cancelled"] = 0
        job.result_json = {
            **result_json,
            "snapshot_version": job.snapshot_version,
            "previous_snapshot_version": job.previous_snapshot_version,
            "snapshot_aliases_total": len(
                (job.snapshot_json or {}).get("alias_entries") or []
            ),
            "documents_seen": job.documents_seen,
            "documents_enriched": job.documents_enriched,
            "documents_failed": job.documents_failed,
            "updated_document_ids": updated_document_ids,
            "matched_documents": matched_documents,
            "alias_result": alias_result,
            "rollout": rollout_metadata,
            "chunked_enrichment": chunked,
        }
        job.status = "succeeded"
        job.error_message = None
        job.finished_at = utc_now()
        mark_binding_snapshot_success(
            binding=job.binding, job=job, completed_at=job.finished_at
        )
        _record_job_metrics(job, status="succeeded")
        logger.info(
            "Elasticsearch enrichment job succeeded",
            extra={
                "job_id": job.id,
                "binding_id": job.binding_id,
                "profile_id": job.profile_id,
                "job_status": job.status,
                "write_strategy": job.write_strategy,
                "snapshot_version": job.snapshot_version,
                "documents_seen": job.documents_seen,
                "documents_enriched": job.documents_enriched,
                "documents_failed": job.documents_failed,
            },
        )
    else:
        chunked["chunks_completed"] = len(completed)
        chunked["chunks_failed"] = len(failed)
        chunked["chunks_cancelled"] = len(cancelled)
        job.result_json = {**result_json, "chunked_enrichment": chunked}


def _initial_chunked_result_json(
    *,
    job: ElasticsearchEnrichmentJob,
    max_documents: int,
    chunk_size: int,
    update_index: str,
    chunks_total: int,
    reindex_result: dict[str, Any] | None,
    rollout_metadata: dict[str, Any] | None,
    backend: str,
    chunk_specs: list[dict[str, Any]],
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
        "snapshot_version": job.snapshot_version,
        "previous_snapshot_version": job.previous_snapshot_version,
        "snapshot_aliases_total": len(
            (job.snapshot_json or {}).get("alias_entries") or []
        ),
        "timestamp_field": job.binding.timestamp_field,
        "time_window_days": job.binding.time_window_days,
        "max_documents": max_documents,
        "chunk_size": chunk_size,
        "reindex_result": reindex_result,
        "rollout": rollout_metadata,
        "chunked_enrichment": {
            "update_index": update_index,
            "candidate_documents_total": sum(
                len(spec.get("document_refs") or []) for spec in chunk_specs
            ),
            "chunks_total": chunks_total,
            "chunks_completed": 0,
            "chunks_failed": 0,
            "chunks_cancelled": 0,
            "chunk_specs": [
                {
                    "chunk_index": int(spec["chunk_index"]),
                    "offset": int(spec["offset"]),
                    "limit": int(spec["limit"]),
                    "document_refs": [
                        {"id": ref.id, "index": ref.index}
                        for ref in spec.get("document_refs") or []
                    ],
                }
                for spec in chunk_specs
            ],
            "chunks": [],
            "queued_chunks": [],
            "started_at": utc_now().isoformat(),
        },
    }


def _rollback_candidate_index(
    previous_alias_indices: list[str], target_index: str
) -> str | None:
    candidates = [index for index in previous_alias_indices if index != target_index]
    if len(candidates) == 1:
        return candidates[0]
    return None


def _build_reindex_rollout_metadata(
    *,
    alias_name: str,
    source_index: str,
    target_index: str,
    previous_alias_indices: list[str],
) -> dict[str, Any]:
    rollback_candidate = _rollback_candidate_index(previous_alias_indices, target_index)
    return {
        "strategy": "reindex_alias_swap",
        "status": "prepared",
        "alias_name": alias_name,
        "source_index": source_index,
        "target_index": target_index,
        "previous_alias_indices": previous_alias_indices,
        "new_alias_indices": [],
        "rollback_candidate_index": rollback_candidate,
        "rollback_available": rollback_candidate is not None,
        "alias_swap_completed": False,
        "alias_swap_started_at": utc_now().isoformat(),
        "alias_swapped_at": None,
        "alias_result": None,
        "cleanup_hint": (
            "If this rollout is cancelled or fails before alias swap, "
            f"review or delete target index {target_index}."
        ),
        "rollback_hint": (
            f"Manual rollback candidate: repoint alias {alias_name} to {rollback_candidate}."
            if rollback_candidate
            else "No single previous alias index was found for automatic rollback planning."
        ),
    }


def _complete_reindex_rollout_metadata(
    *,
    rollout_metadata: dict[str, Any],
    alias_result: dict[str, Any] | None,
    new_alias_indices: list[str],
) -> dict[str, Any]:
    return {
        **rollout_metadata,
        "status": "alias_swapped",
        "new_alias_indices": new_alias_indices,
        "alias_swap_completed": True,
        "alias_swapped_at": utc_now().isoformat(),
        "alias_result": alias_result,
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
            clear_binding_pending_snapshot(job.binding)
            session.commit()
    finally:
        engine.dispose()


def _as_utc_aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _record_job_metrics(job: ElasticsearchEnrichmentJob, *, status: str) -> None:
    duration_seconds = None
    started_at = _as_utc_aware(job.started_at)
    finished_at = _as_utc_aware(job.finished_at)
    if started_at and finished_at:
        duration_seconds = max((finished_at - started_at).total_seconds(), 0.0)
    record_enrichment_job(
        status=status,
        write_strategy=job.write_strategy,
        duration_seconds=duration_seconds,
        documents_seen=job.documents_seen or 0,
        documents_enriched=job.documents_enriched or 0,
        documents_failed=job.documents_failed or 0,
    )


def _collect_candidate_document_refs(
    *,
    client: ElasticsearchDiscoveryClient,
    job: ElasticsearchEnrichmentJob,
    update_index: str,
    max_documents: int,
) -> list[ElasticsearchDocumentRef]:
    binding = job.binding
    return client.search_document_refs(
        index_name=update_index,
        limit=max_documents,
        filter_field=binding.filter_field,
        filter_value=binding.filter_value,
        timestamp_field=binding.timestamp_field,
        time_window_days=binding.time_window_days,
    )


def _build_chunk_specs(
    *, document_refs: list[ElasticsearchDocumentRef], chunk_size: int
) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    for chunk_index, offset in enumerate(range(0, len(document_refs), chunk_size)):
        refs = document_refs[offset : offset + chunk_size]
        if not refs:
            continue
        specs.append(
            {
                "chunk_index": chunk_index,
                "offset": offset,
                "limit": len(refs),
                "document_refs": refs,
            }
        )
    return specs


def _document_refs_for_chunk(
    *, job: ElasticsearchEnrichmentJob, chunk_index: int
) -> list[ElasticsearchDocumentRef] | None:
    result_json = job.result_json or {}
    chunked = result_json.get("chunked_enrichment") or {}
    chunk_specs = chunked.get("chunk_specs")
    if not isinstance(chunk_specs, list):
        return None

    for spec in chunk_specs:
        if not isinstance(spec, dict):
            continue
        if int(spec.get("chunk_index", -1)) != int(chunk_index):
            continue
        refs_payload = spec.get("document_refs")
        if not isinstance(refs_payload, list):
            return []
        refs: list[ElasticsearchDocumentRef] = []
        for item in refs_payload:
            if not isinstance(item, dict):
                continue
            document_id = str(item.get("id") or "").strip()
            index_name = str(item.get("index") or "").strip()
            if document_id and index_name:
                refs.append(ElasticsearchDocumentRef(id=document_id, index=index_name))
        return refs
    return []


def _finalize_empty_chunked_job(job: ElasticsearchEnrichmentJob) -> None:
    now = utc_now()
    result_json = dict(job.result_json or {})
    chunked = dict(result_json.get("chunked_enrichment") or {})
    chunked["chunks_completed"] = 0
    chunked["chunks_failed"] = 0
    chunked["chunks_cancelled"] = 0
    chunked["finalized_at"] = now.isoformat()
    job.documents_seen = 0
    job.documents_enriched = 0
    job.documents_failed = 0
    job.status = "succeeded"
    job.error_message = None
    job.finished_at = now
    job.result_json = {
        **result_json,
        "documents_seen": 0,
        "documents_enriched": 0,
        "documents_failed": 0,
        "updated_document_ids": [],
        "matched_documents": [],
        "alias_result": None,
        "chunked_enrichment": chunked,
    }
    _record_job_metrics(job, status="succeeded")


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
