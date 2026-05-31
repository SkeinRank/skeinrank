# Release Compose with GHCR images

This guide is the fastest way to run the SkeinRank public beta without building Python or Node packages locally.

Use this path when you want to try the product from published GHCR images:

```text
GHCR images
-> docker-compose.yml
-> local PostgreSQL / Elasticsearch / RabbitMQ
-> Governance API / worker / UI
```

For source development, use `docker-compose.dev.yml`. For production hardening, start from `docker-compose.prod.yml` and `docs/deployment/production-compose.md`.

## Images

`docker-compose.yml` pulls these release images:

```text
ghcr.io/skeinrank/skeinrank-governance-api:${SKEINRANK_IMAGE_TAG:-v0.10.0-beta.1}
ghcr.io/skeinrank/skeinrank-governance-worker:${SKEINRANK_IMAGE_TAG:-v0.10.0-beta.1}
ghcr.io/skeinrank/skeinrank-ui:${SKEINRANK_IMAGE_TAG:-v0.10.0-beta.1}
```

The stack also uses pinned datastore images:

```text
postgres:16.4-alpine
rabbitmq:3.13.7-management
docker.elastic.co/elasticsearch/elasticsearch:8.12.2
```

## Quick start

From the repository root:

```bash
cp .env.example .env
docker compose up -d
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

Default local login from `.env.example`:

```text
username: admin
password: change-me
```

These defaults are for local public-beta evaluation only. Do not expose this stack directly to the internet.

## Select another image tag

The release Compose stack reads one version variable for all SkeinRank service images:

```env
SKEINRANK_IMAGE_TAG=v0.10.0-beta.1
```

To try another published release:

```bash
SKEINRANK_IMAGE_TAG=v0.10.0 docker compose pull
SKEINRANK_IMAGE_TAG=v0.10.0 docker compose up -d
```

Or edit `.env`.

## Update images

```bash
docker compose pull
docker compose up -d
```

The migration service runs `python -m skeinrank_governance_api.migrations upgrade head` before the API and worker start.

## Seed the product demo

After the stack is healthy, load the guided platform demo:

```bash
make demo-reset
```

Open the UI and try the Search Playground with:

```text
k8s pg timeout during phoenix rollout
```

## Health checks

```bash
curl http://127.0.0.1:8010/livez | python -m json.tool
curl http://127.0.0.1:8010/readyz | python -m json.tool
```

Expected high-level result:

```json
{
  "status": "ok",
  "database": {"ok": true},
  "elasticsearch": {"configured": true, "ok": true}
}
```

## Stop and reset

Stop containers while keeping local data:

```bash
docker compose down
```

Remove containers and volumes:

```bash
docker compose down -v
```

## What this is not

This is not the production hardening profile. It is intentionally optimized for a low-friction local evaluation path:

```text
clone repo
-> cp .env.example .env
-> docker compose up -d
-> make demo-reset
```

For a hardened deployment, use:

```text
docker-compose.prod.yml
docs/deployment/security.md
docs/deployment/production-compose.md
```
