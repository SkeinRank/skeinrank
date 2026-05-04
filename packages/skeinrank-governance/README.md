# skeinrank-governance

Postgres-ready terminology governance foundation for SkeinRank.

This package contains SQLAlchemy models and an Alembic migration skeleton for the future control-plane layer where teams will manage canonical terms, aliases, snapshots, and audit history.

## Role in the architecture

Runtime extraction should stay fast and deterministic:

```text
Postgres governance store -> published snapshot JSON -> in-memory matcher -> API / CLI / Elasticsearch enrichment
```

The database is the source of truth for editing and publishing terminology. The hot path still loads a versioned snapshot and does not query Postgres per request.

## Schema

Initial tables:

- `terminology_profiles`
- `canonical_terms`
- `term_aliases`
- `profile_snapshots`
- `audit_events`

Important constraints:

- profile names are unique after normalization
- canonical terms are unique per profile after normalization
- aliases are unique per profile after normalization
- alias collisions such as `pg -> postgresql` and `pg -> payment-gateway` are rejected at the database layer
- term, alias, and snapshot statuses are constrained

## Local development

```bash
poetry install
poetry run pytest -q
```

## Alembic smoke test

The default `alembic.ini` uses a local SQLite file for quick smoke tests.

```bash
poetry run alembic upgrade head
```

For PostgreSQL, set:

```bash
export SKEINRANK_GOVERNANCE_DATABASE_URL='postgresql+psycopg://user:password@localhost:5432/skeinrank'
poetry run alembic upgrade head
```

A PostgreSQL driver is intentionally not pinned in this first package skeleton. Add `psycopg` or another driver in the deployment environment where the governance store is used.

## Minimal Python usage

```python
from skeinrank_governance import (
    CanonicalTerm,
    TermAlias,
    TerminologyProfile,
    create_all,
    create_governance_engine,
    create_session_factory,
)

engine = create_governance_engine("sqlite+pysqlite:///:memory:")
create_all(engine)
Session = create_session_factory(engine)

with Session() as session:
    profile = TerminologyProfile(name="default_it")
    term = CanonicalTerm(profile=profile, canonical_value="kubernetes", slot="TOOL")
    alias = TermAlias(profile=profile, term=term, alias_value="k8s")
    session.add_all([profile, term, alias])
    session.commit()
```

## Current scope

This is a platform-foundation package only. It does not yet include:

- admin CLI commands
- snapshot export from Postgres
- approval workflows
- UI
- background enrichment jobs

Those pieces are planned for later platform patches.
