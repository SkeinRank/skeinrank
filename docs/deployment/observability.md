# Observability

SkeinRank ships a vendor-neutral observability layer for the Governance API and workers. It is designed for local debugging, production smoke checks, and operator dashboards without forcing a specific monitoring vendor.

The stack covers:

- request IDs and structured logs;
- Prometheus-compatible metrics at `GET /metrics`;
- optional Prometheus, Grafana, and OpenTelemetry Collector services for Docker Compose;
- a provisioned Grafana dashboard for API, runtime search, enrichment jobs, health, and agent-run signals;
- optional OpenTelemetry tracing hooks for HTTP requests, runtime search, and Celery enrichment tasks;
- sanitized troubleshooting reports for support and restore drills.

Sentry or another hosted error-reporting backend is not bundled. Teams can add one outside the core runtime if their production environment requires it.

## Observability foundation

The API and worker use the same logging and request-context model:

- inbound API calls receive or generate a request id;
- the response includes the configured request-id header;
- logs can be emitted as plain text or JSON;
- HTTP access logs include method, path, status code, duration, client host, and request id;
- exception logs include request metadata without request bodies;
- enrichment jobs emit lifecycle logs for start, chunk queueing, preparation failures, and completion.

The default request id header is:

```text
X-Request-ID
```

If a client provides the header, SkeinRank preserves it. If not, SkeinRank generates a request id and returns it in the same header.

```bash
curl -i http://127.0.0.1:8010/livez \
  -H "X-Request-ID: local-smoke-1"
```

Expected response header:

```text
X-Request-ID: local-smoke-1
```

## Prometheus metrics

Metrics are exposed as Prometheus text:

```http
GET /metrics
```

Example:

```bash
curl http://127.0.0.1:8010/metrics
```

The endpoint is enabled by default in the development and production Compose templates. It can be disabled or moved with environment variables listed below.

### Metric groups

| Metric | Type | Description |
| --- | --- | --- |
| `skeinrank_build_info` | gauge | Service and version metadata. |
| `skeinrank_http_requests_total` | counter | HTTP requests by method, path, and status. |
| `skeinrank_http_request_duration_seconds` | histogram | HTTP request duration. |
| `skeinrank_http_exceptions_total` | counter | Unhandled HTTP exceptions. |
| `skeinrank_health_checks_total` | counter | Health endpoint responses by endpoint and status. |
| `skeinrank_health_check_duration_seconds` | histogram | Health endpoint execution duration. |
| `skeinrank_database_up` | gauge | Database connectivity status from operational health refresh. |
| `skeinrank_schema_ok` | gauge | Governance schema health status from operational health refresh. |
| `skeinrank_schema_current_matches_head` | gauge | Whether the DB revision matches the Alembic head. |
| `skeinrank_schema_missing_tables` | gauge | Number of expected metadata tables missing from the DB. |
| `skeinrank_alembic_multiple_heads` | gauge | Whether multiple Alembic heads are present. |
| `skeinrank_elasticsearch_up` | gauge | Elasticsearch health status, labelled by configured state. |
| `skeinrank_operational_metrics_refresh_total` | counter | `/metrics`-time operational refresh attempts by status. |
| `skeinrank_operational_metrics_refresh_duration_seconds` | histogram | Operational refresh duration. |
| `skeinrank_operational_metrics_last_refresh_success` | gauge | Whether the latest operational refresh succeeded. |
| `skeinrank_operational_metrics_last_refresh_timestamp_seconds` | gauge | Unix timestamp of the latest operational refresh. |
| `skeinrank_runtime_search_requests_total` | counter | Runtime query/search calls by endpoint and status. |
| `skeinrank_runtime_search_duration_seconds` | histogram | Runtime query/search latency. |
| `skeinrank_runtime_search_hits_total` | counter | Hits returned by runtime search endpoints. |
| `skeinrank_runtime_search_binding_requests_total` | counter | Per-binding multi-search success/failure counts. |
| `skeinrank_enrichment_jobs_total` | counter | Enrichment jobs by status and write strategy. |
| `skeinrank_enrichment_job_duration_seconds` | histogram | Enrichment job duration. |
| `skeinrank_enrichment_documents_seen_total` | counter | Documents seen by enrichment jobs. |
| `skeinrank_enrichment_documents_enriched_total` | counter | Documents enriched by enrichment jobs. |
| `skeinrank_enrichment_documents_failed_total` | counter | Documents failed during enrichment jobs. |
| `skeinrank_proposals_submitted_total` | counter | Proposal submissions by source type, suggestion type, validation status, and outcome. |
| `skeinrank_proposal_reviews_total` | counter | Proposal review decisions by source type and decision. |
| `skeinrank_proposal_batch_apply_total` | counter | Proposal batch apply operations by status and snapshot publish flag. |
| `skeinrank_proposal_batch_suggestions_total` | counter | Suggestions processed by proposal batch apply operations. |
| `skeinrank_agent_runs_current` | gauge | Current persisted agent runs by status. |
| `skeinrank_agent_document_visits_current` | gauge | Current persisted agent document visits by status. |
| `skeinrank_agent_candidate_observations_current` | gauge | Current persisted agent observations by status. |
| `skeinrank_agent_llm_reviews_current` | gauge | Current persisted agent LLM reviews by status. |
| `skeinrank_agent_proposal_attempts_current` | gauge | Current persisted agent proposal attempts by status. |
| `skeinrank_agent_evidence_windows_current` | gauge | Current persisted agent evidence windows. |

