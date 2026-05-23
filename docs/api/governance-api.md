# Governance API reference

This page lists the main API surfaces used by the governance console, migration tooling, runtime search path, and Elasticsearch workflows.

The governance API lives in:

```text
packages/skeinrank-governance-api
```

Start locally:

```bash
cd packages/skeinrank-governance-api
poetry install
poetry run python -m skeinrank_governance_api.migrations upgrade head
poetry run skeinrank-governance-api --reload
```

Default local URL:

```text
http://127.0.0.1:8010
```

## Health and readiness

```text
GET /livez
GET /healthz
GET /readyz
GET /metrics
```

`/readyz` reports database and configured Elasticsearch readiness. `/metrics` exposes Prometheus-compatible metrics when enabled by configuration.

## Console dictionary workflows

These endpoints support migration-friendly dictionary workflows for users, notebooks, scripts, CI jobs, and bot integrations.

```text
POST /v1/console/dictionary/validate
POST /v1/console/dictionary/import
GET  /v1/console/dictionary/export?profile_name=...
```

The expected dictionary shape is `skeinrank.dictionary.v1` and is compatible with the lightweight SDK/CLI examples in `examples/migration/console_dictionary.example.json`. New payloads should include `schema_version`; legacy payloads without it are accepted as v1 for backward compatibility. HTTP requests and responses remain JSON; CLI validate/apply accepts YAML files as a human-editable convenience when PyYAML is available.

## Profiles, terms, aliases, and guardrails

The governance API exposes CRUD-style endpoints for:

- profiles;
- canonical terms;
- aliases;
- global stop-list entries;
- profile stop-list entries;
- suggestions and approval/rejection workflows;
- runtime-compatible snapshot export.

Snapshots are exported from governed terminology and served to runtime paths as immutable dictionary versions.

## Suggestions and evidence

Reviewer workflows can refresh evidence for pending suggestions:

```text
POST /v1/governance/profiles/{profile_name}/suggestions/{suggestion_id}/evidence/refresh
```

The request references an Elasticsearch binding for the same profile. If `query` is omitted, alias suggestions use their alias value and canonical-term suggestions use their canonical value.

Saved evidence includes binding metadata, query metadata, warnings, and highlighted snippets.

## Elasticsearch discovery and bindings

Connection and mapping discovery:

```text
GET /v1/governance/elasticsearch/connection/status
GET /v1/governance/elasticsearch/indices
GET /v1/governance/elasticsearch/indices/{index_name}/mapping
```

Binding dry-run:

```text
POST /v1/governance/elasticsearch/bindings/{binding_id}/dry-run
```

Evidence lookup:

```text
POST /v1/governance/elasticsearch/bindings/{binding_id}/evidence
```

Enrichment jobs:

```text
POST /v1/governance/elasticsearch/bindings/{binding_id}/jobs
GET  /v1/governance/elasticsearch/jobs?binding_id=...
GET  /v1/governance/elasticsearch/jobs/{job_id}
POST /v1/governance/elasticsearch/jobs/{job_id}/cancel
```

## Runtime search and canonicalization

Production runtime should prefer binding-aware requests because a binding knows the index, fields, filters, and pinned snapshot.

Recommended production shape:

```json
{
  "binding_id": 7,
  "query": "k8s pg timeout",
  "size": 10
}
```

Useful runtime design rule:

```text
profile_name mode = preview/dev dictionary mode
binding_id mode   = pinned production runtime mode
```

## Auth and API access

The governance API supports local auth, users, roles, personal API tokens, service accounts, and token revocation.

Important environment variables include:

```text
SKEINRANK_GOVERNANCE_API_AUTH_ENABLED
SKEINRANK_GOVERNANCE_API_BOOTSTRAP_ADMIN
SKEINRANK_GOVERNANCE_API_ADMIN_USERNAME
SKEINRANK_GOVERNANCE_API_ADMIN_PASSWORD
SKEINRANK_GOVERNANCE_API_DATABASE_URL
SKEINRANK_GOVERNANCE_API_ELASTICSEARCH_URL
SKEINRANK_GOVERNANCE_API_ENRICHMENT_JOBS_BACKEND
```

Do not use default credentials or permissive CORS settings in production. See `docs/deployment/security.md`.
