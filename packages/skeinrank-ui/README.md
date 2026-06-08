# skeinrank-ui

SkeinRank Governance Console UI.

This package is the React frontend for the SkeinRank control plane. It connects to `packages/skeinrank-governance-api` and provides review-first workflows for terminology governance, runtime snapshot inspection, search playground validation, API access management, Elasticsearch bindings, and operator diagnostics.

## Stack

- React
- TypeScript
- Vite
- local shadcn-style UI components
- Tailwind CSS
- TanStack Query
- TanStack Table
- light/dark/system theme toggle

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

## Product surfaces

The primary navigation is intentionally limited to three daily product surfaces:

```text
Playground
AI Inbox
Schema & Snapshots
```

Low-level pages are still available below the primary workflow:

```text
Settings: API Access, Users, Integrations
Developer Cockpit: Dashboard, Terms, Suggestions, Guardrails
```

This keeps the UI aligned with the headless/API-first product direction. Reviewers and knowledge managers see the workflow they need, while developers still have access to manual tools for local testing and pilot debugging.

## Current capabilities

The governance console includes:

- app shell with local login/logout session controls;
- current user and role display;
- admin-only Users page for local user CRUD, role assignment, account status controls, and user token revocation;
- API Access page for personal API tokens and admin-managed service accounts;
- role-aware controls for Admin, Moderator, and Contributor users;
- AI Inbox page for human-in-the-loop review of agent proposals with risk, validation findings, apply-policy, evidence snippets, source payload, and approve/reject actions;
- Search Playground page with single-query preview, explicit search, and split-screen snapshot compare across two binding-backed runtime contexts;
- Schema & Snapshots page with a read-heavy tree and detail layout for bindings, profiles, slots/categories, canonical terms, aliases, and runtime snapshot drift;
- global degraded-state banner backed by `GET /v1/ops/alerts/report`;
- Suggestions page for manual proposal creation, filtering, approving, rejecting, and evidence-checking alias/canonical term proposals;
- Guardrails page for global and profile-scoped stop-list management;
- Integrations page for manual Elasticsearch binding configs, shared-index validation, time-window filters, dry-run previews, and enrichment job status;
- searchable canonical term picker in manual suggestions with auto-filled slot and existing alias checks;
- profile CRUD controls: create, select, rename, describe, and delete profiles;
- canonical term and alias tables with lifecycle status controls;
- draft snapshot export and JSON download panel;
- light/dark/system theme toggle with local persistence;
- API state management through TanStack Query.

## Review-first proposal workflow

The AI Inbox is the review-first page for agent-submitted proposals. It uses the existing suggestions API, but it is intentionally not a manual CRUD editor. Moderators and admins review pending cards, inspect risk, apply-policy, validation findings, evidence snapshots, source metadata, and audit context, then call the existing approve/reject endpoints. Contributors can inspect the queue in read-only mode.

Manual aliases are submitted as approved entries with `confidence = 1.0`. Manual alias suggestions hide technical confidence/source fields, use existing canonical terms, auto-fill the slot, show existing aliases, keep reviewers on the current queue filter after approve/reject, and submit `source = manual` internally.

The Suggestions UI also supports new canonical term proposals. Contributors can switch the form to `New canonical term`, enter the term, slot, description, and context, and moderators/admins can approve it into an active canonical term.

## Evidence UI

The Terms page includes an explicit Evidence check panel for the selected canonical term. Users can choose one of the profile's Elasticsearch bindings, search the canonical value or an alias, and inspect bounded snippets with highlighted matches. Alias rows also include a shortcut to check evidence for that alias.

The AI Inbox shows saved evidence snapshots as review context. The Suggestions page still lets authorized users refresh evidence for pending suggestions before approve/reject. Evidence checks are never run automatically for every suggestion row; each check is a bounded backend request through the configured binding.

## API Access

The Users page lets admins set user status to `active`, `suspended`, or `deactivated`, and revoke all personal API tokens for a selected user. Suspended or deactivated users cannot sign in or use personal API tokens until reactivated; service accounts remain managed separately from human user status.

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

## Global stop lists

The Guardrails page supports global stop-list management on top of profile-scoped stop lists. Global entries are inherited by every profile and are shown as a read-only `Global` layer above the selected profile's local stop list.

Admins and moderators can create, edit, and delete global entries, and manage profile-local stop-list entries below the inherited global layer. Contributors can inspect both global and profile stop lists in read-only mode. When adding a profile-local entry, the UI warns and blocks duplicate local entries if the same value is already covered by an active global stop-list entry.

## Elasticsearch discovery in Integrations

The Integrations page supports optional Elasticsearch discovery. When the governance API has an Elasticsearch URL configured, the UI can:

