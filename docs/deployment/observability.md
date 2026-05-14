# Observability foundation

SkeinRank includes a lightweight observability foundation for the Governance API and Celery worker.

This layer is intentionally vendor-neutral. It does not require Prometheus, Grafana, OpenTelemetry, or Sentry yet. Those integrations can be added on top of the same configuration in later patches.

## What is included

Patch 31A provides:

- request IDs for API calls;
- `X-Request-ID` response header;
- structured JSON logs or plain text logs;
- HTTP access logs with method, path, status code, duration, client host, and request id;
- exception logs with request id and request metadata;
- job lifecycle logs for enrichment start, chunk queueing, preparation failures, and success;
- shared logging setup for the API process and Celery worker.

## Environment variables

| Variable | Default | Description |
| --- | --- | --- |
| `SKEINRANK_GOVERNANCE_API_OBSERVABILITY_ENABLED` | `true` | Enables request id middleware and logging setup. |
| `SKEINRANK_GOVERNANCE_API_LOG_FORMAT` | `plain` locally, `json` in Compose | `plain` or `json`. |
| `SKEINRANK_GOVERNANCE_API_LOG_LEVEL` | `info` | Python logging level. |
| `SKEINRANK_GOVERNANCE_API_ACCESS_LOG_ENABLED` | `true` | Emits one access log event per HTTP request. |
| `SKEINRANK_GOVERNANCE_API_REQUEST_ID_HEADER` | `X-Request-ID` | Header used to accept and return request ids. |

Global aliases are also supported:

```text
SKEINRANK_OBSERVABILITY_ENABLED
SKEINRANK_LOG_FORMAT
SKEINRANK_LOG_LEVEL
SKEINRANK_ACCESS_LOG_ENABLED
SKEINRANK_REQUEST_ID_HEADER
```

The `SKEINRANK_GOVERNANCE_API_*` variables take precedence.

## Request IDs

If the client sends a request id, SkeinRank preserves it:

```bash
curl -i http://127.0.0.1:8010/livez \
  -H "X-Request-ID: local-smoke-1"
```

Expected response header:

```text
X-Request-ID: local-smoke-1
```

If the client does not send a request id, SkeinRank generates one and returns it in the same header.

## JSON logs

Set:

```text
SKEINRANK_GOVERNANCE_API_LOG_FORMAT=json
```

Example event shape:

```json
{
  "level": "info",
  "logger": "skeinrank_governance_api.observability.http",
  "message": "HTTP request completed",
  "request_id": "local-smoke-1",
  "http_method": "GET",
  "http_path": "/readyz",
  "http_status_code": 200,
  "duration_ms": 12.3,
  "service": {
    "name": "skeinrank-governance-api",
    "version": "0.1.0"
  }
}
```

## Privacy baseline

The foundation does not log request bodies or document snippets. Runtime query text and document contents should remain out of logs by default. Later OpenTelemetry/Sentry integrations should preserve this baseline unless a deployment explicitly opts in to capturing additional payload fields.

## Docker Compose

The dev and production Compose files enable JSON logs by default:

```text
SKEINRANK_GOVERNANCE_API_LOG_FORMAT=json
SKEINRANK_GOVERNANCE_API_ACCESS_LOG_ENABLED=true
```

Use Docker logs during local debugging:

```bash
docker compose -f docker-compose.dev.yml logs -f governance-api
docker compose -f docker-compose.dev.yml logs -f governance-worker
```

## Future integrations

The next observability patches can build on this foundation:

- Prometheus metrics and Grafana dashboards;
- OpenTelemetry tracing with OTLP exporters;
- optional Sentry error reporting;
- deployment dashboards for enrichment jobs and runtime search.
