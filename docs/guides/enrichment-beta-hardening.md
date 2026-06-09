# Operator-controlled search delivery hardening

SkeinRank can publish terminology-derived enrichment artifacts into an existing Elasticsearch/OpenSearch index, but it does not become the owner of the search engine. Profiles, snapshots, bindings, review state, and drift reports remain the source of truth inside SkeinRank. Elasticsearch/OpenSearch receives a derived target field that operators can roll out, validate, and roll back through their normal search operations process.

This guide documents the safety contract for write-mode delivery. It is intentionally explicit: read-only inspection comes first, every write run is confirmed for one concrete plan, and blue/green alias swap is preferred over direct writes.

## Safety model

Operator-controlled delivery uses this sequence:

1. create or update an Elasticsearch/OpenSearch binding;
2. run a read-only dry run;
3. run the read-only job preflight;
4. review the exact plan and warnings;
5. start the job with the current `confirmation_token` from that preflight;
6. inspect job status, counters, rollout metadata, checkpoint state, and cancellation state;
7. roll back alias-swap jobs when rollback metadata is available.

The UI remains an inspection and review surface. Operational delivery is executed through explicit admin/API/CLI/runbook flows, not through casual UI write actions.

## Scope boundary

SkeinRank owns governed terminology artifacts. Search engines execute retrieval.

The delivery path can create a target index, copy the source mapping for a staged reindex, bulk-update the configured target field, and move a serving alias during a reviewed `reindex_alias_swap` rollout. It should not become a general Elasticsearch/OpenSearch management layer for templates, analyzers, cluster settings, synonym graph ownership, or application search logic.

## Preflight endpoint

Before starting a write job, call:

```text
POST /v1/governance/elasticsearch/bindings/{binding_id}/jobs/preflight
```

The request body uses the same plan fields as the start-job endpoint:

```json
{
  "snapshot_version": "platform_ops@2026-05-29T12:00:00Z",
  "max_documents": 1000,
  "chunk_size": 250,
  "alias_name": "platform_knowledge_base_search",
  "target_index_name": "platform_knowledge_base__skeinrank_job_42"
}
```

The endpoint is read-only. It does not create jobs, write documents, reindex, or swap aliases. It returns:

- `ready`;
- `blocking_issues`;
- `warnings`;
- `recommended_request`;
- `confirmation_token` for this exact plan;
- `confirmation_token_fields` showing what the token confirms;
- `safety` metadata such as source index, target index, alias name, snapshot version, chunk size, time window, and any active job for the same binding.

## Per-run confirmation

A write job must include the `confirmation_token` from a fresh preflight response. The token is bound to the specific binding, snapshot version, source index, target index, alias, target field, chunk size, max document limit, filter, and time window.

This keeps `write` mode from becoming a standing approval. Every delivery run confirms one concrete plan. If the plan changes between preflight and start, the API returns `409 Conflict` and asks the operator to re-run preflight.

Start a job after preflight passes:

```text
POST /v1/governance/elasticsearch/bindings/{binding_id}/jobs
```

## Blocking rules

The preflight blocks unsafe starts when:

- Elasticsearch/OpenSearch is not configured;
- the binding is disabled;
- the binding is not in `write` mode;
- another job for the same binding is already `queued`, `running`, `pause_requested`, `paused`, or `cancel_requested`;
- `reindex_alias_swap` is configured with a target index equal to the source index;
- `reindex_alias_swap` is configured with a target index equal to the serving alias;
- the binding has an unsupported write strategy.

The start-job endpoint runs the same preflight before creating a job and also requires the current `confirmation_token` returned by preflight.

## Warnings

Warnings do not block the job. They highlight risks that require operator acceptance:

- `in_place` writes directly to the configured source index and is not reversible by alias rollback; use it only for tightly scoped non-production runs or when an external backup/restore plan exists;
- no time window means the full binding scope may be scanned;
- the selected snapshot has no active aliases;
- `max_documents` is at the API limit.

## Concurrency guard

Only one active delivery job is allowed per binding. A second start request for the same binding is blocked while an earlier job is:

```text
queued
running
pause_requested
paused
cancel_requested
```

Terminal states are not blocked:

```text
succeeded
failed
cancelled
```

This keeps delivery predictable and avoids two workers competing to write or swap the same binding context.

## Existing job endpoints

Inspect jobs:

```text
GET /v1/governance/elasticsearch/jobs?binding_id=...
GET /v1/governance/elasticsearch/jobs/{job_id}
```

Cancel a queued or running job:

```text
POST /v1/governance/elasticsearch/jobs/{job_id}/cancel
```

Roll back a completed reindex alias-swap job when rollback metadata is available:

```text
POST /v1/governance/elasticsearch/jobs/{job_id}/rollback
```

## What this guide does not cover

This guide does not add or assume a scheduler, a new search provider, a new worker backend, or a general-purpose search engine management surface. Blue/green alias-swap operator details are documented in [`../deployment/blue-green-alias-swap-runbook.md`](../deployment/blue-green-alias-swap-runbook.md). Pause/resume/checkpointing is covered by [`enrichment-pause-resume-checkpointing.md`](enrichment-pause-resume-checkpointing.md).
