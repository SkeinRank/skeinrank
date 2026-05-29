# Blue/green alias-swap runbook

Patch 61B documents the production-oriented Elasticsearch enrichment rollout path
that already exists in the governance API: `reindex_alias_swap` jobs create a new
target index, enrich that index, then atomically move the serving alias after the
job succeeds.

The runbook is intentionally operator-focused. It does not introduce a new
scheduler, worker backend, CLI, or Elasticsearch endpoint. It uses the existing
61A preflight, enrichment job, job inspection, cancellation, and rollback APIs.

## Mental model

```text
blue index  = the current physical index behind the serving alias
green index = the new physical target index prepared by an enrichment job
alias       = the stable name used by the application search backend
```

Applications should search through the alias, not through the physical index:

```text
application search -> platform_knowledge_base_search -> platform_knowledge_base_v1
```

A `reindex_alias_swap` rollout prepares a new target index:

```text
platform_knowledge_base_v2
```

When enrichment completes, SkeinRank swaps the alias:

```text
platform_knowledge_base_search -> platform_knowledge_base_v2
```

This keeps live search away from partially enriched data.

## Existing API surface

Use only these existing governance endpoints:

```text
GET  /v1/governance/elasticsearch/connection/status
GET  /v1/governance/elasticsearch/indices
GET  /v1/governance/elasticsearch/indices/{index_name}/mapping
POST /v1/governance/elasticsearch/bindings/{binding_id}/dry-run
POST /v1/governance/elasticsearch/bindings/{binding_id}/jobs/preflight
POST /v1/governance/elasticsearch/bindings/{binding_id}/jobs
GET  /v1/governance/elasticsearch/jobs?binding_id=...
GET  /v1/governance/elasticsearch/jobs/{job_id}
POST /v1/governance/elasticsearch/jobs/{job_id}/cancel
POST /v1/governance/elasticsearch/jobs/{job_id}/rollback
```

There is no special `alias-swap` endpoint. The alias swap happens inside a
successful `reindex_alias_swap` enrichment job.

## Preconditions

Before running blue/green enrichment, verify that:

1. Elasticsearch is configured and reachable.
2. The binding is enabled and uses `mode = write`.
3. The binding uses `write_strategy = reindex_alias_swap`.
4. The application search backend reads from the serving alias.
5. The requested `target_index_name` is a new physical index name.
6. The requested `target_index_name` is not the source index.
7. The requested `target_index_name` is not the serving alias.
8. Only one active enrichment job exists per binding.

Patch 61A preflight enforces the dangerous cases before a job is created.

## Step 1 — Inspect connection and mappings

```bash
curl -sS \
  -H "X-SkeinRank-Role: admin" \
  "$SKEINRANK_CONSOLE_API_URL/v1/governance/elasticsearch/connection/status"
```

```bash
curl -sS \
  -H "X-SkeinRank-Role: admin" \
  "$SKEINRANK_CONSOLE_API_URL/v1/governance/elasticsearch/indices"
```

```bash
curl -sS \
  -H "X-SkeinRank-Role: admin" \
  "$SKEINRANK_CONSOLE_API_URL/v1/governance/elasticsearch/indices/platform_knowledge_base_v1/mapping"
```

This is a read-only check. It does not create an enrichment job and does not
write to Elasticsearch.

## Step 2 — Run dry-run on the binding

```bash
curl -sS -X POST \
  -H "X-SkeinRank-Role: admin" \
  -H "Content-Type: application/json" \
  "$SKEINRANK_CONSOLE_API_URL/v1/governance/elasticsearch/bindings/$SKEINRANK_BINDING_ID/dry-run" \
  -d '{"limit": 3}'
```

Review the returned `would_write` payloads. Continue only when the target field,
matched aliases, canonical values, discriminator filters, and time window look
correct.

## Step 3 — Run alias-swap preflight

Use a target index that clearly identifies the rollout:

```text
<source-index>__skeinrank_<snapshot-or-job-id>
```

Example request body:

```json
{
  "snapshot_version": "platform_ops@2026-05-29T12:00:00Z",
  "max_documents": 1000,
  "chunk_size": 250,
  "alias_name": "platform_knowledge_base_search",
  "target_index_name": "platform_knowledge_base__skeinrank_20260529_1200"
}
```

Run the read-only preflight:

```bash
curl -sS -X POST \
  -H "X-SkeinRank-Role: admin" \
  -H "Content-Type: application/json" \
  "$SKEINRANK_CONSOLE_API_URL/v1/governance/elasticsearch/bindings/$SKEINRANK_BINDING_ID/jobs/preflight" \
  -d @examples/blue-green-alias-swap/preflight-request.json
```

The response must have:

```json
{
  "ready": true,
  "blocking_issues": []
}
```

