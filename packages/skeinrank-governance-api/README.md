# skeinrank-governance-api

FastAPI control-plane API for SkeinRank terminology governance.

This package is the HTTP layer that powers the SkeinRank governance UI. It sits above `skeinrank-governance`, which owns SQLAlchemy models, Alembic migrations, and the admin CLI.

## Role in the architecture

```text
Postgres governance store
  -> skeinrank-governance SQLAlchemy models
  -> skeinrank-governance-api HTTP control plane
  -> skeinrank-ui
  -> published snapshot JSON
  -> fast runtime matcher
```

The runtime extraction path does not query this API on every request. Governance remains a control-plane layer for editing terminology and publishing snapshots.

## Local development

```bash
poetry install
poetry run pytest -q
```


## Pilot integration CLI

Patch 49E adds `skeinrank-governance-pilot`, a dependency-light HTTP CLI for
first-company Elasticsearch pilots. It reads a JSON config, validates the API and
Elasticsearch index mapping, imports a seed dictionary, creates or reuses a
dry-run Elasticsearch binding, and writes a read-only evidence/query-plan report.

```bash
poetry run skeinrank-governance-pilot plan \
  --config ../../examples/pilots/elasticsearch_pilot.example.json

poetry run skeinrank-governance-pilot run \
  --api-url http://127.0.0.1:8010 \
  --config ../../examples/pilots/elasticsearch_pilot.example.json \
  --out ../../examples/pilots/reports/pilot-integration-report.json
```

Use `--token ...` or `--username ... --password ...` when auth is enabled. The
CLI does not call OpenRouter, submit proposals, approve/apply changes, or write
to Elasticsearch.

Patch 54A adds `docs/pilots/first-company-pilot-runbook.md` and `examples/pilots/first_company_pilot_checklist.md` for the full operator workflow around this CLI: intake, benchmark rehearsal, company config preparation, preflight/seed/eval/report, optional validated OpenRouter smoke, and exit criteria.


## Retrieval eval CLI

Patch 50A adds a deterministic retrieval evaluator for the `platform_ops_v1` fixture. Patch 50B expands the fixture to 200 documents and adds hard-negative leakage checks. Patch 50B.1 adds query-hygiene scoring with alias-to-canonical expansion, weighted domain terms, and `generic_token_noise@10`. Patch 50C adds a retrieval comparison report for pilot/company index runs. Patch 53A expands the default fixture to a 500-document small-pilot corpus and records the corpus shape in `corpus_manifest.json`. The evaluator reads `retrieval_queries.jsonl`, `qrels.jsonl`, and `hard_negatives.jsonl`, compares a literal baseline with a SkeinRank-expanded run, and reports `NDCG@10`, `MRR@10`, `Recall@10`, `Precision@10`, `hard_negative_leakage@10`, and `generic_token_noise@10` deltas.

```bash
poetry run skeinrank-governance-retrieval-eval plan
poetry run skeinrank-governance-retrieval-eval eval \
  --out ../../examples/benchmarks/platform_ops_v1/reports/platform_ops_v1-retrieval-report.json
poetry run skeinrank-governance-retrieval-eval report \
  --file ../../examples/benchmarks/platform_ops_v1/reports/platform_ops_v1-retrieval-report.json
poetry run skeinrank-governance-retrieval-compare compare \
  --input ../../examples/benchmarks/platform_ops_v1/reports/platform_ops_v1-retrieval-report.json \
  --out ../../examples/benchmarks/platform_ops_v1/reports/platform_ops_v1-retrieval-comparison-report.json
```


## 5k synthetic smoke generator

Patch 53B adds an offline deterministic synthetic smoke generator for scale checks above the 500-document quality corpus. It generates a local 5,000-document JSONL corpus plus a manifest with batch counts, role counts, aliases, unchanged-skip candidates, and a corpus hash.

```bash
poetry run skeinrank-governance-synthetic-smoke plan
poetry run skeinrank-governance-synthetic-smoke generate
poetry run skeinrank-governance-synthetic-smoke report
```

The generator writes local artifacts under `examples/benchmarks/platform_ops_v1/reports/synthetic/` by default and does not call OpenRouter, Elasticsearch, the database, or runtime mutation endpoints.

## Benchmark performance report

Patch 53C adds an offline cost, latency, and throughput report for the 5k smoke manifest. It can also read an ignored OpenRouter live-pilot report for token/cost hints.

```bash
poetry run skeinrank-governance-benchmark-performance plan   --synthetic-manifest ../../examples/benchmarks/platform_ops_v1/reports/synthetic/platform_ops_v1-5k-manifest.json
poetry run skeinrank-governance-benchmark-performance report   --synthetic-manifest ../../examples/benchmarks/platform_ops_v1/reports/synthetic/platform_ops_v1-5k-manifest.json   --elapsed-seconds 300
poetry run skeinrank-governance-benchmark-performance show   --file ../../examples/benchmarks/platform_ops_v1/reports/platform_ops_v1-cost-latency-throughput-report.json
```

The report uses schema `skeinrank.benchmark_performance_report.v1` and keeps OpenRouter, Elasticsearch, database calls, and runtime mutation disabled.

## Containerized benchmark stack

Patch 48C adds a stack integration harness for the `platform_ops_v1` benchmark. It uses Docker Compose services for PostgreSQL, the Governance API, and Elasticsearch while keeping OpenRouter out of the loop.

From the repository root:

```bash
make benchmark-stack-up
make benchmark-stack-wait
make benchmark-stack-seed
make benchmark-stack-eval
make benchmark-stack-report
```

The direct CLI is also available:

```bash
poetry run python -m skeinrank_governance_api.benchmark_stack eval
poetry run skeinrank-governance-benchmark-stack report
```

See `docs/benchmarks/containerized-benchmark-integration.md`.

## Run the API locally

By default the API uses the same local SQLite URL as the governance CLI:

```bash
sqlite:///skeinrank_governance.db
```

From the repository root, initialize or upgrade the database through Alembic first:

```bash
cd packages/skeinrank-governance-api
poetry run python -m skeinrank_governance_api.migrations upgrade head
```

For quick local demos only, you can still use `SKEINRANK_GOVERNANCE_API_CREATE_TABLES=true`, but migration-based setup is the production-like path.

Then start the API from the same package directory:

```bash
poetry run skeinrank-governance-api --reload
```

Or use Uvicorn directly:

```bash
poetry run uvicorn skeinrank_governance_api.main:app --reload
```

Check health:

```bash
curl http://127.0.0.1:8010/healthz
```

## Configuration

The API reads database configuration from env vars. The API-specific variable has priority:

```bash
export SKEINRANK_GOVERNANCE_API_DATABASE_URL='sqlite:///skeinrank_governance.db'
```

The shared governance variable is still supported as a fallback:

```bash
export SKEINRANK_GOVERNANCE_DATABASE_URL='sqlite:///skeinrank_governance.db'
```

For PostgreSQL later:

```bash
export SKEINRANK_GOVERNANCE_DATABASE_URL='postgresql+psycopg://user:password@localhost:5432/skeinrank'
```

For local demos/tests only, tables can be created at startup:

```bash
export SKEINRANK_GOVERNANCE_API_CREATE_TABLES=true
```

The local UI origin is allowed by default for browser-based development:

```bash
http://127.0.0.1:5173
http://localhost:5173
```

Override CORS origins with a comma-separated value when needed:

```bash
export SKEINRANK_GOVERNANCE_API_CORS_ORIGINS='http://127.0.0.1:5173,http://localhost:5173'
```

Production-like deployments should run Alembic migrations before starting the API.

## Auth, users, and roles

Auth is disabled by default so existing local UI workflows keep working while the auth UI is still being built. Enable it explicitly when testing protected routes:

```bash
export SKEINRANK_GOVERNANCE_API_AUTH_ENABLED=true
export SKEINRANK_GOVERNANCE_API_BOOTSTRAP_ADMIN=true
export SKEINRANK_GOVERNANCE_API_ADMIN_USERNAME=admin
export SKEINRANK_GOVERNANCE_API_ADMIN_PASSWORD='change-me'
```

