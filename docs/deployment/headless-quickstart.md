# Headless quickstart

This guide runs the Phase A headless path without the React UI, Elasticsearch,
RabbitMQ, or Celery workers. It is intended for CI/CD experiments, agent/tool
integrations, and local checks of the dictionary -> binding -> snapshot artifact
workflow.

The headless stack starts only:

```text
PostgreSQL -> migrations -> Governance API
```

It exposes the same headless API facade used by automation:

```text
POST /v1/headless/dictionaries/validate
POST /v1/headless/dictionaries/apply
GET  /v1/headless/dictionaries/export?profile_name=...
GET  /v1/headless/snapshots/export?binding_id=...
```

## Start the headless stack

From the repository root:

```bash
docker compose \
  --env-file deploy/docker/headless.env.example \
  -f docker-compose.headless.yml \
  up --build -d
```

Health check:

```bash
curl -s http://127.0.0.1:8010/readyz | python -m json.tool
```

The headless profile disables auth by default because it is local-only and meant
for quick automation smoke tests. Use `docker-compose.prod.yml` and
`docs/deployment/security.md` for secured deployments.

## Run the golden path helper

The helper applies the example dictionary, creates a local binding, exports a
runtime snapshot artifact, and prints a compact artifact summary.

```bash
deploy/docker/scripts/headless-golden-path.sh
```

By default the helper writes:

```text
snapshots/infra_incidents.binding.v1.json
```

You can override paths through environment variables:

```bash
SKEINRANK_HEADLESS_API_URL=http://127.0.0.1:8010 \
SKEINRANK_HEADLESS_DICTIONARY_FILE=examples/migration/console_dictionary.example.json \
SKEINRANK_HEADLESS_SNAPSHOT_OUTPUT=snapshots/infra_incidents.binding.v1.json \
deploy/docker/scripts/headless-golden-path.sh
```

## Manual golden path

### 1. Apply dictionary spec v1

```bash
curl -s -X POST "http://127.0.0.1:8010/v1/headless/dictionaries/apply" \
  -H "Content-Type: application/json" \
  --data-binary @examples/migration/console_dictionary.example.json \
  | python -m json.tool
```

### 2. Create a local binding

The binding is a runtime context. This step does not require a live Elasticsearch
cluster; it records where and how this profile would be applied.

```bash
curl -s -X POST "http://127.0.0.1:8010/v1/governance/elasticsearch/bindings" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "infra incidents local runtime",
    "profile_name": "infra_incidents",
    "description": "Headless quickstart binding for runtime artifact export.",
    "index_name": "infra_incidents_docs",
    "text_fields": ["title", "body"],
    "target_field": "skeinrank",
    "mode": "dry_run",
    "write_strategy": "reindex_alias_swap",
    "is_enabled": true
  }' | python -m json.tool
```

Save the returned `id` as `BINDING_ID`.

### 3. Export a runtime snapshot artifact

```bash
curl -s "http://127.0.0.1:8010/v1/headless/snapshots/export?binding_id=$BINDING_ID&snapshot_version=infra_incidents@v1" \
  -o snapshots/infra_incidents.binding.v1.json
```

The artifact is a portable, binding-scoped read model:

```text
schema_version: skeinrank.runtime_snapshot_artifact.v1
artifact_type: runtime_snapshot
binding: runtime search context
profile: terminology profile identity
runtime_snapshot: compiled aliases and canonical terms
manifest: checksum, source, version, and alias count
```

### 4. Inspect the artifact with the CLI

If you are running the Poetry environment locally:

```bash
cd packages/skeinrank-governance-api
poetry run skeinrank-migrate snapshot-inspect ../../snapshots/infra_incidents.binding.v1.json
```

This validates the artifact schema and manifest checksum, then prints a summary.

## Stop and reset

Stop containers while keeping the PostgreSQL volume:

```bash
docker compose -f docker-compose.headless.yml down
```

Remove the local headless PostgreSQL volume:

```bash
docker compose -f docker-compose.headless.yml down -v
```

## When to use this profile

Use `docker-compose.headless.yml` when you want to verify the runtime contracts
without operating the full platform preview. Use `docker-compose.dev.yml` when
you need the UI, Elasticsearch enrichment jobs, RabbitMQ, worker, Prometheus, or
Grafana.