- test the connection;
- show discovered indices;
- load mapping fields for the selected index;
- suggest text fields and discriminator fields while creating or editing bindings.

If Elasticsearch is not configured or unavailable, the page still works in manual mode and users can type index names and field names by hand.

## Elasticsearch binding dry-run

The Integrations page can run a read-only dry-run for the selected binding. The preview shows sample documents, matched aliases, canonical values, and the JSON payload that would be written to the configured target field.

Dry-run is safe for production validation because it does not write to Elasticsearch. It only calls the governance API dry-run endpoint and displays the returned preview.

## Elasticsearch enrichment jobs

The Integrations page can run and inspect enrichment jobs for the selected Elasticsearch binding. Admins and moderators can start a job from the selected binding details panel.

The form supports:

- `Job target index`;
- `Job alias name`;
- `Max documents`;
- binding `write_strategy` selection during create/edit.

The job panel shows job history and selected job details: status, write strategy, source index, target index, alias name, requested user, document counters, error message, result JSON, and rollout metadata. Contributors can inspect jobs in read-only mode but cannot run them. Admins and moderators can also request safe cancellation for queued/running jobs; running chunked jobs move through `cancel_requested` before becoming `cancelled`.

The UI uses these governance API endpoints:

```text
POST /v1/governance/elasticsearch/bindings/{binding_id}/jobs
GET /v1/governance/elasticsearch/jobs?binding_id=...
GET /v1/governance/elasticsearch/jobs/{job_id}
POST /v1/governance/elasticsearch/jobs/{job_id}/cancel
GET /v1/governance/profiles/{profile_name}/suggestions?status=pending
POST /v1/governance/profiles/{profile_name}/suggestions/{suggestion_id}/approve
POST /v1/governance/profiles/{profile_name}/suggestions/{suggestion_id}/reject
```

## Elasticsearch enrichment time filters

The Integrations page can store optional document time filters on a binding:

- `Timestamp field`, for example `@timestamp`, `created_at`, or `updated_at`;
- `Time window`: all documents, last 30 days, last 1 year, last 5 years, or custom days.

Dry-run previews and write-mode jobs use the same binding-level time filter. There is no product-facing sort selector; the backend uses newest-first ordering when a timestamp window is configured. `Max documents` remains a safety limit inside the selected window.

The current backend executor is synchronous. Worker-based polling can reuse the same UI contract.

## Rollout metadata and rollback action

The Integrations job details panel surfaces rollout metadata for `reindex_alias_swap` jobs when the API includes `result_json.rollout`.

The panel shows:

- rollout status;
- whether alias swap completed;
- previous alias indices;
- new alias indices;
- rollback candidate index;
- swap timestamp;
- cleanup and rollback hints.

When rollback is available, admins and moderators can use the `Rollback alias` action. The UI shows a confirmation prompt, calls the safe rollback endpoint, and updates the rollout panel with completed rollback metadata.

## Search Playground snapshot compare

The Search Playground supports a safe split-screen compare mode. Users pick two existing Elasticsearch bindings, enter one query, and the UI calls `POST /v1/query/plan` for each binding. This compares active/staging or prod/draft runtime behavior without introducing a new backend endpoint or mutating snapshots.

## Schema & Snapshots tree

The Snapshots section includes a read-only Schema & Snapshots workspace. Users can inspect `binding → profile → category/slot → canonical term → aliases` in a tree and select any node to see details in the right panel. A companion snapshot timeline mode shows active/pending versions, drift, alias counts, and rollback availability. The UI uses existing profile, terms, binding, and snapshot summary endpoints and does not add manual schema editing or rollout buttons.

## Degraded banners and read-only compare mode

The shell displays a compact degraded-state banner when `GET /v1/ops/alerts/report` returns alert events. This is read-only and does not send webhooks or mutate runtime state. Empty states in the Inbox and Playground explain the next safe setup step instead of appearing as blank screens.

Compare mode is intentionally read-only: it does not run enrichment jobs, publish snapshots, apply proposals, or write to Elasticsearch. The separate `Run search` button remains the only path that calls runtime search.

## Read-only legacy/admin cockpit lockdown

Legacy/admin cockpit pages remain reachable for inspection and local debugging, but write controls are disabled by default. This prevents direct UI changes to terminology, bindings, guardrails, or enrichment state from bypassing the proposal → validation → snapshot/GitOps workflow.

For local developer testing only, enable the legacy write bypass explicitly:

```bash
VITE_SKEINRANK_ENABLE_LEGACY_WRITE_TOOLS=true npm run dev
```

Production, demo, and enterprise pilot environments should leave this flag disabled.

## Checks

```bash
npm run typecheck
npm test -- --run
npm run build
```
