# Enrichment pause, resume, and checkpointing

The Elasticsearch enrichment beta path supports long-running
Celery jobs with operator-facing pause/resume controls and chunked
checkpoint metadata in the existing job response.

The goal is not to introduce a new scheduler or a new worker backend. The goal
is to make the existing Celery/RabbitMQ enrichment path safer to operate when a
maintenance window closes, workers need to be drained, or an operator wants to
resume from the last completed chunk instead of restarting the whole job.

## Scope

This guide applies to the existing Elasticsearch enrichment job model:

```text
POST /v1/governance/elasticsearch/bindings/{binding_id}/jobs
GET  /v1/governance/elasticsearch/jobs/{job_id}
POST /v1/governance/elasticsearch/jobs/{job_id}/pause
POST /v1/governance/elasticsearch/jobs/{job_id}/resume
POST /v1/governance/elasticsearch/jobs/{job_id}/cancel
```

Pause/resume is intended for the Celery backend:

```bash
export SKEINRANK_GOVERNANCE_API_ENRICHMENT_JOBS_BACKEND=celery
```

The local synchronous backend is still useful for development, but it cannot be
paused from another request while the API process is executing the job.

## Status model

The enrichment job status set now includes two non-terminal pause states:

```text
queued
running
pause_requested
paused
cancel_requested
cancelled
succeeded
failed
```

`pause_requested` means an operator asked a running job to stop at the next safe
checkpoint. Workers do not kill an in-flight bulk update. They finish or skip at
chunk boundaries and then move the job to `paused`.

`paused` means no new chunks should be processed until an admin resumes the job.
The binding still has a pending snapshot, so preflight treats paused jobs as
active and blocks another enrichment job for the same binding.

## Pause

Pause a queued or running job:

```text
POST /v1/governance/elasticsearch/jobs/{job_id}/pause
```

Example body:

```json
{
  "reason": "maintenance window closed"
}
```

Behavior:

- `queued` moves directly to `paused`;
- `running` moves to `pause_requested`;
- workers checkpoint and then move the job to `paused`;
- terminal jobs cannot be paused;
- pause metadata is written to `result_json.pause`.

## Resume

Resume a paused job:

```text
POST /v1/governance/elasticsearch/jobs/{job_id}/resume
```

Example body:

```json
{
  "reason": "maintenance window reopened"
}
```

Behavior:

- only `paused` jobs can be resumed;
- resume requires the Celery backend;
- a paused queued job requeues the coordinator task;
- a paused chunked job requeues only remaining chunks from the checkpoint;
- resume metadata is appended to `result_json.resume_history`.

## Checkpoint payload

Chunked jobs now expose a checkpoint under:

```text
result_json.chunked_enrichment.checkpoint
```

Example:

```json
{
  "chunks_total": 4,
  "completed_chunk_indices": [0, 1],
  "failed_chunk_indices": [],
  "cancelled_chunk_indices": [],
  "remaining_chunk_indices": [2, 3],
  "last_completed_chunk_index": 1,
  "documents_seen": 500,
  "documents_enriched": 183,
  "documents_failed": 0,
  "updated_at": "2026-05-29T12:00:00Z"
}
```

The checkpoint is derived from the existing `chunk_specs` and `chunks` arrays in
`result_json.chunked_enrichment`. No new table is required.

## Operator flow

Recommended long-running job flow:

1. run dry-run and preflight;
2. start a Celery-backed job;
3. inspect `GET /jobs/{job_id}`;
4. pause before the maintenance window closes;
5. wait until status becomes `paused`;
6. inspect `result_json.chunked_enrichment.checkpoint`;
7. resume when workers can continue;
8. inspect final counters and rollout metadata.

## Relationship to cancel and rollback

Pause/resume is not rollback.

- `pause` keeps the job resumable and preserves the pending snapshot.
- `cancel` stops the job and clears the binding pending snapshot.
- `rollback` is only for succeeded `reindex_alias_swap` jobs with completed alias
  swap metadata.

For production-style alias publication, use the blue/green runbook:
[`../deployment/blue-green-alias-swap-runbook.md`](../deployment/blue-green-alias-swap-runbook.md).
