# Elasticsearch enrichment

SkeinRank can enrich an existing Elasticsearch index with canonical terminology context.

The enrichment path is intentionally explicit: users provide the index, text fields, and target field. Start with dry-run mode and use write mode only after the preview is correct.

## CLI enrichment

```bash
cd packages/skeinrank-provider-elasticsearch
poetry install

poetry run skeinrank-es-enrich \
  --url http://localhost:9200 \
  --index docs \
  --text-field title \
  --text-field body \
  --target-field skeinrank \
  --profile default_it \
  --limit 10 \
  --dry-run
```

Dry-run does not modify the index.

Write mode uses bulk partial updates and only adds or replaces the configured target field:

```bash
poetry run skeinrank-es-enrich \
  --url http://localhost:9200 \
  --index docs \
  --text-field title \
  --text-field body \
  --target-field skeinrank \
  --limit 100 \
  --batch-size 25 \
  --write
```

For safety, the CLI requires either `--dry-run` or `--write`; it never writes by default.

## Enrichment payload

The compact default payload stores:

- `profile_id`;
- `snapshot_version`;
- `alias_matcher_backend`;
- `canonical_values`;
- slot-grouped values.

Optional flags can include matched aliases or full debug evidence:

```bash
--include-matched-aliases
--include-evidence
```

Use full evidence only when you need debug detail. It is intentionally not the compact production default.

## Governance bindings

The governance API can store Elasticsearch binding configs. A binding describes where a profile is applied:

- index or index pattern;
- source text fields;
- target enrichment field;
- optional document discriminator field/value;
- optional timestamp field and time window;
- dry-run/write mode;
- write strategy;
- enabled state;
- pinned runtime snapshot.

When multiple profiles share the same index, SkeinRank requires a discriminator such as `team = infra` so enrichment does not mix documents across domains.

## Discovery and dry-run endpoints

Connection and mapping discovery:

```text
GET /v1/governance/elasticsearch/connection/status
GET /v1/governance/elasticsearch/indices
GET /v1/governance/elasticsearch/indices/{index_name}/mapping
```

Binding dry-run:

```text
POST /v1/governance/elasticsearch/bindings/{binding_id}/dry-run
```

Dry-run reads a small sample, extracts text from configured fields, matches active aliases, and returns the payload that would be written. It never writes to Elasticsearch.

## Enrichment jobs

Run a read-only safety preflight before starting a write job:

```text
POST /v1/governance/elasticsearch/bindings/{binding_id}/jobs/preflight
```

The preflight returns `ready`, `blocking_issues`, `warnings`,
`recommended_request`, and safety metadata. It does not create jobs, write
documents, reindex, or swap aliases. See
[`enrichment-beta-hardening.md`](enrichment-beta-hardening.md) for the 61A beta
hardening contract and
[`../deployment/blue-green-alias-swap-runbook.md`](../deployment/blue-green-alias-swap-runbook.md)
for the 61B operator rollout path.

Start a write-mode enrichment job after preflight passes:

```text
POST /v1/governance/elasticsearch/bindings/{binding_id}/jobs
```

Inspect jobs:

```text
GET /v1/governance/elasticsearch/jobs?binding_id=...
GET /v1/governance/elasticsearch/jobs/{job_id}
```

Roll back a completed reindex alias-swap job when conservative rollout metadata
is available:

```text
POST /v1/governance/elasticsearch/jobs/{job_id}/rollback
```

Supported job statuses include:

```text
queued
running
cancel_requested
cancelled
succeeded
failed
```

The local/default backend can run synchronously for development. A Celery/RabbitMQ backend can queue jobs and process chunks with multiple workers.

## Async worker mode

```bash
export SKEINRANK_GOVERNANCE_API_ENRICHMENT_JOBS_BACKEND=celery
export SKEINRANK_GOVERNANCE_API_CELERY_BROKER_URL=amqp://guest:guest@localhost:5672//
```

Run RabbitMQ for local testing:

```bash
docker run --rm -p 5672:5672 -p 15672:15672 rabbitmq:3.13.7-management
```

Run API and worker separately:

```bash
poetry run skeinrank-governance-api --reload
poetry run skeinrank-governance-worker --loglevel=info
```

Chunk size can be configured:

```bash
export SKEINRANK_GOVERNANCE_API_ENRICHMENT_CHUNK_SIZE=500
```

## Job cancellation

Cancel a queued or running job:

```text
POST /v1/governance/elasticsearch/jobs/{job_id}/cancel
```

Queued jobs can move directly to `cancelled`. Running jobs move to `cancel_requested` so workers can stop safely before starting new chunks. Alias swap is prevented when cancellation is requested.

## Evidence lookup

Evidence lookup helps reviewers validate terminology changes against real indexed content:

```text
POST /v1/governance/elasticsearch/bindings/{binding_id}/evidence
```

The endpoint is bounded and read-only. It uses the binding's index, text fields, discriminator, and optional time-window filters, then returns highlighted snippets.

Pending suggestions can store evidence snapshots through:

```text
POST /v1/governance/profiles/{profile_name}/suggestions/{suggestion_id}/evidence/refresh
```