Warnings are allowed, but operators should explicitly accept them before
starting the job.

## Step 4 — Start the enrichment job

Use the same request shape as preflight:

```bash
curl -sS -X POST \
  -H "X-SkeinRank-Role: admin" \
  -H "Content-Type: application/json" \
  "$SKEINRANK_CONSOLE_API_URL/v1/governance/elasticsearch/bindings/$SKEINRANK_BINDING_ID/jobs" \
  -d @examples/blue-green-alias-swap/start-job-request.json
```

The start endpoint runs the same safety checks again. If another job is already
`queued`, `running`, or `cancel_requested` for the binding, the request returns
`409` instead of creating a competing rollout.

## Step 5 — Monitor job state

List binding jobs:

```bash
curl -sS \
  -H "X-SkeinRank-Role: admin" \
  "$SKEINRANK_CONSOLE_API_URL/v1/governance/elasticsearch/jobs?binding_id=$SKEINRANK_BINDING_ID"
```

Inspect one job:

```bash
curl -sS \
  -H "X-SkeinRank-Role: admin" \
  "$SKEINRANK_CONSOLE_API_URL/v1/governance/elasticsearch/jobs/$SKEINRANK_JOB_ID"
```

Expected terminal success state:

```text
succeeded
```

For `reindex_alias_swap`, inspect `result_json.rollout`:

```json
{
  "strategy": "reindex_alias_swap",
  "status": "alias_swapped",
  "alias_name": "platform_knowledge_base_search",
  "previous_alias_indices": ["platform_knowledge_base_v1"],
  "new_alias_indices": ["platform_knowledge_base__skeinrank_20260529_1200"],
  "alias_swap_completed": true,
  "rollback_available": true,
  "rollback_candidate_index": "platform_knowledge_base_v1"
}
```

## Step 6 — Cancel before publish when needed

Cancel a queued or running job:

```bash
curl -sS -X POST \
  -H "X-SkeinRank-Role: admin" \
  -H "Content-Type: application/json" \
  "$SKEINRANK_CONSOLE_API_URL/v1/governance/elasticsearch/jobs/$SKEINRANK_JOB_ID/cancel" \
  -d '{"reason": "Operator stopped rollout during validation."}'
```

Queued jobs can become `cancelled`. Running jobs become `cancel_requested` so the
worker can stop safely between chunks. Alias swap is prevented when cancellation
is requested.

If the job created a green index but did not swap the alias, review the target
index manually before deleting it. The governance API does not expose an index
delete endpoint.

## Step 7 — Roll back after alias swap

Rollback is available only when the completed job has conservative rollout
metadata:

- job status is `succeeded`;
- write strategy is `reindex_alias_swap`;
- alias swap completed;
- exactly one previous alias target was captured;
- the alias still points to the expected post-rollout index.

Run rollback:

```bash
curl -sS -X POST \
  -H "X-SkeinRank-Role: admin" \
  -H "Content-Type: application/json" \
  "$SKEINRANK_CONSOLE_API_URL/v1/governance/elasticsearch/jobs/$SKEINRANK_JOB_ID/rollback" \
  -d @examples/blue-green-alias-swap/rollback-request.json
```

Successful rollback records `result_json.rollout.rollback` and marks rollback as
completed. It does not delete the green index. Deleting old indices remains an
operator decision outside SkeinRank.

## Rollback decision matrix

| Situation | Action |
| --- | --- |
| Preflight has blocking issues | Do not start the job. Fix the binding or request body. |
| Job is `queued` | Cancel the job. No alias swap has happened. |
| Job is `running` | Request cancellation and wait for `cancel_requested` handling. |
| Job failed before alias swap | Inspect `result_json.rollout.cleanup_hint`; alias should still point to blue. |
| Job succeeded and search regression is bad | Use `POST /v1/governance/elasticsearch/jobs/{job_id}/rollback` if available. |
| Rollback is not available | Repoint the alias manually through the Elasticsearch operator path used by your team. |

## Operator checklist

A short checklist is available in
[`examples/blue-green-alias-swap/operator-checklist.md`](../../examples/blue-green-alias-swap/operator-checklist.md).

## What this runbook does not add

Patch 61B does not add:

- a new API endpoint for alias swap;
- a new CLI command;
- automatic index cleanup;
- pause/resume/checkpointing semantics;
- a scheduler;
- a Terraform provider;
- an Elasticsearch index delete endpoint.

Those remain separate operator or future-product concerns. Patch 61C is reserved
for pause/resume/checkpointing polish.


## Pause/resume during long runs

For Celery-backed enrichment jobs, operators can pause at chunk boundaries and resume from the remaining checkpoint before the alias swap finalization step. See [`../guides/enrichment-pause-resume-checkpointing.md`](../guides/enrichment-pause-resume-checkpointing.md).
