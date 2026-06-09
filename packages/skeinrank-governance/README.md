# skeinrank-governance

Postgres-ready terminology governance foundation for SkeinRank.

This package contains the SQLAlchemy models, Alembic migrations, and local admin CLI used by the SkeinRank control plane. It stores terminology profiles, canonical terms, aliases, stop lists, suggestions, Elasticsearch bindings, snapshots, audit history, users, tokens, service accounts, review metadata, and agent run tracking records.

## Role in the architecture

Runtime extraction stays fast and deterministic:

```text
Postgres governance store -> published snapshot JSON -> in-memory matcher -> API / CLI / Elasticsearch enrichment
```

The database is the source of truth for editing and publishing terminology. Runtime services should consume exported or pinned snapshots instead of querying Postgres for every request.

## Install and test

```bash
cd packages/skeinrank-governance
poetry install
poetry run pytest -q
```

## Database setup

The default `alembic.ini` uses a local SQLite file for quick smoke tests:

```bash
poetry run alembic upgrade head
```

For PostgreSQL, provide the database URL before running migrations:

```bash
export SKEINRANK_GOVERNANCE_DATABASE_URL='postgresql+psycopg://user:password@localhost:5432/skeinrank'
poetry run alembic upgrade head
```

When migrations are executed through the governance API wrapper, `SKEINRANK_GOVERNANCE_API_DATABASE_URL` takes precedence over `SKEINRANK_GOVERNANCE_DATABASE_URL` so the migration target matches the HTTP service configuration.

The package does not pin a PostgreSQL driver directly. Install `psycopg` or the driver required by your deployment environment.

## Core schema surfaces

Primary terminology tables:

- `terminology_profiles`
- `canonical_terms`
- `term_aliases`
- `profile_snapshots`
- `audit_events`

Governance and access-control tables:

- `governance_users`
- `governance_auth_tokens`
- `governance_service_accounts`
- `governance_api_tokens`
- `governance_suggestions`

Operational and runtime-context tables:

- `governance_stop_list_entries`
- `governance_global_stop_list_entries`
- `elasticsearch_bindings`
- `elasticsearch_enrichment_jobs`
- `governance_conflict_reviews`
- `governance_ambiguous_aliases`
- `governance_ambiguous_alias_candidates`
- `governance_binding_policies`

Agent tracking tables:

- `agent_runs`
- `agent_document_visits`
- `agent_candidate_observations`
- `agent_evidence_windows`
- `agent_llm_reviews`
- `agent_proposal_attempts`

## Integrity rules

The schema enforces the invariants that keep runtime snapshots safe:

- profile names are unique after normalization;
- canonical terms are unique per profile after normalization;
- aliases are unique per profile after normalization;
- alias collisions such as `pg -> postgresql` and `pg -> payment-gateway` are rejected at the database layer;
- term, alias, snapshot, suggestion, job, and agent-run statuses are constrained;
- governance user roles are constrained to `admin`, `moderator`, and `contributor`;
- governance user statuses are constrained to `active`, `suspended`, and `deactivated`;
- login tokens, personal API tokens, and service-account API tokens are stored as hashes, not plaintext bearer tokens;
- service account roles are constrained to `admin`, `moderator`, and `contributor`;
- API tokens must belong to exactly one owner: either one user or one service account;
- suggestions are constrained to `pending`, `approved`, and `rejected` review states;
- suggestion source types are constrained to `human`, `agent`, `cli`, `api`, `job`, and `import`.

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

## Admin CLI

`skeinrank-admin` supports local terminology editing and snapshot export workflows.

Initialize a local SQLite database:

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

## Stop lists

The governance schema includes profile-scoped and global stop-list entries for terminology guardrails. A stop-list entry can block aliases, canonical terms, or both. Profile-scoped entries protect one terminology profile, while global entries block organization-wide noise across every profile.

Stop lists are used by the governance API to reject blocked direct edits, blocked suggestions, and approvals that became blocked after the suggestion was created. Elasticsearch dry-runs and enrichment jobs also exclude active aliases or canonical terms blocked by profile or global stop-list entries.

## Elasticsearch bindings and enrichment jobs

`ElasticsearchBinding` connects one terminology profile to one Elasticsearch index or index pattern. It stores source text fields, the target enrichment field, optional discriminator filters such as `team = infra`, optional time-window filters such as `created_at` plus a day window, and the write strategy.

Bindings are configuration records. They do not open an Elasticsearch connection from this package. The governance API and provider packages use the saved binding contract for dry-run previews and write-mode enrichment jobs.

The default write strategy is `reindex_alias_swap`, which is safer for production workflows than mutating the live index directly. `in_place` remains available for sandbox and local validation scenarios. Job records store status, source index, target index, alias name, counters, result JSON, error messages, rollout metadata, and cancellation state.

Supported job lifecycle values include queued, running, cancel requested, cancelled, succeeded, and failed states so workers can stop long-running jobs safely.

## Evidence snapshots

Suggestions can store bounded Elasticsearch evidence snapshots. A saved evidence snapshot records binding metadata, highlighted snippets, warnings, the actor who checked evidence, and the check timestamp. The snapshot is stored as JSON so review UI can show the evidence that supported a proposed alias or canonical term without rerunning Elasticsearch automatically.

## Term tags and conflict review

Canonical terms can carry optional `tags`. Tags are normalized, deduplicated facets such as `infra`, `backend`, or `storage`. They complement the primary `slot` without changing runtime snapshot behavior.

`GovernanceConflictReview` stores persisted review metadata for computed terminology conflicts. Conflict scanners remain read-only; review rows track fingerprint, severity, review status, reviewer, note, and compact conflict details.

`GovernanceAmbiguousAlias` and `GovernanceAmbiguousAliasCandidate` record multi-interpretation alias surfaces such as `pg`. These rows are review metadata and do not mutate active aliases directly.

`GovernanceBindingPolicy` stores optional policy metadata for one `ElasticsearchBinding`. It keeps runtime-context constraints such as preferred slots, allowed tags, denied slots, and context-specific surface rules close to the binding without changing the terminology profile itself.

## Coverage framework

The governance package models the state used by the coverage framework. For end-to-end examples, see `docs/concepts/coverage-framework.md`, `docs/guides/coverage-framework.md`, and `examples/coverage-framework/` from the repository root.

## Agent run tracking

The governance schema stores durable records for agent-backed terminology discovery workflows:

- `AgentRun` stores one row per workflow run, including `run_id`, lifecycle status, trigger type, optional profile and binding scope, model/prompt metadata, report/artifact URIs, summary JSON, and timestamps.
- `AgentDocumentVisit` links source documents to agent runs and stores `content_hash`, `processing_context_hash`, `visit_status`, and `should_scan`.
- `AgentCandidateObservation`, `AgentEvidenceWindow`, `AgentLlmReview`, and `AgentProposalAttempt` connect candidate observations, evidence windows, model judgments, validation responses, idempotency keys, and optional governance suggestion links.

These tables support proposal-first automation: agents can collect evidence and submit reviewable proposals while humans retain approval control.