The bootstrap user is created only when the users table is empty. Passwords are stored as PBKDF2-SHA256 hashes and bearer tokens are stored hashed in the database.

Roles:

- `admin` — full control, including profiles, terms, aliases, snapshots, and users.
- `moderator` — terminology editor: terms, aliases, and snapshot export. No user management or profile management.
- `contributor` — read terminology and submit suggestions for moderator/admin approval.

Login and inspect the current user:

```bash
TOKEN=$(curl -s -X POST http://127.0.0.1:8010/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"change-me"}' | python -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')

curl http://127.0.0.1:8010/v1/auth/me \
  -H "Authorization: Bearer $TOKEN"
```

Create a user as admin:

```bash
curl -X POST http://127.0.0.1:8010/v1/auth/users \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"username":"moderator","password":"moderator-secret","role":"moderator","display_name":"Moderator"}'
```



## Headless Compose quickstart

From the repository root, start the API/PostgreSQL-only profile and run the golden path helper:

```bash
docker compose \
  --env-file deploy/docker/headless.env.example \
  -f docker-compose.headless.yml \
  up --build -d

deploy/docker/scripts/headless-golden-path.sh
```

The helper applies the example dictionary, creates a local binding, exports a `skeinrank.runtime_snapshot_artifact.v1` file, and prints a summary. See `docs/deployment/headless-quickstart.md` for the manual curl flow.

## Headless dictionary and snapshot APIs

Patch 36C/36D add automation-first routes for CI/CD, agents, and headless
runtime workers:

```bash
POST /v1/headless/dictionaries/validate
POST /v1/headless/dictionaries/apply
GET  /v1/headless/dictionaries/export?profile_name=infra_incidents
GET  /v1/headless/snapshots/export?binding_id=1
```

Export a binding-scoped runtime artifact from the CLI:

```bash
poetry run skeinrank-migrate snapshot-export \
  --binding-id 1 \
  --snapshot-version infra_incidents@v1 \
  --output runtime-snapshot.json

poetry run skeinrank-migrate snapshot-inspect runtime-snapshot.json
```

The snapshot artifact includes the binding context and compiled runtime aliases,
so it can be committed to GitOps repositories or loaded by lightweight runtime
workers without querying PostgreSQL on every request. Patch 36E adds a local
artifact loader/cache that validates the artifact checksum and reloads the file
when it changes.


## Headless benchmark CLI

Patch 48A adds a deterministic benchmark harness for the agent proposal workflow. It runs without OpenRouter and without Elasticsearch, using fixture data under `examples/benchmarks/platform_ops_v1`.

```bash
poetry run skeinrank-governance-benchmark seed --reset
poetry run skeinrank-governance-benchmark eval \
  --out ../../examples/benchmarks/platform_ops_v1/reports/platform_ops_v1-report.json
poetry run skeinrank-governance-benchmark report \
  --file ../../examples/benchmarks/platform_ops_v1/reports/platform_ops_v1-report.json
```

From the repository root the same flow is available as `make benchmark-seed`, `make benchmark-eval`, and `make benchmark-report`.

## Proposal batch apply

Patch 37D adds a release path for agent/human proposals:

```bash
POST /v1/governance/profiles/{profile_name}/suggestions/apply-batch
```

The endpoint applies pending suggestions atomically. With `publish_snapshot=true`
and a matching `binding_id`, it also pins the resulting runtime snapshot on that
binding so headless runtime clients can consume a reviewed version.

## User Console API

Patch 27 adds a migration-friendly API surface for users who work from JupyterHub, scripts, bots, or future CLI tools. It reuses the same governance database and role checks as the UI, but accepts a bulk dictionary JSON so companies do not need to enter existing dictionaries by hand. New payloads should include `schema_version: skeinrank.dictionary.v1`; legacy payloads without a schema version are treated as v1 for backward compatibility.

Endpoints:

```bash
POST /v1/console/dictionary/validate
POST /v1/console/dictionary/import
GET  /v1/console/dictionary/export?profile_name=infra_incidents
```

Role behavior:

- `admin`, `moderator`, and `contributor` can validate payloads and export dictionaries.
- `admin` and `moderator` can import into existing profiles.
- only `admin` can create a missing profile during import.

Minimal import payload:

```json
{
  "schema_version": "skeinrank.dictionary.v1",
  "profile_name": "infra_incidents",
  "profile_description": "Infra incident dictionary",
  "mode": "upsert",
  "terms": [
    {
      "canonical_value": "kubernetes",
      "slot": "TOOL",
      "aliases": [
        "k8s",
        {"value": "kube", "confidence": 0.95}
      ]
    }
  ],
  "profile_stop_list": [
    {"value": "tmp", "target": "alias", "reason": "too generic"}
  ],
  "global_stop_list": [
    {"value": "unknown", "target": "both", "reason": "global noise"}
  ]
}
```

Validate without writing:

```bash
curl -X POST http://127.0.0.1:8010/v1/console/dictionary/validate \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d @company_dictionary.json
```

Apply after validation:

```bash
curl -X POST http://127.0.0.1:8010/v1/console/dictionary/import \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d @company_dictionary.json
```

Export a profile back to the same stable shape. Exports include `schema_version`:

```bash
curl "http://127.0.0.1:8010/v1/console/dictionary/export?profile_name=infra_incidents" \
  -H "Authorization: Bearer $TOKEN"
```

Import modes:

- `upsert` — create missing values and update existing values.
- `strict` — report conflicts when the payload already exists.

The validation/import report includes the resolved schema version, planned create/update counts, duplicate warnings, alias/canonical conflicts, unsupported schema-version errors, and stop-list blocks.


## Dictionary Migration Tool

Patch 28 adds a small stdlib-based CLI on top of the User Console API. The tool does not write to the database directly; it calls the same FastAPI endpoints that notebooks, bots, and scripts can use.

Install the governance API package and run:

```bash
poetry run skeinrank-migrate --help
```

The API URL defaults to `http://127.0.0.1:8010` and can be overridden with `--api-url` or `SKEINRANK_CONSOLE_API_URL`. When API auth is enabled, pass a bearer token with `--token` or `SKEINRANK_API_TOKEN`.

Validate a dictionary JSON/YAML file without writing changes:

```bash
poetry run skeinrank-migrate validate ../../examples/migration/console_dictionary.example.json
poetry run skeinrank-migrate validate ../../examples/migration/console_dictionary.example.yaml
```

Apply the dictionary after validation:

```bash
poetry run skeinrank-migrate apply ../../examples/migration/console_dictionary.example.json
```

Export a profile back to the same stable migration JSON shape. Exports include `schema_version`:

```bash
poetry run skeinrank-migrate export --profile-name infra_incidents \
  --output infra_incidents.export.json
```

Useful environment setup for authenticated API runs:

```bash
export SKEINRANK_CONSOLE_API_URL=http://127.0.0.1:8010
export SKEINRANK_API_TOKEN="$TOKEN"
```

`validate` returns exit code `2` when the API returns an invalid validation report. Use `--allow-invalid` when you want to inspect/report invalid migrations without failing a shell pipeline.

## Database migrations

`skeinrank-governance` owns the SQLAlchemy models and canonical Alembic revision files. The API package exposes a configuration-aware migration wrapper that uses the same database URL resolution as the HTTP service.

Upgrade the configured database to the latest governance schema:

```bash
cd packages/skeinrank-governance-api
poetry run python -m skeinrank_governance_api.migrations upgrade head
```

Show the current database revision:

```bash
poetry run python -m skeinrank_governance_api.migrations current
```

Show migration history:

```bash
poetry run python -m skeinrank_governance_api.migrations history
```

Check that the database is at the current Alembic head and that all SQLAlchemy metadata tables exist:

```bash
poetry run python -m skeinrank_governance_api.migrations check
```

The same read-only report is available over HTTP:

```bash
curl http://127.0.0.1:8010/schema/health | python -m json.tool
```

Patch 45A also mirrors deployment health and current DB-backed agent tracking state into Prometheus metrics:

```bash
curl http://127.0.0.1:8010/metrics | grep -E "skeinrank_(database_up|schema_ok|agent_runs_current)"
```

Patch 45B adds structured log events and a sanitized troubleshooting report:

```bash
curl http://127.0.0.1:8010/v1/ops/troubleshooting/report | python -m json.tool
poetry run python -m skeinrank_governance_api.troubleshooting report
```

Patch 45C adds portable governance DB backup/restore commands:

```bash
poetry run python -m skeinrank_governance_api.backup_restore export --out backups/governance.json
poetry run python -m skeinrank_governance_api.backup_restore inspect --file backups/governance.json
poetry run python -m skeinrank_governance_api.backup_restore restore --file backups/governance.json --dry-run
```

See `docs/deployment/backup-restore.md` for restore drills and operational runbooks.

Patch 46A adds a production-oriented Docker Compose profile with `.env.production.example`, optional `ops`/`observability` profiles, Docker log rotation, and `deploy/docker/scripts/prod-smoke-test.sh`. Patch 46B adds env validation and secrets documentation:

```bash
cp .env.production.example .env
make prod-env-check
poetry run python -m skeinrank_governance_api.env_validation validate --file ../../.env
docker compose --env-file .env -f docker-compose.prod.yml config
docker compose --env-file .env -f docker-compose.prod.yml up --build -d
deploy/docker/scripts/prod-smoke-test.sh
# or fail if /readyz is degraded because an external dependency is unavailable
deploy/docker/scripts/prod-smoke-test.sh --strict
```

See `docs/deployment/production-compose.md` and `docs/deployment/env-and-secrets.md` for the full production-ish Compose runbook and secrets checklist.

When auth is enabled, the HTTP report requires an admin user. Personal/service-account tokens also need the `ops:reports:read` scope.

Downgrade one revision when developing locally:

```bash
poetry run python -m skeinrank_governance_api.migrations downgrade -1
```

The migration wrapper resolves database URL precedence in the same order as the API:

1. `SKEINRANK_GOVERNANCE_API_DATABASE_URL`
2. `SKEINRANK_GOVERNANCE_DATABASE_URL`
3. `sqlite:///skeinrank_governance.db`

If deployments need a custom migration directory, set:

```bash
export SKEINRANK_GOVERNANCE_API_ALEMBIC_SCRIPT_LOCATION=/path/to/alembic
```

`SKEINRANK_GOVERNANCE_API_CREATE_TABLES=true` remains available for lightweight demos/tests, but Alembic is the preferred operational path for users, roles, suggestions, snapshot history, and bindings.

## Current scope

This package currently provides:

- FastAPI app factory
- environment-based configuration
- SQLAlchemy session dependency
- `/healthz`, `/readyz`, and `/schema/health` endpoints
- Prometheus health and DB-backed agent tracking gauges under `/metrics`
- structured log events and `/v1/ops/troubleshooting/report` diagnostics
- portable governance DB backup/restore CLI and operational runbooks
- production-oriented Docker Compose profile, env validation, ops helpers, and smoke checks
- governance REST endpoints for profiles, terms, aliases, suggestions, profile/global stop lists, and snapshot export
- user-console dictionary validation, import, and export endpoints for migration workflows
- CRUD endpoints for updating/deleting profiles, canonical terms, and aliases
- local auth endpoints for login/logout/current user
- admin-only user management endpoints
- role-aware API permissions for Admin, Moderator, and Contributor
- Uvicorn launcher command
- Alembic migration wrapper and read-only schema-health check for the API database URL
- tests for app creation, health checks, DB dependency wiring, migrations, and governance routes

## Governance REST endpoints

Profiles:

```bash
curl http://127.0.0.1:8010/v1/governance/profiles

curl -X POST http://127.0.0.1:8010/v1/governance/profiles \
  -H "Content-Type: application/json" \
  -d '{"name":"default_it","description":"Default IT terms"}'

curl -X PATCH http://127.0.0.1:8010/v1/governance/profiles/default_it \
  -H "Content-Type: application/json" \
  -d '{"name":"infra_incidents","description":"Infra incident terminology"}'

curl -X DELETE http://127.0.0.1:8010/v1/governance/profiles/infra_incidents
```

Canonical terms:

```bash
curl -X POST http://127.0.0.1:8010/v1/governance/profiles/default_it/terms \
  -H "Content-Type: application/json" \
  -d '{"canonical_value":"kubernetes","slot":"TOOL"}'

curl http://127.0.0.1:8010/v1/governance/profiles/default_it/terms

curl -X PATCH http://127.0.0.1:8010/v1/governance/profiles/default_it/terms/kubernetes \
  -H "Content-Type: application/json" \
  -d '{"canonical_value":"kubernetes platform","slot":"PLATFORM","status":"active"}'

curl -X DELETE http://127.0.0.1:8010/v1/governance/profiles/default_it/terms/kubernetes%20platform
```

Aliases:

```bash
curl -X POST http://127.0.0.1:8010/v1/governance/profiles/default_it/terms/kubernetes/aliases \
  -H "Content-Type: application/json" \
  -d '{"alias_value":"k8s","confidence":0.97}'

# Replace 1 with the alias id returned by the create response.
curl -X PATCH http://127.0.0.1:8010/v1/governance/profiles/default_it/terms/kubernetes/aliases/1 \
  -H "Content-Type: application/json" \
  -d '{"alias_value":"kube","confidence":0.84,"status":"ambiguous"}'

curl -X DELETE http://127.0.0.1:8010/v1/governance/profiles/default_it/terms/kubernetes/aliases/1
```



Stop lists:

Global stop-list entries apply across all profiles:

```bash
curl -X POST http://127.0.0.1:8010/v1/governance/global-stop-list \
  -H "Content-Type: application/json" \
  -d '{"value":"unknown","target":"both","reason":"Organization-wide noise."}'

curl http://127.0.0.1:8010/v1/governance/global-stop-list

# Replace 1 with the global stop-list entry id returned by the create response.
curl -X PATCH http://127.0.0.1:8010/v1/governance/global-stop-list/1 \
  -H "Content-Type: application/json" \
  -d '{"value":"test","target":"alias","is_active":false}'

curl -X DELETE http://127.0.0.1:8010/v1/governance/global-stop-list/1
```

Profile stop-list entries apply only inside one profile:

```bash
curl -X POST http://127.0.0.1:8010/v1/governance/profiles/default_it/stop-list \
  -H "Content-Type: application/json" \
  -d '{"value":"service","target":"alias","reason":"Too generic for this profile."}'

curl http://127.0.0.1:8010/v1/governance/profiles/default_it/stop-list

# Replace 1 with the stop-list entry id returned by the create response.
curl -X PATCH http://127.0.0.1:8010/v1/governance/profiles/default_it/stop-list/1 \
  -H "Content-Type: application/json" \
  -d '{"value":"app","target":"both","is_active":false}'

curl -X DELETE http://127.0.0.1:8010/v1/governance/profiles/default_it/stop-list/1
```

Stop-list targets are `alias`, `canonical`, and `both`. Active global and profile stop-list entries block matching direct CRUD mutations, suggestion creation, suggestion approval, Elasticsearch dry-run matches, enrichment job matches, and evidence lookup warnings.

Elasticsearch bindings:

```bash
# Create a manual binding config. This stores where a profile should be applied later.
curl -X POST http://127.0.0.1:8010/v1/governance/elasticsearch/bindings \
  -H "Content-Type: application/json" \
  -d '{"name":"infra docs","profile_name":"default_it","index_name":"docs","text_fields":["title","body"],"target_field":"skeinrank","filter_field":"team","filter_value":"infra","mode":"dry_run","write_strategy":"reindex_alias_swap"}'

curl http://127.0.0.1:8010/v1/governance/elasticsearch/bindings
curl http://127.0.0.1:8010/v1/governance/elasticsearch/bindings?profile_name=default_it

# Replace 1 with the binding id returned by the create response.
curl -X PATCH http://127.0.0.1:8010/v1/governance/elasticsearch/bindings/1 \
  -H "Content-Type: application/json" \
  -d '{"index_name":"docs-v2","text_fields":["body"],"mode":"write","write_strategy":"in_place","is_enabled":false}'

curl -X DELETE http://127.0.0.1:8010/v1/governance/elasticsearch/bindings/1
```