### Operational refresh behavior

Prometheus scrapes refresh deployment-health and agent-tracking gauges on a best-effort basis. `GET /metrics` still returns Prometheus text if the database, schema, or Elasticsearch dependency is degraded. Refresh failures are reflected through:

```text
skeinrank_operational_metrics_refresh_total{status="failed"}
skeinrank_operational_metrics_last_refresh_success
```

The health gauges intentionally mirror the operator-facing endpoints:

```text
GET /healthz
GET /readyz
GET /schema/health
GET /metrics
```

`GET /readyz` remains the deployment gate. Metrics make the same status visible to Prometheus and Grafana without requiring operators to parse JSON responses.

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
| `SKEINRANK_GOVERNANCE_API_TRACING_ENABLED` | `false` | Enables optional OpenTelemetry tracing hooks. |
| `SKEINRANK_GOVERNANCE_API_OTEL_SERVICE_NAME` | `skeinrank-governance-api` | Service name used in OTEL resources. |
| `SKEINRANK_GOVERNANCE_API_OTEL_TRACES_EXPORTER` | `none` | Trace exporter: `none`, `console`, or `otlp`. |
| `SKEINRANK_GOVERNANCE_API_OTEL_EXPORTER_OTLP_ENDPOINT` | `http://otel-collector:4317` | OTLP endpoint for trace export. |
| `SKEINRANK_GOVERNANCE_API_OTEL_SAMPLING_RATIO` | `1.0` | Trace sampling ratio from `0.0` to `1.0`. |
| `SKEINRANK_GOVERNANCE_API_OTEL_CAPTURE_QUERY_TEXT` | `false` | Captures raw query text in spans only when explicitly enabled. |

Global aliases are also supported:

```text
SKEINRANK_OBSERVABILITY_ENABLED
SKEINRANK_LOG_FORMAT
SKEINRANK_LOG_LEVEL
SKEINRANK_ACCESS_LOG_ENABLED
SKEINRANK_REQUEST_ID_HEADER
SKEINRANK_METRICS_ENABLED
SKEINRANK_METRICS_PATH
SKEINRANK_TRACING_ENABLED
SKEINRANK_OTEL_SERVICE_NAME
SKEINRANK_OTEL_TRACES_EXPORTER
SKEINRANK_OTEL_EXPORTER_OTLP_ENDPOINT
SKEINRANK_OTEL_SAMPLING_RATIO
SKEINRANK_OTEL_CAPTURE_QUERY_TEXT
```

