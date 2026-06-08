# SkeinRank Docker deployment assets

This directory contains Dockerfiles, Compose overlays, environment examples, and smoke-test helpers for running SkeinRank locally or in controlled rollout environments.

The default development stack starts:

- PostgreSQL 16 for governance state;
- Elasticsearch 8.12.2 for searchable documents and enrichment fields;
- RabbitMQ with the management UI for Celery enrichment jobs;
- SkeinRank Governance API;
- SkeinRank Governance Celery worker;
- SkeinRank UI through Vite;
- a one-shot `governance-migrate` service for Alembic migrations.

The development stack is intended for local evaluation, integration work, and smoke testing. It is not a production security profile. For production-oriented Compose, start with `docker-compose.prod.yml`, `.env.production.example`, and `docs/deployment/security.md`.

## Deployment paths

| Path | Use when | Entry point |
| --- | --- | --- |
| Release Compose | You want the fastest local run with prebuilt GHCR images | `docker-compose.yml` |
| Development Compose | You are changing source code and need local builds | `docker-compose.dev.yml` |
| Headless Compose | You only need API/PostgreSQL dictionary and snapshot contracts | `docker-compose.headless.yml` |
| Production-oriented Compose | You need a hardened Compose baseline for a pilot or controlled rollout | `docker-compose.prod.yml` |
| OpenRouter agent demo | You want a safe, report-only alias-scout walkthrough on top of the dev stack | `deploy/docker/openrouter-agent-full-demo.compose.yml` |

## Release Compose with GHCR images

From the repository root:

```bash
cp .env.example .env
docker compose up -d
```

This pulls:

```text
ghcr.io/skeinrank/skeinrank-governance-api:${SKEINRANK_IMAGE_TAG:-v0.10.0-beta.1}
ghcr.io/skeinrank/skeinrank-governance-worker:${SKEINRANK_IMAGE_TAG:-v0.10.0-beta.1}
ghcr.io/skeinrank/skeinrank-ui:${SKEINRANK_IMAGE_TAG:-v0.10.0-beta.1}
```

Use `docs/deployment/release-compose.md` for the complete release-image walkthrough.

## Development quick start

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

Default development credentials from `.env.example`:

```text
SkeinRank UI/API:
  username: admin
  password: change-me

RabbitMQ:
  username: skeinrank
  password: skeinrank_dev_password
```

The `governance-migrate` service runs migrations before the API and worker start.

## First-search walkthrough

Use the full install guide when you want to validate the complete local workflow:

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

Run the bundled development smoke helper after the stack is up:

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

## Headless-only profile

Use the API/PostgreSQL-only profile when you want to test dictionary import and snapshot artifact contracts without UI, Elasticsearch, RabbitMQ, or Celery workers:

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
make prod-env-check
docker compose --env-file .env -f docker-compose.prod.yml config
docker compose --env-file .env -f docker-compose.prod.yml up --build -d
```

Before running it, replace every `CHANGE_ME` value and review:

```text
docs/deployment/security.md
docs/deployment/production-compose.md
docs/deployment/env-and-secrets.md
```

The production-oriented profile keeps PostgreSQL and RabbitMQ internal to the Compose network, requires authentication, allows Elasticsearch to be configured when needed, and enables fail-fast security guardrails. It also includes optional `ops` and `observability` profiles plus `deploy/docker/scripts/prod-smoke-test.sh`.

Production datastore image tags are pinned explicitly: `postgres:16.4-alpine` and `rabbitmq:3.13.7-management`. Avoid broad production tags such as `rabbitmq:3-management`; bump image versions through a deliberate dependency update.

Operational helpers can be run directly or through the root Makefile:

```bash
make prod-env-check
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

## OpenRouter alias scout Compose demo

The `openrouter-agent-full-demo` Compose overlay provides a safe, report-only walkthrough for the OpenRouter alias scout. It runs on top of the development stack, indexes validation documents into an isolated Elasticsearch index, and writes standard reports under `examples/agents/openrouter_alias_scout/reports/docker-demo/`.

Inspect the plan without running the stack:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --config examples/agents/openrouter_alias_scout/agent_config.example.json \
  --print-docker-demo-plan
```

Run the one-shot demo:

```bash
deploy/docker/scripts/openrouter-agent-full-demo.sh run
```

The default scenario does not call OpenRouter, does not submit proposals, does not publish snapshots, and limits Elasticsearch writes to the configured validation index.

Detailed guide:

```text
docs/deployment/openrouter-agent-full-demo.md
```

## Observability

The development and production-oriented Compose profiles include the Governance API observability foundation. JSON logs are enabled by default in Compose.

Optional development observability profile:

```bash
docker compose -f docker-compose.dev.yml --profile observability up --build
```

Services:

- Prometheus: `http://127.0.0.1:9090`
- Grafana: `http://127.0.0.1:3000`
- Governance API metrics: `http://127.0.0.1:8010/metrics`

Prometheus scrapes the Governance API `/metrics` endpoint. Grafana is provisioned with the `SkeinRank Overview` dashboard from `deploy/grafana/dashboards/skeinrank-overview.json`.

See `docs/deployment/observability.md` for request IDs, access logs, job lifecycle logs, metrics, and dashboard details.

## Controlled upgrade flow

Use the upgrade preflight and smoke helpers before replacing a running pilot stack:

```bash
make prod-upgrade-check
make prod-preflight
make prod-upgrade
make prod-post-upgrade-smoke
```

Detailed runbooks live in:

```text
docs/deployment/upgrade-guide.md
docs/deployment/migration-safety.md
docs/deployment/release-checklist.md
```

## Reset the development stack

Stop containers and remove development volumes:

```bash
docker compose -f docker-compose.dev.yml down -v
```

## Security notes

- Elasticsearch security is disabled in the development stack.
- PostgreSQL, Elasticsearch, RabbitMQ, API, and UI ports are bound to `127.0.0.1` by default.
- Do not expose the development stack directly to the internet.
- For production-oriented Compose, use `docker-compose.prod.yml`, `.env.production.example`, and `docs/deployment/security.md`.
