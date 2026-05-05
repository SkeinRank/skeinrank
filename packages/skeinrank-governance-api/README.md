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

Initialize the database through the governance CLI first:

```bash
cd ../skeinrank-governance
poetry run skeinrank-admin db init
```

Then start the API:

```bash
cd ../skeinrank-governance-api
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

The API reads database configuration from env vars:

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

Production deployments should use Alembic migrations from `packages/skeinrank-governance` instead.

## Current scope

This package currently provides:

- FastAPI app factory
- environment-based configuration
- SQLAlchemy session dependency
- `/healthz` endpoint
- governance REST endpoints for profiles, terms, aliases, and snapshot export
- Uvicorn launcher command
- tests for app creation, health checks, DB dependency wiring, and governance routes

## Governance REST endpoints

Profiles:

```bash
curl http://127.0.0.1:8010/v1/governance/profiles

curl -X POST http://127.0.0.1:8010/v1/governance/profiles \
  -H "Content-Type: application/json" \
  -d '{"name":"default_it","description":"Default IT terms"}'
```

Canonical terms:

```bash
curl -X POST http://127.0.0.1:8010/v1/governance/profiles/default_it/terms \
  -H "Content-Type: application/json" \
  -d '{"canonical_value":"kubernetes","slot":"TOOL"}'

curl http://127.0.0.1:8010/v1/governance/profiles/default_it/terms
```

Aliases:

```bash
curl -X POST http://127.0.0.1:8010/v1/governance/profiles/default_it/terms/kubernetes/aliases \
  -H "Content-Type: application/json" \
  -d '{"alias_value":"k8s","confidence":0.97}'
```

Snapshot export:

```bash
curl -X POST http://127.0.0.1:8010/v1/governance/profiles/default_it/snapshot/export \
  -H "Content-Type: application/json" \
  -d '{"snapshot_version":"default_it@v1","description":"Runtime snapshot exported from the governance API"}'
```

The response is a runtime-compatible profile snapshot that can be passed to `skeinrank-core` through `--profile-file` or `load_attribute_profile(...)`.

Future patches will add snapshot publishing lifecycle, suggestions, approval flow, and authentication.
