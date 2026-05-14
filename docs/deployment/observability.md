# Observability

## Observability foundation

SkeinRank includes a vendor-neutral observability layer for the Governance API and Celery worker.

The current stack covers:

- request IDs and structured logs;
- Prometheus-compatible metrics at `GET /metrics`;
- optional Prometheus + Grafana services for the Docker Compose dev stack;
- a pre-provisioned Grafana dashboard for API, runtime search, and enrichment job signals.

OpenTelemetry tracing and optional Sentry reporting are intentionally left for later patches.

## Request IDs and logs

Patch 31A added:

- request IDs for API calls;
- `X-Request-ID` response header;
- structured JSON logs or plain text logs;
- HTTP access logs with method, path, status code, duration, client host, and request id;
- exception logs with request id and request metadata;
- job lifecycle logs for enrichment start, chunk queueing, preparation failures, and success;
- shared logging setup for the API process and Celery worker.

## Prometheus metrics

Patch 31B adds a dependency-free Prometheus text endpoint:

```http
GET /metrics
```

Example:

```bash
curl http://127.0.0.1:8010/metrics
```

The endpoint is enabled by default in the dev and production Compose templates.

### Metric groups

The built-in metrics include:

| Metric | Type | Description |
| --- | --- | --- |
| `skeinrank_build_info` | gauge | Service and version metadata. |
| `skeinrank_http_requests_total` | counter | HTTP requests by method, path, and status. |
| `skeinrank_http_request_duration_seconds` | histogram | HTTP request duration. |
| `skeinrank_http_exceptions_total` | counter | Unhandled HTTP exceptions. |
| `skeinrank_runtime_search_requests_total` | counter | Runtime query/search calls by endpoint and status. |
| `skeinrank_runtime_search_duration_seconds` | histogram | Runtime query/search latency. |
| `skeinrank_runtime_search_hits_total` | counter | Hits returned by runtime search endpoints. |
| `skeinrank_runtime_search_binding_requests_total` | counter | Per-binding multi-search success/failure counts. |
| `skeinrank_enrichment_jobs_total` | counter | Enrichment jobs by status and write strategy. |
| `skeinrank_enrichment_job_duration_seconds` | histogram | Enrichment job duration. |
| `skeinrank_enrichment_documents_seen_total` | counter | Documents seen by enrichment jobs. |
| `skeinrank_enrichment_documents_enriched_total` | counter | Documents enriched by enrichment jobs. |
| `skeinrank_enrichment_documents_failed_total` | counter | Documents failed during enrichment jobs. |

## Environment variables

| Variable | Default | Description |
| --- | --- | --- |
| `SKEINRANK_GOVERNANCE_API_OBSERVABILITY_ENABLED` | `true` | Enables request id middleware and logging setup. |
| `SKEINRANK_GOVERNANCE_API_LOG_FORMAT` | `plain` locally, `json` in Compose | `plain` or `json`. |
| `SKEINRANK_GOVERNANCE_API_LOG_LEVEL` | `info` | Python logging level. |
| `SKEINRANK_GOVERNANCE_API_ACCESS_LOG_ENABLED` | `true` | Emits one access log event per HTTP request. |
| `SKEINRANK_GOVERNANCE_API_REQUEST_ID_HEADER` | `X-Request-ID` | Header used to accept and return request ids. |
| `SKEINRANK_GOVERNANCE_API_METRICS_ENABLED` | `true` | Enables the Prometheus metrics endpoint. |
| `SKEINRANK_GOVERNANCE_API_METRICS_PATH` | `/metrics` | Metrics endpoint path. |

Global aliases are also supported:

```text
SKEINRANK_OBSERVABILITY_ENABLED
SKEINRANK_LOG_FORMAT
SKEINRANK_LOG_LEVEL
SKEINRANK_ACCESS_LOG_ENABLED
SKEINRANK_REQUEST_ID_HEADER
SKEINRANK_METRICS_ENABLED
SKEINRANK_METRICS_PATH
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

## Docker Compose observability profile

Start the normal dev stack:

```bash
docker compose -f docker-compose.dev.yml up --build
```

Start the dev stack with Prometheus and Grafana:

```bash
docker compose -f docker-compose.dev.yml --profile observability up --build
```

Available endpoints:

| Service | URL |
| --- | --- |
| Prometheus | `http://127.0.0.1:9090` |
| Grafana | `http://127.0.0.1:3000` |
| Governance API metrics | `http://127.0.0.1:8010/metrics` |

Default dev Grafana login:

```text
admin / admin
```

Prometheus config:

```text
deploy/prometheus/prometheus.yml
```

Grafana provisioning:

```text
deploy/grafana/provisioning/
deploy/grafana/dashboards/skeinrank-overview.json
```

## Privacy baseline

The foundation does not log request bodies or document snippets. Runtime query text and document contents should remain out of logs by default. Later OpenTelemetry/Sentry integrations should preserve this baseline unless a deployment explicitly opts in to capturing additional payload fields.

## Future integrations

The next observability patches can build on this foundation:

- OpenTelemetry tracing with OTLP exporters;
- optional Sentry error reporting;
- deployment dashboards for enrichment jobs and runtime search.
