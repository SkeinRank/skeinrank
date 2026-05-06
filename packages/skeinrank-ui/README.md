# skeinrank-ui

SkeinRank Governance Console UI.

This package is the first frontend layer for the governance platform. It reads users, profiles, terms, aliases, and runtime snapshots from `packages/skeinrank-governance-api`, and provides MVP workflows for manual terminology governance with local auth and roles.

## Stack

- React
- TypeScript
- Vite
- shadcn-style local UI components
- Tailwind CSS
- TanStack Query
- TanStack Table
- Light/dark/system theme toggle

## Run locally

Start the governance API first:

```bash
cd packages/skeinrank-governance-api
poetry run python -m skeinrank_governance_api.migrations upgrade head

# Optional protected local run:
export SKEINRANK_GOVERNANCE_API_AUTH_ENABLED=true
export SKEINRANK_GOVERNANCE_API_BOOTSTRAP_ADMIN=true
export SKEINRANK_GOVERNANCE_API_ADMIN_USERNAME=admin
export SKEINRANK_GOVERNANCE_API_ADMIN_PASSWORD='change-me'

poetry run skeinrank-governance-api --reload
```

Then start the UI:

```bash
cd packages/skeinrank-ui
npm install
npm run dev
```

Open:

```text
http://127.0.0.1:5173
```

If the API is not running on the default URL, set:

```bash
export VITE_SKEINRANK_GOVERNANCE_API_URL=http://127.0.0.1:8010
```

## Current scope

The governance console currently includes:

- app shell with local login/logout session controls
- current user and role display
- admin-only Users page for local user CRUD and role assignment
- role-aware controls for Admin, Moderator, and Contributor users
- profile CRUD controls: create, select, rename, describe, and delete profiles
- terms table with row selection
- create, edit, and delete canonical terms
- term details panel with lifecycle status controls
- create, edit, and delete aliases with manual confidence hidden
- manual alias status choices limited to `active`, `deprecated`, and `disabled`; review-only statuses stay reserved for future suggestions and validation flags
- aliases display
- draft snapshot export and JSON download panel
- light/dark/system theme toggle with local persistence
- API state management through TanStack Query

Manual aliases are sent as approved entries with `confidence = 1.0`; model confidence will be shown later in the suggestions/approval workflow. The UI now supports CRUD for users, profiles, canonical terms, and aliases through the governance API. Auth can be disabled for local development; when enabled, the UI sends bearer tokens and applies role-aware controls. Approval flow, publish/rollback, Elasticsearch bindings, and realtime collaboration are intentionally left for follow-up patches.

## Checks

```bash
npm run typecheck
npm test -- --run
npm run build
```
