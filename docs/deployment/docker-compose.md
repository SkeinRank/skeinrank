# Docker Compose full stack install guide

This guide covers both public-beta release Compose and the source-built development stack.

## Public beta quick start using GHCR images

Use the root `docker-compose.yml` when you want to try SkeinRank from published GHCR images without building the Python API or React UI locally:

```bash
cp .env.example .env
docker compose up -d
```

Open:

```text
UI:        http://127.0.0.1:5173
API docs:  http://127.0.0.1:8010/docs
```

Then load the guided demo:

```bash
make demo-reset
```

The release stack uses one image tag variable for the SkeinRank service images:

```env
SKEINRANK_IMAGE_TAG=v0.10.0-beta.1
```

Full release-compose notes are in [`release-compose.md`](release-compose.md).

## Source-built development stack

This guide shows how to run the SkeinRank governance platform locally as a full development stack.

The stack is intended for local development, integration testing, and product smoke tests. It starts the components needed to verify the main SkeinRank flow end-to-end:

```text
dictionary import
-> Elasticsearch binding
-> enrichment job
-> runtime search
-> UI validation
```

For production security hardening, see `docs/deployment/security.md`, `docs/deployment/production-compose.md`, and `docker-compose.prod.yml`. Do not expose this development stack directly to the internet.

## Production-oriented profile

The development stack is not a production security profile. For a production-oriented starting point, use:

```bash
cp .env.production.example .env
docker compose --env-file .env -f docker-compose.prod.yml config
docker compose --env-file .env -f docker-compose.prod.yml up --build -d
```

Read the security and production Compose guides first:

```text
docs/deployment/security.md
docs/deployment/production-compose.md
```

The production profile enables fail-fast configuration checks when `SKEINRANK_ENV=production` or `SKEINRANK_GOVERNANCE_API_ENV=production`. It does not publish PostgreSQL or RabbitMQ ports, requires auth, rejects wildcard CORS, refuses unsafe default secrets, and can optionally validate a configured Elasticsearch/OpenSearch URL through `/readyz`. Patch 46A adds a production env example, ops one-shot services, optional Prometheus/Grafana, Docker log rotation, and `deploy/docker/scripts/prod-smoke-test.sh`.

## What the dev stack starts

`docker-compose.dev.yml` starts:

| Service | Purpose | Default local URL |
| --- | --- | --- |
| PostgreSQL | Governance state: profiles, terms, users, bindings, jobs | `127.0.0.1:15432` |
| Elasticsearch | Searchable documents and `skeinrank` enrichment fields | `http://127.0.0.1:19200` |
| RabbitMQ | Celery broker for enrichment jobs | `127.0.0.1:5672` |
| RabbitMQ Management | Broker UI | `http://127.0.0.1:15672` |
| Governance API | Control-plane and runtime API | `http://127.0.0.1:8010` |
| Governance Worker | Celery worker for async enrichment | internal service |
| UI | SkeinRank web console | `http://127.0.0.1:5173` |
| Migration service | One-shot Alembic migration runner | exits after success |

## Prerequisites

- Docker Desktop or Docker Engine with Docker Compose v2.
- At least 4 GB of free memory for the local stack.
- Ports `15432`, `19200`, `5672`, `15672`, `8010`, and `5173` available on `127.0.0.1`.

If a port is already in use, either stop the conflicting process or override the port in `.env`.

## Start the stack

From the repository root:

```bash
cp .env.example .env
docker compose -f docker-compose.dev.yml up --build
```

Open the UI:

```text
http://127.0.0.1:5173
```

Default development login from `.env.example`:

```text
username: admin
password: change-me
```

The default credentials are for local development only.

## Populate the platform preview

For a screenshot-ready console, seed the local stack with a platform-operations knowledge base:

```bash
make demo-reset
```

This runs `examples/platform_ops_demo/seed_platform_demo.py`. It creates the `platform_ops` profile, loads `platform_knowledge_base`, creates a binding, adds evidence-backed AI Inbox proposals, refreshes evidence snapshots, starts an enrichment job, and prints the 59A guided Control Plane walkthrough. See [`../guides/seeded-demo-walkthrough.md`](../guides/seeded-demo-walkthrough.md) for the product tour.

