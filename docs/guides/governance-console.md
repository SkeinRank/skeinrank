# Governance console workflow

The governance layer is the control plane for terminology. It is composed of:

- `packages/skeinrank-governance` — SQLAlchemy models, Alembic migrations, admin CLI;
- `packages/skeinrank-governance-api` — FastAPI governance and runtime API;
- `packages/skeinrank-ui` — React/TypeScript governance console.

## Start the governance API

```bash
cd packages/skeinrank-governance-api
poetry install
poetry run python -m skeinrank_governance_api.migrations upgrade head
poetry run skeinrank-governance-api --reload
```

Health check:

```bash
curl http://127.0.0.1:8010/readyz
```

For local throwaway demos only, tables can be created on startup:

```bash
export SKEINRANK_GOVERNANCE_API_CREATE_TABLES=true
poetry run skeinrank-governance-api --reload
```

## Optional local auth bootstrap

```bash
export SKEINRANK_GOVERNANCE_API_AUTH_ENABLED=true
export SKEINRANK_GOVERNANCE_API_BOOTSTRAP_ADMIN=true
export SKEINRANK_GOVERNANCE_API_ADMIN_USERNAME=admin
export SKEINRANK_GOVERNANCE_API_ADMIN_PASSWORD='change-me'
```

## Start the UI

```bash
cd packages/skeinrank-ui
npm install
npm run dev
```

Open:

```text
http://127.0.0.1:5173
```

## Main workflow

A typical governance workflow looks like this:

```text
1. Create or import a terminology profile.
2. Add canonical terms and aliases.
3. Configure global/profile guardrails.
4. Review contributor suggestions.
5. Check evidence from Elasticsearch when a binding exists.
6. Export or publish a snapshot.
7. Bind the profile snapshot to runtime search or enrichment.
```

## Current UI scope

The UI currently covers:

- local login/logout session controls;
- current user and role display;
- role-aware actions for Admin, Moderator, and Contributor users;
- profile create/select/rename/describe/delete controls;
- canonical term create/edit/delete and lifecycle status controls;
- alias create/edit/delete controls;
- suggestions for aliases and canonical terms;
- approval/rejection flows;
- evidence refresh/display for review workflows;
- global and profile stop-list guardrails;
- Elasticsearch binding configuration;
- binding dry-runs and enrichment job history/details;
- API access management for personal tokens and service accounts;
- admin user management, roles, statuses, and token revocation;
- snapshot export and JSON download;
- light/dark/system theme toggle.

## Dictionary migration API

The console API supports migration-friendly dictionary workflows for notebooks, scripts, CI jobs, and bot integrations.

Important endpoints:

```text
POST /v1/console/dictionary/validate
POST /v1/console/dictionary/import
GET  /v1/console/dictionary/export/{profile_name}
```

The migration CLI `skeinrank-migrate` can validate, apply, and export dictionary JSON files without direct database access. New files should declare `schema_version: skeinrank.dictionary.v1`; legacy files without a schema version are treated as v1 for now. CLI validate/apply also accepts YAML input for human-edited GitOps dictionaries when PyYAML is available. See [`../concepts/dictionary-spec-v1.md`](../concepts/dictionary-spec-v1.md).

## API tokens and service accounts

The platform supports:

- personal API tokens for human users;
- service accounts for automation and CI/bot workflows;
- token revocation;
- role-aware migration scopes such as `migration:validate`, `migration:apply`, and `migration:export`.

Suspended or deactivated users cannot sign in or use personal API tokens. Service account tokens are controlled separately.
