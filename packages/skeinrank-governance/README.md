# skeinrank-governance

Postgres-ready terminology governance foundation for SkeinRank.

This package contains SQLAlchemy models and Alembic migrations for the control-plane layer where teams manage canonical terms, aliases, suggestions, snapshots, audit history, users, auth tokens, and roles.

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
- `governance_users`
- `governance_auth_tokens`
- `governance_suggestions`

Important constraints:

- profile names are unique after normalization
- canonical terms are unique per profile after normalization
- aliases are unique per profile after normalization
- alias collisions such as `pg -> postgresql` and `pg -> payment-gateway` are rejected at the database layer
- term, alias, and snapshot statuses are constrained
- governance user roles are constrained to `admin`, `moderator`, and `contributor`
- auth tokens are stored as hashes, not plaintext bearer tokens
- suggestions are constrained to `pending`, `approved`, and `rejected` review states
- suggestion types are constrained to `alias` and `canonical_term`

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

When migrations are run through the governance API wrapper, `SKEINRANK_GOVERNANCE_API_DATABASE_URL` takes precedence over `SKEINRANK_GOVERNANCE_DATABASE_URL` so the migration target matches the HTTP service configuration.

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


## Admin CLI preview

`skeinrank-governance` now includes a small `skeinrank-admin` CLI for local terminology governance workflows.

Initialize a local SQLite database for development:

```bash
cd packages/skeinrank-governance
poetry run skeinrank-admin db init
```

Create a profile, add terms and aliases, and export a runtime snapshot:

```bash
poetry run skeinrank-admin profile create default_it --description "Default IT terms"
poetry run skeinrank-admin term add default_it kubernetes --slot TOOL
poetry run skeinrank-admin alias add default_it kubernetes k8s
poetry run skeinrank-admin alias add default_it kubernetes kube
poetry run skeinrank-admin term list default_it
poetry run skeinrank-admin snapshot export default_it --out /tmp/default_it.json --snapshot-version default_it@v1
```

The exported JSON is compatible with `skeinrank-core` runtime commands:

```bash
cd ../skeinrank-core
poetry run skeinrank-validate-profile /tmp/default_it.json
poetry run skeinrank-extract --text "k8s timeout" --profile-file /tmp/default_it.json --compact
```

By default the CLI uses `sqlite:///skeinrank_governance.db`. Override it with:

```bash
export SKEINRANK_GOVERNANCE_DATABASE_URL='postgresql+psycopg://user:password@localhost:5432/skeinrank'
```


## Current scope

This is a platform-foundation package. It now includes basic admin CLI commands for local terminology editing and snapshot export. It does not yet include:

- suggestions UI
- full approval discussion threads
- UI
- background enrichment jobs
- snapshot publish/archive lifecycle beyond JSON export

Those pieces are planned for later platform patches.


## Governance stop lists

The governance schema includes profile-scoped stop-list entries for terminology guardrails. A stop-list entry can block aliases, canonical terms, or both. This is intentionally profile-scoped for the MVP because a value that is too generic in one corpus can be valid in another.

Stop lists are used by the governance API to reject blocked direct edits, blocked suggestions, and approvals that became blocked after the suggestion was created.


## Elasticsearch bindings

The governance schema includes saved Elasticsearch enrichment bindings. A binding is a configuration object that connects one terminology profile to one Elasticsearch index or index pattern, the source text fields to inspect, an enrichment target field, an optional metadata filter such as `team = infra`, and an enrichment write strategy.

Bindings are configuration-only in this package. They do not open an Elasticsearch connection or write to an index. Future provider/job patches can read these saved bindings to run dry-run or write-mode enrichment jobs. The default write strategy is `reindex_alias_swap`, which is safer for production workflows than mutating the live index directly.
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

