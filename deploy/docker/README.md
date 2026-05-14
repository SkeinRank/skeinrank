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

## Production-oriented profile

Start from:

```bash
cp .env.production.example .env
docker compose -f docker-compose.prod.yml up --build -d
```

Before running it, replace every `CHANGE_ME` value and review:

```text
docs/deployment/security.md
```

The production profile keeps PostgreSQL and RabbitMQ internal to the Compose network, requires auth, requires a configured Elasticsearch endpoint, and enables fail-fast security guardrails.

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
curl http://127.0.0.1:8010/healthz | python -m json.tool
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
