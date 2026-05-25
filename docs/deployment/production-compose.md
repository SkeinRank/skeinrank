# Production-oriented Docker Compose profile

`docker-compose.prod.yml` is the production-ish Compose profile for the Enterprise MVP track. It is still a Compose-based deployment, not a replacement for Kubernetes, managed PostgreSQL backups, or an organization-specific ingress/secrets system.

Use it when you want a reproducible pilot stack with:

```text
PostgreSQL + RabbitMQ + Governance API + Celery worker + UI
+ optional ops one-shot services
+ optional Prometheus/Grafana profile
```

## Start from the example environment

From the repository root:

```bash
cp .env.production.example .env
```

Edit `.env` and replace every `CHANGE_ME` value before starting the stack. Elasticsearch is optional for the first smoke test: leave `SKEINRANK_GOVERNANCE_API_ELASTICSEARCH_URL=` empty until you have a reachable Elasticsearch/OpenSearch endpoint.

The production profile intentionally enables fail-fast guardrails:

```text
SKEINRANK_ENV=production
SKEINRANK_GOVERNANCE_API_ENV=production
SKEINRANK_GOVERNANCE_API_AUTH_ENABLED=true
SKEINRANK_GOVERNANCE_API_PRODUCTION_SECURITY_ENABLED=true
```

## Makefile helpers

The direct `docker compose` commands are still documented below, but the root `Makefile` also provides wrappers:

```bash
make prod-config
make prod-up
make prod-smoke
make prod-smoke-strict
make prod-down
make prod-schema-check
make prod-backup-export
```

Set `PROD_ENV=path/to/.env` if you do not keep the production environment file in the repository root.

## Render and validate Compose config

Render the final config before starting containers:

```bash
docker compose --env-file .env -f docker-compose.prod.yml config
```

This catches missing required values such as `POSTGRES_PASSWORD`, `RABBITMQ_DEFAULT_PASS`, `SKEINRANK_GOVERNANCE_API_ADMIN_PASSWORD`, `SKEINRANK_GOVERNANCE_API_CORS_ORIGINS`, `VITE_SKEINRANK_GOVERNANCE_API_URL`, and secret values before Docker starts anything.

## Start the stack

```bash
docker compose --env-file .env -f docker-compose.prod.yml up --build -d
```

The profile runs a one-shot `governance-migrate` service before the API and worker become healthy.

Published ports are bound to localhost by default:

```text
API: 127.0.0.1:${GOVERNANCE_API_PORT:-8010}
UI:  127.0.0.1:${UI_PORT:-5173}
```

Expose those through a reverse proxy, VPN, or private ingress rather than binding PostgreSQL/RabbitMQ directly to the public network.

## Smoke test

After startup:

```bash
deploy/docker/scripts/prod-smoke-test.sh
# or fail if /readyz is degraded because an external dependency is unavailable
deploy/docker/scripts/prod-smoke-test.sh --strict
```

The script checks:

```text
/livez
/healthz
/readyz  # warning by default; strict with --strict
/schema/health
/metrics
```

If `SKEINRANK_PROD_SMOKE_ADMIN_PASSWORD` or `SKEINRANK_GOVERNANCE_API_ADMIN_PASSWORD` is present, it also logs in and checks `GET /v1/ops/troubleshooting/report`.

## Optional ops one-shot services

Run schema validation through Compose:

```bash
docker compose --env-file .env -f docker-compose.prod.yml --profile ops run --rm governance-schema-check
```

Export a timestamped portable JSON governance backup into the `skeinrank_postgres_backups` volume:

```bash
docker compose --env-file .env -f docker-compose.prod.yml --profile ops run --rm governance-backup-export
```

For large production PostgreSQL deployments, keep native backups as the primary disaster-recovery mechanism. See `docs/deployment/backup-restore.md`.

## Optional observability profile

Start Prometheus and Grafana alongside the production-oriented stack:

```bash
docker compose --env-file .env -f docker-compose.prod.yml --profile observability up -d prometheus grafana
```

Open:

```text
Prometheus: http://127.0.0.1:${PROMETHEUS_PORT:-9090}
Grafana:    http://127.0.0.1:${GRAFANA_PORT:-3000}
```

The profile reuses:

```text
deploy/prometheus/prometheus.yml
deploy/grafana/provisioning/
deploy/grafana/dashboards/skeinrank-overview.json
```

## Operational notes

- `governance-api` container health checks use `GET /healthz` so optional external services do not block the first local production-ish bootstrap. Use `deploy/docker/scripts/prod-smoke-test.sh --strict` when `/readyz` must be fully `ok`.
- PostgreSQL and RabbitMQ are not published to host ports in the production profile.
- Docker json-file log rotation is configured through `DOCKER_LOG_MAX_SIZE` and `DOCKER_LOG_MAX_FILE`.
- `governance-backup-export` is CLI-only by design; no HTTP restore endpoint is exposed.
- Compose is suitable for pilots and controlled deployments; larger company deployments should move secrets, backups, ingress, and service supervision into the target platform.
