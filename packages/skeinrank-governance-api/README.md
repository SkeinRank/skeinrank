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

`SKEINRANK_GOVERNANCE_API_CREATE_TABLES=true` remains available for lightweight demos/tests, but Alembic is the preferred operational path before adding users, roles, suggestions, snapshot history, and bindings.

## Current scope

This package currently provides:

- FastAPI app factory
- environment-based configuration
- SQLAlchemy session dependency
- `/healthz` endpoint
- governance REST endpoints for profiles, terms, aliases, and snapshot export
- CRUD endpoints for updating/deleting profiles, canonical terms, and aliases
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

Snapshot export:

```bash
curl -X POST http://127.0.0.1:8010/v1/governance/profiles/default_it/snapshot/export \
  -H "Content-Type: application/json" \
  -d '{"snapshot_version":"default_it@v1","description":"Runtime snapshot exported from the governance API"}'
```

The response is a runtime-compatible profile snapshot that can be passed to `skeinrank-core` through `--profile-file` or `load_attribute_profile(...)`.

Future patches will add snapshot publishing lifecycle, suggestions, approval flow, authentication, users, and roles.
