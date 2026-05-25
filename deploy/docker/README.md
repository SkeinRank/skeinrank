# SkeinRank Docker Compose dev stack

This directory contains Docker assets for running the SkeinRank governance platform locally.

The development stack starts:

- PostgreSQL 16 for governance state;
- Elasticsearch 8.12.2 for searchable documents and enrichment fields;
- RabbitMQ with the management UI for Celery enrichment jobs;
- SkeinRank Governance API;
- SkeinRank Governance Celery worker;
- SkeinRank UI through Vite;
- a one-shot migration service.

The dev stack is intended for local development and smoke testing. It is not a production security profile. Use `docker-compose.prod.yml` together with `docs/deployment/security.md` for the production-oriented profile.

## Quick start

From the repository root:

```bash
cp .env.example .env
docker compose -f docker-compose.dev.yml up --build
```

Open:

```text
UI:        http://127.0.0.1:5173
API:       http://127.0.0.1:8010
API docs:  http://127.0.0.1:8010/docs
RabbitMQ:  http://127.0.0.1:15672
ES:        http://127.0.0.1:19200
Postgres: 127.0.0.1:15432
```

Default dev credentials from `.env.example`:

```text
SkeinRank UI/API:
  username: admin
  password: change-me

RabbitMQ:
  username: skeinrank
  password: skeinrank_dev_password
```

The `governance-migrate` service runs Alembic migrations before the API and worker start.


## Headless-only profile

Use the API/PostgreSQL-only profile when you want to test headless dictionary and snapshot artifact contracts without UI, Elasticsearch, RabbitMQ, or Celery workers:

```bash
docker compose \
  --env-file deploy/docker/headless.env.example \
  -f docker-compose.headless.yml \
  up --build -d

deploy/docker/scripts/headless-golden-path.sh
```

Full walkthrough:

```text
docs/deployment/headless-quickstart.md
```

## Production-oriented profile

Start from:

```bash
cp .env.production.example .env
docker compose --env-file .env -f docker-compose.prod.yml config
docker compose --env-file .env -f docker-compose.prod.yml up --build -d
```

Before running it, replace every `CHANGE_ME` value and review:

```text
docs/deployment/security.md
docs/deployment/production-compose.md
```

The production profile keeps PostgreSQL and RabbitMQ internal to the Compose network, requires auth, allows Elasticsearch to be configured when needed, and enables fail-fast security guardrails. Patch 46A also adds optional `ops` and `observability` profiles plus `deploy/docker/scripts/prod-smoke-test.sh`.

Operational helpers can be run directly or through the root Makefile:

```bash
make prod-config
make prod-up
make prod-smoke
make prod-smoke-strict
make prod-down
make prod-schema-check
make prod-backup-export
```

Direct commands:

```bash
deploy/docker/scripts/prod-smoke-test.sh
docker compose --env-file .env -f docker-compose.prod.yml --profile ops run --rm governance-schema-check
docker compose --env-file .env -f docker-compose.prod.yml --profile ops run --rm governance-backup-export
docker compose --env-file .env -f docker-compose.prod.yml --profile observability up -d prometheus grafana
```

## Full install guide

Use the full install guide for the complete first-search workflow:

```text
docs/deployment/docker-compose.md
```

It covers:

```text
start stack
-> health check
-> login
-> create demo Elasticsearch index
-> import dictionary
-> create binding
-> run enrichment job
-> runtime search
-> UI validation
```

Troubleshooting notes are in:

```text
docs/deployment/dev-stack-troubleshooting.md
```

## Smoke checks

Health:

```bash
curl http://127.0.0.1:8010/livez | python -m json.tool
curl http://127.0.0.1:8010/readyz | python -m json.tool
```

Login:

```bash
export ADMIN_TOKEN=$(
  curl -s -X POST http://127.0.0.1:8010/v1/auth/login \
    -H "Content-Type: application/json" \
    -d '{"username":"admin","password":"change-me"}' \
  | python -c 'import json,sys; print(json.load(sys.stdin)["access_token"])'
)

echo "$ADMIN_TOKEN"
```


Run the bundled smoke helper after the stack is up:

```bash
deploy/docker/scripts/dev-smoke-test.sh
```

Elasticsearch connection:

```bash
curl -s http://127.0.0.1:8010/v1/governance/elasticsearch/connection/status \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  | python -m json.tool
```

Import the example dictionary:

```bash
curl -s -X POST http://127.0.0.1:8010/v1/console/dictionary/import \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d @examples/migration/console_dictionary.example.json \
  | python -m json.tool
```

## Reset the dev stack

Stop containers and remove dev volumes:

```bash
docker compose -f docker-compose.dev.yml down -v
```

## Notes

- Elasticsearch security is disabled in this dev stack.
- PostgreSQL, Elasticsearch, RabbitMQ, API, and UI ports are bound to `127.0.0.1`.
- For production, use `docker-compose.prod.yml`, `.env.production.example`, and `docs/deployment/security.md`.

## Observability

The dev and production Compose profiles include the Governance API observability foundation. JSON logs are enabled by default in Compose. See `docs/deployment/observability.md` for request IDs, access logs, job lifecycle logs, and future OpenTelemetry/Sentry integration notes.

## Optional observability profile

The development stack can also start Prometheus and Grafana:

```bash
docker compose -f docker-compose.dev.yml --profile observability up --build
```

Services:

- Prometheus: `http://127.0.0.1:9090`
- Grafana: `http://127.0.0.1:3000`
- Governance API metrics: `http://127.0.0.1:8010/metrics`

Prometheus scrapes the Governance API `/metrics` endpoint. Grafana is provisioned with the `SkeinRank Overview` dashboard from `deploy/grafana/dashboards/skeinrank-overview.json`.

See `docs/deployment/observability.md` for metric names and dashboard details.

### Patch 42D — Docker Compose full demo scenario

The `openrouter-agent-full-demo` Compose overlay provides a report-only full demo path for the OpenRouter alias scout. Use `--print-docker-demo-plan` to inspect the plan before running Docker Compose.