Bindings are configuration-only in this API patch. They support the three core deployment shapes: one profile to one index, one profile to multiple indices through multiple bindings, and multiple profiles to one index when each binding has an explicit metadata filter such as `team = infra`.

Suggestions:

```bash
# Alias suggestion for an existing canonical term.
curl -X POST http://127.0.0.1:8010/v1/governance/profiles/default_it/suggestions \
  -H "Content-Type: application/json" \
  -d '{"suggestion_type":"alias","canonical_value":"kubernetes","alias_value":"kube","slot":"TOOL","context":"People search for kube in incident docs."}'

# Canonical term suggestion for moderator/admin review.
curl -X POST http://127.0.0.1:8010/v1/governance/profiles/default_it/suggestions \
  -H "Content-Type: application/json" \
  -d '{"suggestion_type":"canonical_term","canonical_value":"vector database","slot":"TOOL","description":"Storage system optimized for vector similarity search.","context":"No canonical term exists for vector databases yet."}'

curl http://127.0.0.1:8010/v1/governance/profiles/default_it/suggestions?status=pending

# Replace 1 with the suggestion id returned by the create response.
curl -X POST http://127.0.0.1:8010/v1/governance/profiles/default_it/suggestions/1/approve \
  -H "Content-Type: application/json" \
  -d '{"review_comment":"Approved."}'

curl -X POST http://127.0.0.1:8010/v1/governance/profiles/default_it/suggestions/1/reject \
  -H "Content-Type: application/json" \
  -d '{"review_comment":"Not used by this corpus."}'
```

Agent-ready proposal metadata can be attached to the same suggestion workflow:

```bash
curl -X POST http://127.0.0.1:8010/v1/governance/profiles/default_it/suggestions \
  -H "Content-Type: application/json" \
  -d '{"suggestion_type":"alias","canonical_value":"kubernetes","alias_value":"kube","slot":"TOOL","source":"discovery","proposal_source_type":"agent","proposal_source_name":"search-log-scout","idempotency_key":"search-log-scout:default_it:kube","source_payload":{"query_count":42}}'
```

Supported `proposal_source_type` values are `human`, `agent`, `cli`, `api`, `job`, and `import`. If `binding_id` is provided, it must reference a binding for the same profile. If `validation_summary` is omitted, SkeinRank stores an automatic proposal validation summary with checks for canonical availability, alias collisions, stop-list guardrails, noisy aliases, confidence, idempotency hints, and agent audit payloads. Callers may still provide their own `validation_summary` when they already ran an external checker. Patch 37E enforces idempotency keys for safe retries. Patch 37G adds proposal metrics and source quality reporting:

```bash
curl http://127.0.0.1:8010/v1/governance/proposals/source-quality \
  -H "X-SkeinRank-Role: admin"
```

Prometheus counters include proposal submissions, review decisions, and batch apply operations.

Agent-friendly REST tools expose the same flow without requiring callers to know
the full profile suggestions route shape:

```bash
curl -X POST http://127.0.0.1:8010/v1/tools/validate-alias \
  -H "Content-Type: application/json" \
  -d '{"profile_name":"default_it","canonical_value":"kubernetes","alias_value":"kube","slot":"TOOL","proposal_source_name":"search-log-scout"}'

curl -X POST http://127.0.0.1:8010/v1/tools/suggest-alias \
  -H "Content-Type: application/json" \
  -d '{"profile_name":"default_it","canonical_value":"kubernetes","alias_value":"kube","slot":"TOOL","proposal_source_name":"search-log-scout","source_payload":{"query_count":42}}'

curl -X POST http://127.0.0.1:8010/v1/tools/explain-query \
  -H "Content-Type: application/json" \
  -d '{"profile_name":"default_it","query":"k8s timeout","text_fields":["title","body"],"target_field":"skeinrank"}'
```

Approved alias suggestions create active aliases. Approved canonical term suggestions create active canonical terms.

Snapshot export:

```bash
curl -X POST http://127.0.0.1:8010/v1/governance/profiles/default_it/snapshot/export \
  -H "Content-Type: application/json" \
  -d '{"snapshot_version":"default_it@v1","description":"Runtime snapshot exported from the governance API"}'
```

The response is a runtime-compatible profile snapshot that can be passed to `skeinrank-core` through `--profile-file` or `load_attribute_profile(...)`.

Future patches will add snapshot publishing lifecycle, Elasticsearch write/reindex jobs, discovery ingestion, and richer review/audit workflows.

## Elasticsearch discovery

Elasticsearch discovery is optional and read-only. It is used by the governance UI to test connectivity, list indices, and inspect index mappings while creating enrichment bindings.

```bash
export SKEINRANK_ELASTICSEARCH_URL=http://localhost:9200
# optional basic auth
export SKEINRANK_ELASTICSEARCH_USERNAME=elastic
export SKEINRANK_ELASTICSEARCH_PASSWORD=...
# optional API key auth
export SKEINRANK_ELASTICSEARCH_API_KEY=...
```

API-specific names are also supported and take precedence:

```bash
export SKEINRANK_GOVERNANCE_API_ELASTICSEARCH_URL=http://localhost:9200
export SKEINRANK_GOVERNANCE_API_ELASTICSEARCH_USERNAME=elastic
export SKEINRANK_GOVERNANCE_API_ELASTICSEARCH_PASSWORD=...
export SKEINRANK_GOVERNANCE_API_ELASTICSEARCH_API_KEY=...
```

Discovery endpoints:

```text
GET /v1/governance/elasticsearch/connection/status
GET /v1/governance/elasticsearch/indices
GET /v1/governance/elasticsearch/indices/{index_name}/mapping
```

These endpoints do not update documents and do not execute enrichment jobs.

## Elasticsearch binding dry-run

Saved Elasticsearch bindings can be previewed with a read-only dry-run endpoint:

```text
POST /v1/governance/elasticsearch/bindings/{binding_id}/dry-run
```

Request body:

```json
{"limit": 3}
```

The endpoint samples documents from the configured index, applies the binding discriminator filter when present, reads configured text fields, matches active profile aliases, and returns the `would_write` payload for the configured target field. It does not update documents and does not start background jobs.

## Elasticsearch enrichment write strategy

Elasticsearch bindings include `write_strategy` metadata for future write jobs:

```text
in_place
reindex_alias_swap
```

`reindex_alias_swap` is the default because it is the safer production path: future enrichment jobs can create a new enriched index, validate the result, and swap an alias instead of writing directly into a live index. `in_place` is available for sandbox/dev workflows or small indexes where direct bulk partial updates are acceptable.

This API patch only stores and validates the strategy. It does not perform writes, reindexing, alias swaps, or background jobs.
### Patch 25g — reindex + alias swap jobs

Patch 25g adds the backend job contract for Elasticsearch enrichment writes. A
binding can now start a synchronous MVP enrichment job through:

```bash
POST /v1/governance/elasticsearch/bindings/{binding_id}/jobs
```

The job record stores status, write strategy, source index, target index, alias
name, counters, result JSON, and error message. The default production-oriented
write strategy is `reindex_alias_swap`; `in_place` remains available for
sandbox/dev use cases.

Patch 25g introduced synchronous MVP execution. Patch 35 keeps `sync` as the
default backend and adds optional Celery/RabbitMQ dispatch for background worker
execution. Patch 36 extends the worker path with bounded parallel document chunks.

## Elasticsearch async worker backend

Set the enrichment backend to `celery` to enqueue jobs instead of executing them
inline in the FastAPI request:

```bash
export SKEINRANK_GOVERNANCE_API_ENRICHMENT_JOBS_BACKEND=celery
export SKEINRANK_GOVERNANCE_API_CELERY_BROKER_URL=amqp://guest:guest@localhost:5672//
export SKEINRANK_GOVERNANCE_API_CELERY_TASK_QUEUE=skeinrank.enrichment
export SKEINRANK_GOVERNANCE_API_ENRICHMENT_CHUNK_SIZE=500
```

`sync` remains the default and requires no RabbitMQ:

```bash
export SKEINRANK_GOVERNANCE_API_ENRICHMENT_JOBS_BACKEND=sync
```

In celery mode the start-job endpoint creates a durable job row with
`status=queued`, records the coordinator Celery task id in `result_json`, and
returns immediately. The coordinator worker marks the job `running`, prepares the
target/reindex step when needed, and dispatches bounded chunk tasks. Chunk tasks
update counters and per-chunk metadata in `result_json`; the final completed
chunk marks the job `succeeded` and swaps the alias for `reindex_alias_swap` jobs.

Run RabbitMQ separately, for example:

```bash
docker run --rm -p 5672:5672 -p 15672:15672 rabbitmq:3.13.7-management
```

Run API and worker separately:

```bash
poetry run skeinrank-governance-api --reload
poetry run skeinrank-governance-worker --loglevel=info
```

The direct Celery command is also supported:

```bash
poetry run celery -A skeinrank_governance_api.worker:celery_app worker --loglevel=info
```

Chunk size can also be passed per job as `chunk_size` in
`POST /v1/governance/elasticsearch/bindings/{binding_id}/jobs`. The global
default is `SKEINRANK_GOVERNANCE_API_ENRICHMENT_CHUNK_SIZE`, with the short alias
`SKEINRANK_ENRICHMENT_CHUNK_SIZE`.

Patch 36 adds parallel chunk execution. Patch 38 adds safe cancellation for
queued/running jobs; retry UI, Flower, scheduled jobs, and rollback controls
remain follow-up patches.

## Elasticsearch enrichment job time filters

Elasticsearch bindings can optionally scope dry-runs and write-mode enrichment
jobs by document time:

```json
{
  "timestamp_field": "created_at",
  "time_window_days": 1825
}
```

When both values are present, dry-run and job search/reindex requests include a
range filter from `now-{time_window_days}d` to `now`. Search samples are sorted
by the timestamp field descending internally; the API does not expose a separate
sort setting. `max_documents` still limits the number of documents processed
inside the window.

## Elasticsearch evidence API

Saved Elasticsearch bindings can be queried for bounded, read-only evidence
snippets:

```text
POST /v1/governance/elasticsearch/bindings/{binding_id}/evidence
```

Example request:

```json
{
  "query": "k8s",
  "canonical_value": "kubernetes",
  "max_documents": 5,
  "context_chars": 80
}
```

The response includes the binding metadata, normalized query, warnings, and a
small list of snippets with plain `fragment`, `highlighted_fragment`,
`matched_text`, and match offsets. Evidence lookup respects the binding
`filter_field`/`filter_value` discriminator and optional
`timestamp_field`/`time_window_days` range filter. It does not write to
Elasticsearch and is safe for contributor/reviewer validation workflows.

## Suggestion evidence snapshots

Patch 33 adds a profile-scoped endpoint that refreshes Elasticsearch evidence and
saves the bounded evidence result on a pending suggestion:

```text
POST /v1/governance/profiles/{profile_name}/suggestions/{suggestion_id}/evidence/refresh
```

Example request:

```json
{
  "binding_id": 1,
  "max_documents": 5,
  "context_chars": 80
}
```

If `query` is omitted, alias suggestions use `alias_value`; canonical-term
suggestions use `canonical_value`. The binding must belong to the same profile as
the suggestion. The endpoint returns the updated suggestion with:

- `evidence_snapshot` — binding/query metadata, warnings, and highlighted snippets;
- `evidence_checked_by`;
- `evidence_checked_at`.

Only pending suggestions can be refreshed so approved/rejected review history is
not mutated. Contributors, moderators, and admins can refresh evidence; approval
remains limited to moderators/admins.


## API tokens and service accounts

Patch 29 adds copy-once API tokens for external clients.

Human users can create personal access tokens for notebooks, scripts, or local CLI work:

```bash
curl -X POST http://127.0.0.1:8010/v1/auth/api-tokens \
  -H "Authorization: Bearer $LOGIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Jupyter migration token",
    "scopes": ["migration:validate", "migration:apply", "migration:export"],
    "expires_in_days": 90
  }'
```

The response includes an `sk_pat_...` token once. The API stores only a SHA-256 hash and a short token prefix.

Admins can create service accounts for bots and automation:

```bash
curl -X POST http://127.0.0.1:8010/v1/auth/service-accounts \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "migration-bot", "role": "admin"}'

curl -X POST http://127.0.0.1:8010/v1/auth/service-accounts/migration-bot/tokens \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "CI import token",
    "scopes": ["migration:validate", "migration:apply", "migration:export"]
  }'
```

The second response includes an `sk_sat_...` token once.

Console dictionary endpoints now enforce migration scopes for API tokens:

- `migration:validate` for `POST /v1/console/dictionary/validate`
- `migration:apply` for `POST /v1/console/dictionary/import`
- `migration:export` for `GET /v1/console/dictionary/export`

Regular login/session tokens continue to use role checks only. Personal and service-account API tokens must pass both role checks and scope checks.


## User account status controls

Patch 31 adds explicit account statuses for human users:

```text
active
suspended
deactivated
```

Admins can change user status and revoke all personal API tokens for one user:

```bash
curl -X PATCH http://127.0.0.1:8010/v1/auth/users/alex/status \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"status": "suspended"}'

curl -X POST http://127.0.0.1:8010/v1/auth/users/alex/revoke-api-tokens \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

Suspended and deactivated users cannot sign in and their personal API tokens are rejected by Bearer auth. Reactivating a user restores access for non-revoked, non-expired personal API tokens. `revoke-api-tokens` permanently revokes the user-owned personal API tokens without touching service account tokens.

## Patch 39 — Rollout / rollback metadata

`reindex_alias_swap` enrichment jobs now record rollout metadata in
`result_json.rollout`. The API captures the indices attached to the alias before
swap, the indices attached after swap, and a rollback candidate when the previous
alias state points to exactly one index.

The metadata is written by both synchronous enrichment execution and Celery
chunked execution:

```json
{
  "strategy": "reindex_alias_swap",
  "status": "alias_swapped",
  "alias_name": "docs_current",
  "source_index": "docs_v1",
  "target_index": "docs_v2",
  "previous_alias_indices": ["docs_v1"],
  "new_alias_indices": ["docs_v2"],
  "rollback_candidate_index": "docs_v1",
  "rollback_available": true,
  "alias_swap_completed": true
}
```

Patch 40 adds the safe rollback API:

```bash
curl -X POST http://127.0.0.1:8010/v1/governance/elasticsearch/jobs/123/rollback \
  -H "Content-Type: application/json" \
  -d '{"reason": "bad rollout"}'