Use the non-destructive variant after the first run:

```bash
make demo-seed
```

Check existing demo state without writing data:

```bash
make demo-status
```

Open Search Playground with:

```text
k8s pg timeout during phoenix rollout
```

## Verify service health

Use `GET /livez` for process liveness and `GET /readyz` for deployment readiness in a second terminal:

```bash
curl http://127.0.0.1:8010/livez | python -m json.tool
curl http://127.0.0.1:8010/readyz | python -m json.tool
```

Expected high-level result:

```json
{
  "status": "ok",
  "database": {"ok": true},
  "elasticsearch": {"ok": true, "configured": true}
}
```

You can also run the bundled smoke helper:

```bash
deploy/docker/scripts/dev-smoke-test.sh
```

Get an admin token:

```bash
export ADMIN_TOKEN=$(
  curl -s -X POST http://127.0.0.1:8010/v1/auth/login \
    -H "Content-Type: application/json" \
    -d '{"username":"admin","password":"change-me"}' \
  | python -c 'import json,sys; print(json.load(sys.stdin)["access_token"])'
)

echo "$ADMIN_TOKEN"
```

Verify Elasticsearch connectivity through the Governance API:

```bash
curl -s http://127.0.0.1:8010/v1/governance/elasticsearch/connection/status \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  | python -m json.tool
```

Expected high-level result:

```json
{
  "configured": true,
  "ok": true
}
```

## First end-to-end search

This smoke test creates a small Elasticsearch index, imports the example dictionary, creates a binding, runs an enrichment job, and searches through the runtime API.

### 1. Create a demo Elasticsearch index

```bash
export ES_URL="http://127.0.0.1:19200"

curl -s -X DELETE "$ES_URL/kb" >/dev/null || true

curl -s -X PUT "$ES_URL/kb" \
  -H "Content-Type: application/json" \
  -d '{
    "mappings": {
      "properties": {
        "title": {"type": "text"},
        "text": {"type": "text"},
        "source_type": {"type": "keyword"},
        "created_at": {"type": "date"},
        "skeinrank": {
          "properties": {
            "profile_id": {"type": "keyword"},
            "binding_id": {"type": "integer"},
            "binding_name": {"type": "keyword"},
            "snapshot_version": {"type": "keyword"},
            "canonical_values": {"type": "keyword"},
            "matched_aliases": {"type": "keyword"},
            "slots": {"type": "object", "dynamic": true},
            "matched_aliases_by_value": {"type": "object", "dynamic": true}
          }
        }
      }
    }
  }' | python -m json.tool
```

Add demo documents:

```bash
cat > /tmp/skeinrank-kb.bulk.ndjson <<'NDJSON'
{"index":{"_index":"kb","_id":"doc_001"}}
{"title":"K8s rollout incident","text":"k8s rollout failed after pg migration. The api-server had timeout errors.","source_type":"incident","created_at":"2026-05-01T10:00:00Z"}
{"index":{"_index":"kb","_id":"doc_002"}}
{"title":"Database latency","text":"Postgres latency spike during backup window. Billing service slowed down.","source_type":"runbook","created_at":"2026-05-02T10:00:00Z"}
{"index":{"_index":"kb","_id":"doc_003"}}
{"title":"Cache failover","text":"Redis failover caused connection reset errors.","source_type":"incident","created_at":"2026-05-03T10:00:00Z"}
NDJSON

curl -s -X POST "$ES_URL/_bulk?refresh=true" \
  -H "Content-Type: application/x-ndjson" \
  --data-binary @/tmp/skeinrank-kb.bulk.ndjson \
  | python -m json.tool
```

### 2. Import the example dictionary

```bash
curl -s -X POST http://127.0.0.1:8010/v1/console/dictionary/import \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d @examples/migration/console_dictionary.example.json \
  | python -m json.tool
```

The example dictionary creates the `infra_incidents` profile with aliases such as `k8s`, `kube`, `postgres`, and `pg`.

### 3. Create an Elasticsearch binding

