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


## User Console API

Patch 27 adds a migration-friendly API surface for users who work from JupyterHub, scripts, bots, or future CLI tools. It reuses the same governance database and role checks as the UI, but accepts a bulk dictionary JSON so companies do not need to enter existing dictionaries by hand.

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

Export a profile back to the same stable shape:

```bash
curl "http://127.0.0.1:8010/v1/console/dictionary/export?profile_name=infra_incidents" \
  -H "Authorization: Bearer $TOKEN"
```

Import modes:

- `upsert` — create missing values and update existing values.
- `strict` — report conflicts when the payload already exists.

The validation/import report includes planned create/update counts, duplicate warnings, alias/canonical conflicts, and stop-list blocks.


## Dictionary Migration Tool

Patch 28 adds a small stdlib-based CLI on top of the User Console API. The tool does not write to the database directly; it calls the same FastAPI endpoints that notebooks, bots, and scripts can use.

Install the governance API package and run:

```bash
poetry run skeinrank-migrate --help
```

The API URL defaults to `http://127.0.0.1:8010` and can be overridden with `--api-url` or `SKEINRANK_CONSOLE_API_URL`. When API auth is enabled, pass a bearer token with `--token` or `SKEINRANK_API_TOKEN`.

Validate a dictionary JSON without writing changes:

```bash
poetry run skeinrank-migrate validate ../../examples/migration/console_dictionary.example.json
```

Apply the dictionary after validation:

```bash
poetry run skeinrank-migrate apply ../../examples/migration/console_dictionary.example.json
```

Export a profile back to the same stable migration JSON shape:

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
- `/healthz` endpoint
- governance REST endpoints for profiles, terms, aliases, suggestions, profile/global stop lists, and snapshot export
- user-console dictionary validation, import, and export endpoints for migration workflows
- CRUD endpoints for updating/deleting profiles, canonical terms, and aliases
- local auth endpoints for login/logout/current user
- admin-only user management endpoints
- role-aware API permissions for Admin, Moderator, and Contributor
- Uvicorn launcher command
- Alembic migration wrapper for the API database URL
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

Stop-list targets are `alias`, `canonical`, and `both`. Active global and profile stop-list entries block matching direct CRUD mutations, suggestion creation, suggestion approval, Elasticsearch dry-run matches, and Elasticsearch enrichment job matches.

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

This patch intentionally does not add Celery/RabbitMQ yet. The API executes the
MVP job inline and records a durable job row so a future worker implementation
can reuse the same contract.

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
