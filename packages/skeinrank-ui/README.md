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
- admin-only Users page for local user CRUD, role assignment, account status controls, and user token revocation
- API Access page for personal API tokens and admin-managed service accounts
- role-aware controls for Admin, Moderator, and Contributor users
- Suggestions page for creating, filtering, approving, rejecting, and evidence-checking alias/canonical term proposals
- Guardrails page for global and profile-scoped stop-list management
- Integrations page for manual Elasticsearch binding configs, shared-index validation, time-window filters, dry-run previews, and enrichment job status
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

Manual aliases are sent as approved entries with `confidence = 1.0`. Manual alias suggestions hide technical confidence/source fields, use existing canonical terms, auto-fill the slot, show existing aliases, keep reviewers on the current queue filter after approve/reject, and submit `source = manual` with `confidence = 1.0` internally. The Suggestions UI now also supports new canonical term proposals: contributors can switch the form to `New canonical term`, enter the term, slot, description, and context, and moderators/admins can approve it into an active canonical term. Discovery/import workflows can still use confidence and source metadata later. The UI now supports CRUD for users, profiles, canonical terms, aliases, suggestions, global stop-list guardrails, profile stop-list guardrails, Elasticsearch binding configs, dry-run previews, evidence checks, enrichment job status, personal API tokens, and service accounts through the governance API, including UI validation for shared-index bindings. Auth can be disabled for local development; when enabled, the UI sends bearer tokens and applies role-aware controls. Publish/rollback, background workers, advanced guardrail policies, model-based discovery, and realtime collaboration are intentionally left for follow-up patches.

## Evidence UI

The Terms page includes an explicit Evidence check panel for the selected canonical term. Users can choose one of the profile's Elasticsearch bindings, search the canonical value or an alias, and inspect bounded snippets with highlighted matches. Alias rows also include a shortcut to check evidence for that alias.

The Suggestions page shows saved evidence snapshots from the backend and lets authorized users refresh evidence for pending suggestions before approve/reject. Evidence checks are never run automatically for every suggestion row; each check is a bounded backend request through the configured binding.

## API Access

The Users page lets admins set user status to `active`, `suspended`, or `deactivated`, and revoke all personal API tokens for a selected user. Suspended/deactivated users cannot sign in or use personal API tokens until reactivated; service accounts remain managed separately from human user status.

The API Access page lets signed-in users create and revoke personal API tokens for notebooks, scripts, and the `skeinrank-migrate` CLI. Tokens are displayed only once after creation; after that the UI only shows token metadata such as prefix, scopes, expiration, last-used time, and revoked/active status.

Admins also see the Service accounts area. They can:

- create service accounts for bots, CI jobs, and dictionary migration automation;
- suspend or reactivate service accounts;
- create service account tokens;
- revoke service account tokens.

Service account tokens are also displayed only once. Suspended service accounts cannot issue new tokens from the UI, and backend auth rejects tokens for inactive service accounts.

Supported migration scopes:

```text
migration:validate
migration:apply
migration:export
```

User roles are still enforced by the governance API. A token scope grants API-token permission, but it does not bypass role checks.

## Checks

```bash
npm run typecheck
npm test -- --run
npm run build
```

## Global stop lists

The Guardrails page now supports global stop-list management on top of the profile-scoped stop lists. Global entries are inherited by every profile and are shown as a read-only `Global` layer above the selected profile's local stop list.

Admins and moderators can:

- create global stop-list entries;
- edit global target/reason/active status;
- delete global entries;
- manage profile-local stop-list entries below the inherited global layer.

Contributors can inspect both global and profile stop lists in read-only mode. When adding a profile-local entry, the UI warns and blocks duplicate local entries if the same value is already covered by an active global stop-list entry.

## Elasticsearch discovery in Integrations

The Integrations page now supports optional Elasticsearch discovery. When the governance API has an Elasticsearch URL configured, the UI can:

- test the connection;
- show discovered indices;
- load mapping fields for the selected index;
- suggest text fields and discriminator fields while creating or editing bindings.

If Elasticsearch is not configured or unavailable, the page still works in manual mode and users can type index names and field names by hand.

## Elasticsearch binding dry-run

The Integrations page can run a read-only dry-run for the selected binding. The preview shows sample documents, matched aliases, canonical values, and the JSON payload that would be written to the configured target field.

Dry-run is safe for production validation because it does not write to Elasticsearch. It only calls the governance API dry-run endpoint and displays the returned preview.

## Elasticsearch enrichment jobs

The Integrations page can now run and inspect enrichment jobs for the selected
Elasticsearch binding when Patch 25g backend endpoints are available.

Admins and moderators can start a job from the selected binding details panel.
The form supports:

- `Job target index`;
- `Job alias name`;
- `Max documents`;
- binding `write_strategy` selection during create/edit.

The job panel shows job history and selected job details: status, write
strategy, source index, target index, alias name, requested user, document
counters, error message, and result JSON. Contributors can inspect jobs in
read-only mode but cannot run them. Admins and moderators can also request safe cancellation for queued/running jobs; running chunked jobs move through `cancel_requested` before becoming `cancelled`.

The UI uses these governance API endpoints:

```text
POST /v1/governance/elasticsearch/bindings/{binding_id}/jobs
GET /v1/governance/elasticsearch/jobs?binding_id=...
GET /v1/governance/elasticsearch/jobs/{job_id}
POST /v1/governance/elasticsearch/jobs/{job_id}/cancel
```

## Elasticsearch enrichment time filters

The Integrations page can now store optional document time filters on a binding:

- `Timestamp field`, for example `@timestamp`, `created_at`, or `updated_at`;
- `Time window`: all documents, last 30 days, last 1 year, last 5 years, or custom days.

Dry-run previews and write-mode jobs use the same binding-level time filter.
There is no product-facing sort selector; the backend uses newest-first ordering
when a timestamp window is configured. `Max documents` remains a safety limit
inside the selected window.

The current backend executor is synchronous. Future worker-based polling can
reuse the same UI contract.

## Patch 39 — Rollout metadata in job details

The Integrations job details panel now surfaces rollout metadata for
`reindex_alias_swap` jobs when the API includes `result_json.rollout`.

The panel shows:

- rollout status;
- whether alias swap completed;
- previous alias indices;
- new alias indices;
- rollback candidate index;
- swap timestamp;
- cleanup and rollback hints.

Patch 40 adds a `Rollback alias` action for admins/moderators when rollback is
available. The UI shows a confirmation prompt, calls the safe rollback endpoint,
and updates the rollout panel with completed rollback metadata.
