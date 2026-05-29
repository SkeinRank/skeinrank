# Enrichment Beta hardening

Patch 61A tightens the Elasticsearch enrichment beta path without changing the
underlying worker architecture. The goal is to make write-mode enrichment harder
to start accidentally and easier to inspect before a job is queued.

## Safety model

Enrichment remains an operator-controlled workflow:

1. create or update an Elasticsearch binding;
2. run a read-only dry-run;
3. run the read-only job preflight;
4. start exactly one active job per binding;
5. inspect job status, counters, rollout metadata, and cancellation state.

The UI should treat this as a beta operator path, not as a casual production
button. Legacy/admin cockpit write tools stay disabled unless local development
explicitly enables them.

## Preflight endpoint

Before starting a write job, call:

```text
POST /v1/governance/elasticsearch/bindings/{binding_id}/jobs/preflight
```

The request body uses the same fields as the start-job endpoint:

```json
{
  "snapshot_version": "platform_ops@2026-05-29T12:00:00Z",
  "max_documents": 1000,
  "chunk_size": 250,
  "alias_name": "platform_knowledge_base_search",
  "target_index_name": "platform_knowledge_base__skeinrank_job_42"
}
```

The endpoint is read-only. It does not create jobs, write documents, reindex, or
swap aliases. It returns:

- `ready`;
- `blocking_issues`;
- `warnings`;
- `recommended_request`;
- `safety` metadata such as source index, target index, alias name, snapshot
  version, chunk size, time window, and any active job for the same binding.

## Blocking rules

The preflight blocks unsafe starts when:

- Elasticsearch is not configured;
- the binding is disabled;
- the binding is not in `write` mode;
- another job for the same binding is already `queued`, `running`,
  `pause_requested`, `paused`, or `cancel_requested`;
- `reindex_alias_swap` is configured with a target index equal to the source
  index;
- `reindex_alias_swap` is configured with a target index equal to the serving
  alias;
- the binding has an unsupported write strategy.

The start-job endpoint now runs the same preflight before creating a job. If the
preflight fails, the API returns `409` with the blocking issues.

## Warnings

Warnings do not block the job. They highlight beta risks such as:

- `in_place` writes directly to the configured source index;
- no time window means the full binding scope may be scanned;
- the selected snapshot has no active aliases;
- `max_documents` is at the API limit.

## Concurrency guard

Only one active enrichment job is allowed per binding. A second start request for
the same binding is blocked while an earlier job is:

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

This keeps beta enrichment predictable and avoids two workers competing to write
or swap the same binding context.

## Existing job endpoints

Start a job after preflight passes:

```text
POST /v1/governance/elasticsearch/bindings/{binding_id}/jobs
```

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

## What this patch does not do

Patch 61A does not add a new worker backend, a scheduler, a new Elasticsearch
provider, or a new production deployment mechanism. Blue/green alias-swap operator details are documented in
[`../deployment/blue-green-alias-swap-runbook.md`](../deployment/blue-green-alias-swap-runbook.md).
Pause/resume/checkpointing is covered by [`enrichment-pause-resume-checkpointing.md`](enrichment-pause-resume-checkpointing.md).
