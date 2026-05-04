# skeinrank-governance-api

FastAPI control-plane API skeleton for SkeinRank terminology governance.

This package is the HTTP layer that will later power the SkeinRank governance UI. It sits above `skeinrank-governance`, which owns SQLAlchemy models, Alembic migrations, and the admin CLI.

## Role in the architecture

```text
Postgres governance store
  -> skeinrank-governance SQLAlchemy models
  -> skeinrank-governance-api HTTP control plane
  -> future skeinrank-ui
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

Production deployments should use Alembic migrations from `packages/skeinrank-governance` instead.

## Current scope

This is a skeleton package. It currently provides:

- FastAPI app factory
- environment-based configuration
- SQLAlchemy session dependency
- `/healthz` endpoint
- Uvicorn launcher command
- tests for app creation, health checks, and DB dependency wiring

Future patches will add REST endpoints for profiles, terms, aliases, suggestions, and snapshot publishing.
