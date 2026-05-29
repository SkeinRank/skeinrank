# Schema & Snapshots Tree UI

Patch 58D adds a read-heavy **Schema & Snapshots** workspace to the governance console.

The goal is to give operators and knowledge managers a compact way to inspect how runtime contexts, profiles, canonical terms, aliases, and snapshots fit together without turning the UI back into a broad manual CRUD console.

## Scope

The screen is intentionally read-heavy and uses existing governance API calls:

- `GET /v1/snapshots/summary`
- `GET /v1/governance/profiles`
- `GET /v1/governance/elasticsearch/bindings`
- `GET /v1/governance/profiles/{profile_name}/terms`

No new backend endpoint is introduced by this UI patch.

## Layout

The page keeps the existing snapshot release cockpit and adds a new workspace above it:

1. **Schema tree** — `binding → profile → category/slot → canonical term → aliases`.
2. **Snapshot timeline** — binding-scoped runtime snapshot status and drift.
3. **Detail panel** — selected node metadata, rollout state, and safe links to Playground/Integrations.

The tree intentionally avoids a force-directed graph. A tree + detail view scales better for thousands of terms, is easier to test, and matches the enterprise “read/audit/debug” UI direction.

## Safety

- No term, alias, stop-list, binding, or snapshot mutation is added.
- No enrichment job is started from the tree.
- No snapshot publish/rollback action is introduced.
- The screen links to existing pages for deeper workflows, such as Playground and Integrations.

## Intended usage

Use this screen to answer:

- Which profile owns this runtime binding?
- Which canonical terms and aliases are active in a selected profile?
- Which slots/categories contain the most aliases?
- Is the active snapshot aligned with the current profile?
- Should a user test a drifted binding in Playground before release?