```

The rollback endpoint is conservative: it only works for succeeded
`reindex_alias_swap` jobs with completed alias swaps, a single rollback
candidate, and a current alias state that still matches the expected
post-rollout indices. Successful rollback writes `result_json.rollout.rollback`
and marks the rollout status as `rolled_back`.


### Headless dictionary facade

Use the headless facade for CI/CD, agents, and service integrations:

```text
POST /v1/headless/dictionaries/validate
POST /v1/headless/dictionaries/apply
GET  /v1/headless/dictionaries/export?profile_name=...
```

The legacy console migration routes remain available and use the same
implementation. New automation should prefer `/v1/headless/dictionaries/*`.

## MCP server MVP

Patch 37F adds a small Model Context Protocol (MCP) stdio server that adapts
agent tool calls to the existing REST API. It has no mandatory third-party MCP
runtime dependency; business logic stays in the governance API routes.

Start the governance API first, then run:

```bash
poetry run skeinrank-mcp --api-url http://127.0.0.1:8010
```

Environment variables:

```bash
export SKEINRANK_MCP_GOVERNANCE_API_URL=http://127.0.0.1:8010
export SKEINRANK_MCP_ROLE=admin
# optional when auth is enabled
export SKEINRANK_MCP_API_TOKEN=...
```

MCP tools exposed in this MVP:

- `skeinrank_list_bindings`
- `skeinrank_explain_query`
- `skeinrank_validate_alias`
- `skeinrank_submit_alias_proposal`
- `skeinrank_get_proposal_status`

Agents submit proposals for review; they do not mutate active runtime
terminology directly.

## OpenRouter alias scout foundation

The repository includes a small reference runner for future OpenRouter-powered
agents:

```bash
python ../../examples/agents/openrouter_alias_scout/run_alias_scout.py --dry-run-plan
python ../../examples/agents/openrouter_alias_scout/run_alias_scout.py --print-tool-schemas
python ../../examples/agents/openrouter_alias_scout/run_alias_scout.py --print-system-prompt
python ../../examples/agents/openrouter_alias_scout/run_alias_scout.py --print-sample-review-prompt
python ../../examples/agents/openrouter_alias_scout/run_alias_scout.py --discover-candidates
python ../../examples/agents/openrouter_alias_scout/run_alias_scout.py --print-sample-candidate-pack
python ../../examples/agents/openrouter_alias_scout/run_alias_scout.py --sample-evidence
python ../../examples/agents/openrouter_alias_scout/run_alias_scout.py --print-sample-evidence-pack
python ../../examples/agents/openrouter_alias_scout/run_alias_scout.py --run-demo-report
python ../../examples/agents/openrouter_alias_scout/run_alias_scout.py --print-demo-review-prompt
```

Patch 40F keeps the runner dependency-light and LLM-free. Patch 40G adds
OpenRouter/OpenAI-compatible tool schemas, safety prompts, compact review prompt
helpers, and strict structured output parsing. Patch 40H adds deterministic
failed-query candidate discovery, pruning, scoring, and compact fact-pack output.
Patch 40I adds local compact evidence windows with explicit size limits, producing
`skeinrank.agent_evidence_sampling.v1` and LLM-ready evidence packs without
calling OpenRouter. Patch 40K adds `skeinrank.agent_demo_report.v1`, a local E2E
report that stitches discovery and evidence into a review queue while keeping
`proposals_submitted` at `0`. The example still does not execute model tool calls;
it only documents the contract that later agent patches can wire to model review
and LangGraph orchestration on top of the same safe proposal workflow.


### Patch 38A/38B: term tags in governance and runtime

Dictionary terms and governance term APIs now accept optional `tags` on canonical
terms. Tags are normalized, deduplicated facets (`infra`, `backend`, `storage`)
that complement the primary `slot`. Runtime snapshot alias entries now carry
those tags too, so exported artifacts and query/canonicalization debug output
can explain both the primary slot and richer term facets.


### Conflict detection report

The API exposes a read-only conflict report for coverage-framework workflows:

```text
GET /v1/governance/conflicts
GET /v1/governance/conflicts?profile_name=infra_incidents
```

The report surfaces cross-profile alias reuse, active alias/canonical stop-list
collisions, and pending proposal conflicts without mutating terminology. Each
conflict includes a deterministic `fingerprint`, default severity, and persisted
review state. Admins and moderators can update review state through
`PATCH /v1/governance/conflicts/{fingerprint}/review`.

### Ambiguous alias candidates

The API exposes profile-scoped ambiguous alias candidate endpoints for coverage review. They let reviewers record surfaces like `pg` with multiple candidate canonicals while keeping runtime snapshots unchanged until binding policy resolution is added. Patch 38F also links conflicting proposals to this model: when a new alias proposal disagrees with an active alias or another pending proposal, SkeinRank upserts ambiguous alias candidates automatically and leaves the proposal pending for review.

### Binding policies

The governance API exposes binding-scoped policy metadata under `/v1/governance/elasticsearch/bindings/{binding_id}/policy`. Policies are optional and are used to describe how a binding should later resolve ambiguous candidates. They store `preferred_slots`, `allowed_tags`, `deny_slots`, and `context_rules`. Runtime canonicalization/query planning now applies an active policy when `binding_id` is provided, exposing `policy_decisions` in debug output.


### Runtime binding policy resolver

Patch 38H connects binding policies to runtime endpoints. When a request uses `binding_id`, the runtime resolver can deny noisy slots, require allowed tags, and select ambiguous candidates by context rule or preferred slot. Responses include `policy_decisions` for audit/debug and keep the write model unchanged.

## Snapshot before/after evaluation

Use `snapshot-eval` to compare two local runtime snapshot artifacts before a
release:

```bash
poetry run skeinrank-migrate snapshot-eval \
  --before before.json \
  --after after.json \
  --queries queries.jsonl \
  --output eval-report.json
```

The command is offline and read-only. It validates both artifacts, compares their
alias/tag coverage, and can show which sample queries would produce a different
canonicalization plan.


## Coverage framework examples

See `docs/concepts/coverage-framework.md`, `docs/guides/coverage-framework.md`, and `examples/coverage-framework/` for the Phase C controlled-coverage workflow: term tags, conflict reports, ambiguous alias candidates, binding policies, runtime policy decisions, and snapshot before/after evaluation.

### Patch 40J — OpenRouter execution / LangGraph-ready workflow

Patch 40J adds the first live OpenRouter execution path for the alias scout. Use
`--print-llm-review-plan` to preview the LangGraph-ready state-machine workflow
without network calls, then set `OPENROUTER_API_KEY` and run `--llm-review` to
call OpenRouter `/chat/completions` for strict `propose`, `reject`, or
`needs_evidence` judgments. The output schema is
`skeinrank.agent_llm_review_report.v1`. Proposal submission remains disabled by
default, so the workflow prepares proposal payloads but does not mutate SkeinRank
state.

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py --print-llm-review-plan
OPENROUTER_API_KEY=... python examples/agents/openrouter_alias_scout/run_alias_scout.py --llm-review --model openai/gpt-4o-mini --max-candidates 3
```

## Patch 40L — OpenRouter agent security profile

Patch 40L adds a safe service-account profile to the OpenRouter alias scout. The
runner can now print and validate a redacted security report before live model
review:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py --print-security-profile
python examples/agents/openrouter_alias_scout/run_alias_scout.py --check-security-profile
```

The report schema is `skeinrank.agent_security_profile.v1`. Proposal submission
remains disabled by default; the agent may prepare proposal payloads, but it
must not directly write dictionaries, publish snapshots, push to Git, or mutate
runtime state.

## Patch 40M — OpenRouter agent budget and cache

Patch 40M adds run budgets and JSON response caching to the OpenRouter alias
scout. It keeps the agent safe by default: no backend routes are changed,
proposal submission stays disabled, and cached responses never mutate runtime
state. Use `--print-budget-cache-plan` for an offline `skeinrank.agent_budget_cache_plan.v1`
preview, `--max-llm-calls` / `--max-run-cost-usd` for live-run limits, and
`--clear-llm-cache` to remove the configured local cache.
## Patch 40N — Agent evaluation loop

Patch 40N adds an offline evaluation report for the OpenRouter alias scout. It
can score the local demo pipeline or a saved `skeinrank.agent_llm_review_report.v1`
without calling OpenRouter, SkeinRank, Elasticsearch, or publishing snapshots.

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py --run-evaluation-report
python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --llm-review-report /tmp/skeinrank-alias-scout-llm-report.json \
  --run-evaluation-report
```

The output schema is `skeinrank.agent_evaluation_report.v1`. It reports
evidence coverage, LLM action mix, proposal-ready counts, optional human/policy
outcomes (`accepted`, `rejected`, `blocked`, `ambiguous`, `noisy`, `conflict`),
cost/cache summary, and a quality gate. Snapshot before/after evaluation remains
disabled until approved proposals are applied through the governed workflow.

### Patch 40O — Agent deployment recipe

Patch 40O adds a Docker Compose deployment recipe for the OpenRouter alias scout.
Use `--print-deployment-recipe` to inspect the offline `skeinrank.agent_deployment_recipe.v1` report, or `make agent-deploy-plan` / `make agent-compose-config` from the repository root. The reference service defaults to an offline evaluation report; proposal submission and runtime mutation remain disabled.

## Patch 41A — Canonical hints and stronger review pack

Patch 41A improves the OpenRouter alias scout quality loop without changing backend routes or mutating runtime state. The runner now includes configured canonical hints in each candidate pack, so the model can choose from known terms such as `kubernetes`, `postgresql`, `elasticsearch`, and `rabbitmq` instead of guessing from raw evidence only.

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py --print-canonical-hints
python examples/agents/openrouter_alias_scout/run_alias_scout.py --print-sample-evidence-pack
```

The report schema is `skeinrank.agent_canonical_hints.v1`. Validation-sprint noise such as `queue`, `red`, and `shard` is pruned before LLM review by default, while real alias candidates such as `pg`, `k8s`, and `kube` receive `possible_canonical`, `slot`, `canonical_hint`, `canonical_candidates`, and `known_canonicals` fields in the review pack.


## Patch 41B — Validate and submit proposals safely

Patch 41B connects high-confidence agent `proposal_payload` values to the
existing SkeinRank agent tools without changing backend routes. The runner can
preview a submission plan, validate ready proposals through
`POST /v1/tools/validate-alias`, and optionally submit pending proposals through
`POST /v1/tools/suggest-alias` only when explicitly requested and allowed by
security/config.

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --llm-review-report /tmp/skeinrank-41a-llm-report.json \
  --print-proposal-submission-plan

python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --llm-review-report /tmp/skeinrank-41a-llm-report.json \
  --validate-ready-proposals
```

Submission remains opt-in and governed. It creates pending proposals only; it
never writes directly to dictionaries, never pushes Git, and never publishes
runtime snapshots.

## Patch 41C — Agent validation statuses and idempotent proposal handling

Patch 41C keeps proposal submission safe while making validation reports more
useful for agent workflows. Validation warnings are now classified before any
optional submission: existing aliases that already map to the requested canonical
are treated as idempotent no-ops, slot mismatches are routed to manual review,
and blocked validations are never submitted.

This means an agent run can distinguish:

```text
passed → eligible for optional submission
existing alias warning → idempotent_existing_alias
slot mismatch warning → manual_review_required
blocked → blocked
```

The runner still does not mutate runtime dictionaries or publish snapshots.


## Patch 41D — New alias proposal smoke test

Patch 41D adds a controlled smoke path for a brand-new alias proposal. It does not call OpenRouter and does not publish snapshots. The runner can generate a proposal-ready LLM report for the configured smoke alias, validate it through `POST /v1/tools/validate-alias`, and, only with an explicit submit flag, create a pending proposal through `POST /v1/tools/suggest-alias`.

Preview the smoke plan without network calls:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py --print-new-alias-smoke-plan
```

Write a proposal-ready smoke report:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --write-new-alias-smoke-llm-report /tmp/skeinrank-new-alias-smoke-llm.json
```

Validate the smoke proposal without saving it:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py --run-new-alias-smoke-test
```

Create one pending proposal and verify idempotent retry explicitly:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --submit-new-alias-smoke-test \
  --write-new-alias-smoke-report /tmp/skeinrank-new-alias-smoke-report.json
```

The default smoke alias is `pgx → postgresql` in the `infra_incidents` profile. Re-running the submit smoke should not create duplicate proposals; the second `suggest-alias` call is expected to return an idempotent retry.

## Patch 41E — Elasticsearch evidence connector

Patch 41E adds an optional, read-only Elasticsearch/OpenSearch evidence connector for the OpenRouter alias scout. It does not change backend routes, does not call OpenRouter, and does not mutate dictionaries, snapshots, or runtime state. The connector searches a configured index for discovered candidates, normalizes hits into local evidence records, and reuses the existing compact evidence sampler.

Preview the connector plan without network calls:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py --print-elasticsearch-evidence-plan
```

Sample evidence from Elasticsearch for discovered candidates:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --sample-evidence-from-elasticsearch \
  --elasticsearch-url http://127.0.0.1:9200 \
  --elasticsearch-index skeinrank-agent-evidence \
  --elasticsearch-text-field title \
  --elasticsearch-text-field text
```

Export normalized Elasticsearch hits to JSONL for offline review:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --write-elasticsearch-evidence-records /tmp/skeinrank-es-evidence.jsonl
```


### Patch 41F — Agent tracking contract

The OpenRouter alias scout reference runner now supports local run/document tracking through `--print-agent-tracking-plan`, `--write-agent-tracking-report`, and `--append-agent-tracking-ledger`. This patch does not change the Governance API schema or routes.

### Patch 41G — Proposal inbox / review workflow

The OpenRouter alias scout can now build an offline proposal inbox from saved LLM review and validation/submission reports. Use `--print-proposal-inbox-plan`, `--build-proposal-inbox`, and `--write-proposal-inbox` from `examples/agents/openrouter_alias_scout/run_alias_scout.py`. This patch does not add backend routes or migrations.


### Patch 41H — Apply approved proposals + snapshot evaluation

The OpenRouter alias scout can now build an offline approved-proposal apply plan from a saved proposal inbox and can evaluate before/after snapshot artifacts. Use `--print-approved-apply-plan`, `--build-approved-apply-plan`, `--write-approved-apply-plan`, `--run-snapshot-evaluation`, and `--write-snapshot-evaluation-report`. This patch does not add backend routes or migrations.

### Agent scheduled runner checks

Patch 41I adds a dependency-light scheduled runner for the OpenRouter alias scout.
From this package, the safe offline cycle can be invoked with:

```bash
poetry run python ../../examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --print-scheduled-runner-plan

poetry run python ../../examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --run-agent-cycle
```

The default scheduled cycle writes reports only and does not call OpenRouter or mutate
SkeinRank state.

### Patch 42A — full agent integration smoke test

The OpenRouter alias scout now includes a network-free full contour smoke test:

```bash
poetry run python ../../examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --write-integration-smoke-report /tmp/skeinrank-agent-smoke.json
```

It builds deterministic smoke artifacts for the agent report chain without calling
OpenRouter, Elasticsearch, or the Governance API.

### Patch 42B — real Elasticsearch agent validation

The OpenRouter alias scout now includes a real Elasticsearch/OpenSearch validation scenario. It is exposed through the example runner and remains outside the governance API surface; no new backend route is required.

### Patch 42C — Agent artifact standard

Agent runs now support a normalized artifact layout with `manifest.json`,
`run_summary.json`, and per-stage reports. This is used by scheduled/worker-mode
runs and is safe for CI/Airflow collection.

### Patch 42E — Dictionary import → binding → snapshot quickstart

Patch 42E adds a safe quickstart around existing governance endpoints. From the repository root or package Poetry environment, use `--print-dictionary-quickstart-plan`, `--write-dictionary-quickstart-payloads`, and `--run-dictionary-quickstart` to validate a sample dictionary payload. Applying the import, creating the Elasticsearch binding, and exporting the source=latest snapshot artifact require explicit CLI flags.

- Proposal batch hardening: `apply-batch/preview` provides a no-mutation dry run, and `apply-batch` now requires explicit `allow_warnings` for validation-warning proposals.

### Runtime API final smoke

Patch 42G adds a dependency-light smoke runner for the runtime API layer:

```bash
poetry run python ../../examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --print-runtime-api-smoke-plan

poetry run python ../../examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --write-runtime-api-smoke-report /tmp/sr-runtime-smoke.json
```

It validates `/v1/text/canonicalize`, `/v1/query/plan`, and optional `/v1/headless/snapshots/export` without mutating runtime state.

### Patch 42D — Docker Compose full demo scenario

The `openrouter-agent-full-demo` Compose overlay provides a report-only full demo path for the OpenRouter alias scout. Use `--print-docker-demo-plan` to inspect the plan before running Docker Compose.



### Agent run registry

The API includes a DB-backed agent run registry for scheduled/worker executions. Use it to register one durable run row before or during an agent cycle, then update status and report metadata as the cycle progresses.

```bash
curl -X POST http://127.0.0.1:8010/v1/agents/runs \
  -H 'Content-Type: application/json' \
  -d '{"run_id":"agent-run-001","agent_name":"openrouter_alias_scout","status":"queued","trigger_type":"manual"}'
```

Run registry writes do not change dictionaries, proposals, snapshots, or runtime state.


### Agent document visit API

The API exposes DB-backed document visit tracking at `/v1/agents/runs/{run_id}/document-visits`. This is the first persistent layer for determining whether an agent should scan or skip source documents in future runs.


### Agent LLM reviews and proposal attempts

The API exposes DB-backed LLM review and proposal-attempt tracking at `/v1/agents/runs/{run_id}/llm-reviews` and `/v1/agents/runs/{run_id}/proposal-attempts`. These endpoints persist audit metadata only; they do not submit proposals or mutate snapshots.


### Proposal lifecycle hardening

The governance API now returns proposal lifecycle metadata on suggestions and enforces the same warning/blocked validation gates for single-suggestion approval as for batch apply. Use `allow_warnings=true` only after a human or policy review.

### Proposal batch idempotency

`apply-batch` now distinguishes created changes from idempotent no-ops via `idempotent_suggestion_ids`, making worker retries safe after network interruptions.

### Patch 43C — RBAC/scoped token enforcement for agent actions

Agent-facing APIs now enforce API-token scopes in addition to role checks. Session
login tokens and local-dev mode keep the existing role-based behavior, while
personal/service-account API tokens must include the required scopes.

Recommended service-account scopes:

```text
agent:runs:read
agent:runs:write
agent:tracking:read
agent:tracking:write
agent:tools:read
agent:tools:validate
agent:tools:suggest
agent:tools:explain
ops:reports:read
```

This keeps scheduled agents and CI jobs least-privileged: read-only jobs can list
runs and tracking records, validation-only jobs can call `validate-alias`, and
proposal-writing jobs must explicitly carry `agent:tools:suggest`.


## Production-ish upgrade runbooks

Deployment upgrades should use the root Makefile helpers:

```bash
make prod-upgrade-check
make prod-preflight
make prod-upgrade
make prod-post-upgrade-smoke
```

See `docs/deployment/upgrade-guide.md`, `docs/deployment/migration-safety.md`, and `docs/deployment/release-checklist.md`.

## OpenRouter live pilot

Patch 48B keeps live agent execution opt-in and bounded. Configure `OPENROUTER_API_KEY` locally, preview the plan first, then run a small live pilot:

```bash
make agent-openrouter-pilot-plan
OPENROUTER_API_KEY=sk-or-... make agent-openrouter-pilot-report
```

The live pilot writes ignored reports under `examples/agents/openrouter_alias_scout/reports/live-pilot/` and does not approve/apply proposals or publish snapshots. Use `make agent-openrouter-pilot-validate` only after the Governance API and scoped agent token are configured.


### Benchmark stack troubleshooting

If `benchmark-stack-up` reports a Docker container name conflict for `skeinrank-*-dev`, the stack target now prunes the fixed dev-stack benchmark containers before startup:

```bash
make benchmark-stack-prune-containers
make benchmark-stack-up
```

The prune step removes containers only; named volumes are not deleted. Use `docker compose -f docker-compose.dev.yml down -v` only when you intentionally want to remove persisted dev volumes.

The stack benchmark connects to PostgreSQL from the local Poetry environment, so run `cd packages/skeinrank-governance-api && poetry install` after applying dependency changes.

### Proposal quality metrics

Patch 49B adds `proposal_quality` to benchmark reports. It exposes rates, coverage, breakdowns, per-alias outcomes, and proposal-quality gates for tuning agent prompts, validators, and candidate filters without relying only on pass/fail status.

Patch 49C adds `agent_decision_diagnostics` with document decisions, candidate decisions, skipped-candidate explanations, validator reasons, and missing-alias diagnostics. This helps explain why an alias was proposed, blocked, skipped as unchanged, or treated as an idempotent no-op.


### Patch 49D — Live OpenRouter validated pilot

Adds an explicit validate-only live pilot flow for OpenRouter proposals against the SkeinRank Governance API. Use `make benchmark-agent-live-validated-pilot-plan` to preview and `make benchmark-agent-live-validated-pilot-report` or `make benchmark-agent-live-validated-pilot-stack` for guarded live validation. Reports include `validated_pilot` diagnostics and keep runtime mutation disabled.

### Agent run progress API

Long-running agent runs can now expose a safe, read-only progress snapshot:

```bash
curl http://127.0.0.1:8010/v1/agents/runs/agent-run-001/progress
```

The response uses schema `skeinrank.agent_run_progress.v1` and aggregates existing tracking rows for documents, candidates, evidence windows, LLM reviews, proposal attempts, and errors. If the run summary includes `expected_documents_total` and `phase`, the endpoint also returns `percent_complete` and a human-readable phase.

The progress endpoint is observational only: it does not run the agent, submit proposals, apply dictionary changes, publish snapshots, or call OpenRouter/Elasticsearch.

### Agent run resume plan API

Long-running agent runs can also ask for the next bounded resume/retry batch:

```bash
curl -X POST http://127.0.0.1:8010/v1/agents/runs/agent-run-001/resume-plan \
  -H "Content-Type: application/json" \
  -d '{"batch_limit":100,"retry_errors":true,"retry_skipped":false}'
```

The response uses schema `skeinrank.agent_run_resume_plan.v1`. It includes `limits`, `summary.by_kind`, and `work_items` for unfinished documents, document errors, candidate errors, LLM review errors, proposal errors, skipped documents when requested, and forced rescans when requested.

The planner is read-only: it does not mutate the run, execute workers, call OpenRouter/Elasticsearch, submit proposals, apply dictionary changes, or publish snapshots.

### Agent run diagnostics/report API

Operators can inspect a run-level diagnostics report before deciding whether to resume, retry, or stop a long-running agent job:

```bash
curl http://127.0.0.1:8010/v1/agents/runs/agent-run-001/report \
  | python -m json.tool
```

The response uses schema `skeinrank.agent_run_report.v1`. It embeds the `/progress` snapshot and adds sampled skipped/unchanged documents, sampled errors, manual-review items, proposal validation outcomes, recommendations, and LLM usage/cost hints from persisted review metadata.

The report endpoint is read-only: it does not mutate the run, execute workers, call OpenRouter/Elasticsearch, submit proposals, apply dictionary changes, or publish snapshots.

### Patch 53A.1 — validated pilot preflight hotfix

The OpenRouter validated pilot now checks the actual read-only `POST /v1/tools/validate-alias` tool before spending model budget. This catches missing profile/binding contexts early and points operators to seed the benchmark stack or pass an existing `--profile-name` / `--binding-id`.

### Patch 53B — 5k synthetic smoke generator

Adds `skeinrank_governance_api.synthetic_smoke` and the `skeinrank-governance-synthetic-smoke` Poetry script for deterministic 5k JSONL corpus generation. The generated artifacts are intended for local scale smoke runs and are not committed by default.

### Patch 53C — Cost, latency, throughput report

Adds `skeinrank_governance_api.benchmark_performance` and the `skeinrank-governance-benchmark-performance` Poetry script for offline performance reporting. The report reads the 5k synthetic manifest plus optional live-pilot usage JSON and outputs documents/minute, seconds/document, batch latency, token/cost rates, skip/cache/idempotency savings, and a simple 100k-document projection without provider, Elasticsearch, database, or runtime mutation calls.
