# Docker Compose dev stack troubleshooting

This page lists common issues when running the SkeinRank Docker Compose development stack.

## Port is already in use

Example error:

```text
failed to bind port 127.0.0.1:5672/tcp: address already in use
```

Check which process is listening:

```bash
lsof -nP -iTCP:5672 -sTCP:LISTEN
lsof -nP -iTCP:15672 -sTCP:LISTEN
lsof -nP -iTCP:8010 -sTCP:LISTEN
lsof -nP -iTCP:5173 -sTCP:LISTEN
lsof -nP -iTCP:15432 -sTCP:LISTEN
lsof -nP -iTCP:19200 -sTCP:LISTEN
```

Common causes:

- a previously started RabbitMQ container;
- an existing local PostgreSQL or Elasticsearch instance;
- an SSH tunnel that still binds `15432` or `19200`;
- a local Vite or Uvicorn dev server.

Stop old compose containers:

```bash
docker compose -f docker-compose.dev.yml down
```

List running containers:

```bash
docker ps
```

Override ports in `.env` when you want to keep another service running.

## Worker keeps restarting

Check worker logs:

```bash
docker compose -f docker-compose.dev.yml logs -f governance-worker
```

A healthy worker should connect to RabbitMQ and stay running. If it keeps restarting, check:

- RabbitMQ health;
- `SKEINRANK_GOVERNANCE_API_CELERY_BROKER_URL`;
- database connectivity;
- whether migrations completed successfully.

## Migrations failed

Check migration logs:

```bash
docker compose -f docker-compose.dev.yml logs governance-migrate
```

For a clean local reset:

```bash
docker compose -f docker-compose.dev.yml down -v
docker compose -f docker-compose.dev.yml up --build
```

`down -v` removes PostgreSQL, RabbitMQ, and Elasticsearch dev volumes.

## API is up but UI cannot log in

Check API health:

```bash
curl http://127.0.0.1:8010/readyz | python -m json.tool
```

Check the admin password in `.env`:

```text
SKEINRANK_GOVERNANCE_API_ADMIN_USERNAME=admin
SKEINRANK_GOVERNANCE_API_ADMIN_PASSWORD=change-me
```

Bootstrap admin credentials are applied when the initial admin user is created. Changing `.env` later does not reset an existing user password. For a clean dev reset:

```bash
docker compose -f docker-compose.dev.yml down -v
docker compose -f docker-compose.dev.yml up --build
```

## Elasticsearch is slow to become healthy

Elasticsearch can take longer to start on small machines. Watch logs:

```bash
docker compose -f docker-compose.dev.yml logs -f elasticsearch
```

You can reduce memory usage in `.env`:

```text
ES_JAVA_OPTS=-Xms512m -Xmx512m
```

## Rebuild after code changes

```bash
docker compose -f docker-compose.dev.yml up --build
```

Or rebuild one service:

```bash
docker compose -f docker-compose.dev.yml build governance-api
docker compose -f docker-compose.dev.yml up governance-api
```

## Inspect service status

```bash
docker compose -f docker-compose.dev.yml ps
```

## View logs

```bash
docker compose -f docker-compose.dev.yml logs -f governance-api
docker compose -f docker-compose.dev.yml logs -f governance-worker
docker compose -f docker-compose.dev.yml logs -f ui
```


## Run the smoke helper

After the stack is up, run the deployment smoke helper from the repository root:

```bash
deploy/docker/scripts/dev-smoke-test.sh
```

It checks liveness, readiness, admin login, authenticated `/v1/auth/me`, and Elasticsearch connection status.

## Prometheus or Grafana ports are busy

The observability profile publishes:

```text
127.0.0.1:9090 -> Prometheus
127.0.0.1:3000 -> Grafana
```

Check port usage:

```bash
lsof -nP -iTCP:9090 -sTCP:LISTEN
lsof -nP -iTCP:3000 -sTCP:LISTEN
```

Override ports in `.env`:

```text
PROMETHEUS_PORT=19090
GRAFANA_PORT=13000
```

Then start the observability profile again:

```bash
docker compose -f docker-compose.dev.yml --profile observability up --build
```

## Metrics endpoint is empty or unavailable

Check that metrics are enabled:

```text
SKEINRANK_GOVERNANCE_API_METRICS_ENABLED=true
SKEINRANK_GOVERNANCE_API_METRICS_PATH=/metrics
```

Then call:

```bash
curl http://127.0.0.1:8010/metrics
```
