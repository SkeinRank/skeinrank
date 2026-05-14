# Production security profile

This page documents the production security baseline for running SkeinRank with Docker Compose.

The development stack in `docker-compose.dev.yml` is intentionally permissive. It disables Elasticsearch security, uses simple local credentials, and binds services to `127.0.0.1` for smoke testing. Do not expose the development stack directly to the internet.

Use `docker-compose.prod.yml` as the production-oriented starting point.

## Security model

A production deployment should treat the Governance API and UI as the only user-facing surfaces.

PostgreSQL, RabbitMQ, and Elasticsearch should not be exposed directly to end users.

```text
User / browser / integration
  -> UI or Governance API
  -> internal PostgreSQL / RabbitMQ / Elasticsearch
```

## Quick start

Create a production environment file:

```bash
cp .env.production.example .env
```

Edit `.env` and replace every `CHANGE_ME` value with a real secret.

Start the production-oriented stack:

```bash
docker compose -f docker-compose.prod.yml up --build -d
```

Check API health:

```bash
curl http://127.0.0.1:8010/readyz | python -m json.tool
```

The production compose file binds the UI and API to `127.0.0.1` by default. Put a reverse proxy, VPN, or private ingress in front of the API/UI if users need remote access.

## Required production settings

Set these values in `.env`:

```text
SKEINRANK_ENV=production
SKEINRANK_GOVERNANCE_API_ENV=production
SKEINRANK_GOVERNANCE_API_AUTH_ENABLED=true
SKEINRANK_GOVERNANCE_API_PRODUCTION_SECURITY_ENABLED=true
SKEINRANK_GOVERNANCE_API_CORS_ORIGINS=https://your-ui.example.com
SKEINRANK_GOVERNANCE_API_ELASTICSEARCH_URL=https://your-es.example.com:9200
```

Use strong secrets for:

```text
POSTGRES_PASSWORD
RABBITMQ_DEFAULT_PASS
SKEINRANK_GOVERNANCE_API_ADMIN_PASSWORD
SKEINRANK_GOVERNANCE_API_ELASTICSEARCH_PASSWORD or SKEINRANK_GOVERNANCE_API_ELASTICSEARCH_API_KEY
```

## Fail-fast guardrails

When `SKEINRANK_ENV=production` or `SKEINRANK_GOVERNANCE_API_ENV=production`, the Governance API validates production guardrails at startup.

It refuses to start if:

```text
- auth is disabled
- SQLite is used as the database
- automatic table creation is enabled
- wildcard CORS is configured
- bootstrap admin uses an unsafe default password
- Celery uses default broker credentials
- Elasticsearch URL is missing
```

This is intentional. A production deployment should fail loudly instead of starting with development defaults.

If you need to inspect a failed production config during local testing, you can temporarily set:

```text
SKEINRANK_GOVERNANCE_API_PRODUCTION_SECURITY_ENABLED=false
```

Do not use that override in a real production deployment.

## Bootstrap admin lifecycle

`SKEINRANK_GOVERNANCE_API_BOOTSTRAP_ADMIN=true` is useful for the first startup only.

Recommended flow:

```text
1. Start with BOOTSTRAP_ADMIN=true and a strong admin password.
2. Log in and create real admin/operator accounts.
3. Rotate or store the bootstrap credentials securely.
4. Set BOOTSTRAP_ADMIN=false for normal operation.
```

Bootstrap does not overwrite an existing admin user. Changing `SKEINRANK_GOVERNANCE_API_ADMIN_PASSWORD` after the user exists does not reset that user's password.

## Network exposure

`docker-compose.prod.yml` intentionally does not publish PostgreSQL or RabbitMQ ports.

The API/UI are bound to localhost by default:

```yaml
127.0.0.1:${GOVERNANCE_API_PORT:-8010}:8010
127.0.0.1:${UI_PORT:-5173}:5173
```

Expose them through a reverse proxy or private network boundary rather than binding them directly to `0.0.0.0`.

## Elasticsearch security

For production, use an Elasticsearch or OpenSearch endpoint with TLS and credentials.

Supported environment variables:

```text
SKEINRANK_GOVERNANCE_API_ELASTICSEARCH_URL
SKEINRANK_GOVERNANCE_API_ELASTICSEARCH_USERNAME
SKEINRANK_GOVERNANCE_API_ELASTICSEARCH_PASSWORD
SKEINRANK_GOVERNANCE_API_ELASTICSEARCH_API_KEY
```

Prefer a dedicated service account or API key with least-privilege access to the indices SkeinRank should enrich/search.

## Secrets

Do not commit `.env`.

For production, prefer a secrets manager or orchestrator-specific secret injection. If you use `.env`, keep it outside version control and restrict file permissions.

## Backups

Back up PostgreSQL regularly. It is the source of truth for governance state:

```text
profiles
terms
aliases
stop lists
bindings
users/tokens
jobs
snapshot metadata
```

Back up Elasticsearch indices according to your organization's search/data retention policy.

## Related docs

- `docs/deployment/docker-compose.md`
- `docs/deployment/dev-stack-troubleshooting.md`
- `deploy/docker/README.md`

## Observability privacy baseline

Production logging should avoid request bodies, document snippets, and sensitive query payloads by default. The built-in observability foundation logs request metadata, request ids, status codes, durations, and job lifecycle metadata only. See `docs/deployment/observability.md`.
