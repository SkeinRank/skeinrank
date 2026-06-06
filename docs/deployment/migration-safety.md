# Migration safety guide

SkeinRank uses Alembic migrations for the Governance API database. Production-like deployments should treat migrations as an explicit operational step, even when Docker Compose runs the one-shot `governance-migrate` service automatically.

## Safety model

The migration safety model has three operator-facing checks:

```text
python -m skeinrank_governance_api.migrations check
GET /schema/health
GET /readyz
```

`GET /schema/health` is the most direct schema check. It verifies:

- whether `alembic_version` exists;
- current database revision;
- expected Alembic head revision;
- whether current revision matches head;
- whether multiple Alembic heads exist;
- which SQLAlchemy metadata tables are missing.

`GET /readyz` remains the deployment gate. It becomes degraded when the schema is not safe for the API to serve production-like traffic.

## Local CLI check

```bash
cd packages/skeinrank-governance-api
poetry run python -m skeinrank_governance_api.migrations upgrade head
poetry run python -m skeinrank_governance_api.migrations check
```

Expected successful output includes:

```text
schema_ok=true
current_matches_head=true
multiple_heads=false
missing_tables=
```

## Compose schema check

For production-style Compose:

```bash
make prod-schema-check
```

or directly:

```bash
docker compose --env-file .env -f docker-compose.prod.yml --profile ops run --rm governance-schema-check
```

## Migration order for upgrades

Use this order:

```text
1. validate env
2. validate compose config
3. export backup
4. check current schema
5. run upgrade / one-shot migrations
6. check schema again
7. run smoke test
```

`make prod-upgrade` follows this order.

## Multiple heads

If schema health reports `multiple_heads=true`, stop the upgrade. This indicates Alembic history needs to be reconciled before production use.

Do not manually edit `alembic_version` as a workaround. Fix the migration graph and rerun:

```bash
poetry run python -m skeinrank_governance_api.migrations check
```

## Missing tables

If schema health reports missing tables:

1. confirm the service is pointed at the expected DB URL;
2. run migrations to head;
3. rerun schema health;
4. only then start the API/worker.

## Create-tables mode

`SKEINRANK_GOVERNANCE_API_CREATE_TABLES=true` is useful for early development, but production-like deployments should use Alembic migrations. A DB created only through metadata `create_all` can be missing `alembic_version`, which makes readiness degrade.