The `SKEINRANK_GOVERNANCE_API_*` variables take precedence.

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
  "event": "http.request.completed",
  "outcome": "succeeded",
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

## Troubleshooting reports

The Governance API exposes a sanitized operator report for support/debug sessions:

```bash
curl http://127.0.0.1:8010/v1/ops/troubleshooting/report \
  -H "Authorization: Bearer $SKEINRANK_TOKEN" | python -m json.tool

poetry run python -m skeinrank_governance_api.troubleshooting report
```

The report includes service metadata, deployment environment, sanitized config, database/schema/Elasticsearch/observability checks, selected table counts, and recommendations. It does not include credentials, API tokens, request bodies, query text, or document snippets.

For backup/restore drills and incident runbooks, see [`backup-restore.md`](backup-restore.md) (`docs/deployment/backup-restore.md`).

For API tokens, use the `ops:reports:read` scope. Session login and local-dev mode remain role-based.

## Docker Compose observability profile

Start the normal development stack:

```bash
docker compose -f docker-compose.dev.yml up --build
```

Start the development stack with Prometheus and Grafana:

```bash
docker compose -f docker-compose.dev.yml --profile observability up --build
```

Start the production-style observability profile:

```bash
docker compose --env-file .env -f docker-compose.prod.yml --profile observability up -d prometheus grafana
```

Available endpoints:

| Service | URL |
| --- | --- |
| Prometheus | `http://127.0.0.1:9090` |
| Grafana | `http://127.0.0.1:3000` |
| Governance API metrics | `http://127.0.0.1:8010/metrics` |

Default local Grafana login:

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

The Compose profile reuses the same Prometheus config and Grafana dashboard for local and production-style deployments. Keep Prometheus and Grafana bound to `127.0.0.1` or expose them only through a protected operator network.

## OpenTelemetry tracing

Tracing hooks are optional. The core package does not require OpenTelemetry libraries at import time. If tracing is enabled but OpenTelemetry packages are not installed, the API logs a warning and continues with no-op spans.

To enable tracing in an environment that has OpenTelemetry SDK/exporter packages installed:

```text
SKEINRANK_GOVERNANCE_API_TRACING_ENABLED=true
SKEINRANK_GOVERNANCE_API_OTEL_TRACES_EXPORTER=otlp
SKEINRANK_GOVERNANCE_API_OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317
SKEINRANK_GOVERNANCE_API_OTEL_SAMPLING_RATIO=1.0
```

The Compose observability profile includes an OpenTelemetry Collector config at:

```text
deploy/otel/collector.yml
```

Tracing spans are emitted for:

- HTTP requests;
- `/v1/query/plan`;
- `/v1/search`;
- Celery enrichment coordinator tasks;
- Celery enrichment chunk tasks.

By default, raw query text is not added to spans. Enable query-text capture only in safe test environments:

```text
SKEINRANK_GOVERNANCE_API_OTEL_CAPTURE_QUERY_TEXT=true
```

## Privacy baseline

The observability layer does not log request bodies or document snippets. Runtime query text and document contents remain out of logs and spans by default. OpenTelemetry query text capture is opt-in through `SKEINRANK_GOVERNANCE_API_OTEL_CAPTURE_QUERY_TEXT=true` and should only be used in safe environments.

## Operational checklist

Before exposing observability endpoints outside a developer workstation:

- keep `/metrics`, Prometheus, Grafana, and OTLP endpoints on an internal operator network;
- set `SKEINRANK_GOVERNANCE_API_LOG_FORMAT=json` for machine-parsable logs;
- keep query-text tracing disabled unless the environment is explicitly safe;
- give troubleshooting report tokens the `ops:reports:read` scope only;
- run backup/restore drills with the troubleshooting report and schema checks documented in [`backup-restore.md`](backup-restore.md) (`docs/deployment/backup-restore.md`) and [`migration-safety.md`](migration-safety.md).
