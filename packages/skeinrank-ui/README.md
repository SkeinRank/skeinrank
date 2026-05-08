# skeinrank-ui

SkeinRank Governance Console UI.

This package is the first frontend layer for the governance platform. It reads users, profiles, terms, aliases, suggestions, and runtime snapshots from `packages/skeinrank-governance-api`, and provides MVP workflows for manual terminology governance with local auth and roles.

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
- Suggestions page for creating, filtering, approving, and rejecting alias/canonical term proposals
- Guardrails page for profile-scoped stop-list management
- Integrations page for manual Elasticsearch binding configs with shared-index validation
- searchable canonical term picker in manual suggestions with auto-filled slot and existing alias checks
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

Manual aliases are sent as approved entries with `confidence = 1.0`. Manual alias suggestions hide technical confidence/source fields, use existing canonical terms, auto-fill the slot, show existing aliases, keep reviewers on the current queue filter after approve/reject, and submit `source = manual` with `confidence = 1.0` internally. The Suggestions UI now also supports new canonical term proposals: contributors can switch the form to `New canonical term`, enter the term, slot, description, and context, and moderators/admins can approve it into an active canonical term. Discovery/import workflows can still use confidence and source metadata later. The UI now supports CRUD for users, profiles, canonical terms, aliases, suggestions, profile stop-list guardrails, and Elasticsearch binding configs through the governance API, including UI validation for shared-index bindings. Auth can be disabled for local development; when enabled, the UI sends bearer tokens and applies role-aware controls. Publish/rollback, Elasticsearch connection tests/dry-run jobs, advanced guardrail policies, model-based discovery, and realtime collaboration are intentionally left for follow-up patches.

## Checks

```bash
npm run typecheck
npm test -- --run
npm run build
```

## Elasticsearch discovery in Integrations

The Integrations page now supports optional Elasticsearch discovery. When the governance API has an Elasticsearch URL configured, the UI can:

- test the connection;
- show discovered indices;
- load mapping fields for the selected index;
- suggest text fields and discriminator fields while creating or editing bindings.

If Elasticsearch is not configured or unavailable, the page still works in manual mode and users can type index names and field names by hand.