```bash
export BINDING_ID=$(
  curl -s -X POST http://127.0.0.1:8010/v1/governance/elasticsearch/bindings \
    -H "Authorization: Bearer $ADMIN_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{
      "name": "kb dev smoke",
      "profile_name": "infra_incidents",
      "description": "Docker Compose smoke-test binding",
      "index_name": "kb",
      "text_fields": ["title", "text"],
      "target_field": "skeinrank",
      "mode": "write",
      "write_strategy": "in_place",
      "is_enabled": true
    }' \
  | python -c 'import json,sys; print(json.load(sys.stdin)["id"])'
)

echo "$BINDING_ID"
```

### 4. Run enrichment

```bash
export JOB_ID=$(
  curl -s -X POST "http://127.0.0.1:8010/v1/governance/elasticsearch/bindings/$BINDING_ID/jobs" \
    -H "Authorization: Bearer $ADMIN_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"max_documents": 10, "chunk_size": 1}' \
  | python -c 'import json,sys; print(json.load(sys.stdin)["id"])'
)

echo "$JOB_ID"
```

Poll job status until it is `succeeded`:

```bash
curl -s "http://127.0.0.1:8010/v1/governance/elasticsearch/jobs/$JOB_ID" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  | python -m json.tool
```

Expected counters:

```text
documents_seen: 3
documents_enriched: 2
documents_failed: 0
```

### 5. Run runtime search

```bash
curl -s -X POST http://127.0.0.1:8010/v1/search \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"binding_id\": $BINDING_ID,
    \"query\": \"k8s pg timeout\",
    \"size\": 10
  }" | python -m json.tool
```

Expected high-level result:

```text
canonical_values: ["kubernetes", "postgresql"]
hits include doc_001 and doc_002
hits contain skeinrank.snapshot_version
```

### 6. Try multi-binding search

```bash
curl -s -X POST http://127.0.0.1:8010/v1/search/multi \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"binding_ids\": [$BINDING_ID],
    \"query\": \"k8s pg timeout\",
    \"size\": 10
  }" | python -m json.tool
```

Expected high-level result:

```text
succeeded_bindings: 1
failed_bindings: 0
hits_count: 2
```

## UI flow

After the backend smoke test, open:

```text
http://127.0.0.1:5173
```

Use:

```text
admin / change-me
```

Recommended UI checks:

1. `Terms` shows the imported `infra_incidents` profile.
2. `Integrations` shows the Elasticsearch connection as healthy.
3. The `kb dev smoke` binding is visible.
4. The enrichment job appears in job history.
5. The binding shows runtime snapshot status.

## Stop or reset the stack

Stop containers but keep volumes:

```bash
docker compose -f docker-compose.dev.yml down
```

Stop containers and remove all dev data:

```bash
docker compose -f docker-compose.dev.yml down -v
```

## Production warning

This guide uses the development stack. It intentionally keeps local setup simple:

- Elasticsearch security is disabled.
- Default development credentials are used.
- Ports are bound to `127.0.0.1` for local testing.
- Secrets are stored in `.env`.

Do not use this file as a production security profile. Production deployment should use non-default secrets, restricted network exposure, Elasticsearch security/TLS, backups, and external secret management.

## Observability

The Compose stack enables the Governance API observability foundation by default. API responses include `X-Request-ID`, and API/worker containers emit structured logs when `SKEINRANK_GOVERNANCE_API_LOG_FORMAT=json`. See `docs/deployment/observability.md`.

## Optional Prometheus and Grafana

For local observability testing, start the dev stack with the `observability` profile:

```bash
docker compose -f docker-compose.dev.yml --profile observability up --build
```

This starts:

- Prometheus on `http://127.0.0.1:9090`
- Grafana on `http://127.0.0.1:3000`
- Governance API metrics on `http://127.0.0.1:8010/metrics`

Grafana is provisioned with a `SkeinRank Overview` dashboard. The dashboard JSON lives at:

```text
deploy/grafana/dashboards/skeinrank-overview.json
```

Prometheus scrape config lives at:

```text
deploy/prometheus/prometheus.yml
```

More details: `docs/deployment/observability.md`.


## OpenTelemetry tracing

SkeinRank supports optional OpenTelemetry tracing hooks for the Governance API and worker. See `docs/deployment/observability.md` for `SKEINRANK_GOVERNANCE_API_TRACING_ENABLED`, OTLP exporter settings, and privacy defaults.
