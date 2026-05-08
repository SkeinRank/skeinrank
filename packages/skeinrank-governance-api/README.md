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
- governance REST endpoints for profiles, terms, aliases, suggestions, stop lists, and snapshot export
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

Stop-list targets are `alias`, `canonical`, and `both`. Active stop-list entries block matching direct CRUD mutations, suggestion creation, and suggestion approval.

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
