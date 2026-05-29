# Read-only legacy/admin cockpit lockdown

Patch 58G makes legacy/admin UI surfaces read-only by default.

SkeinRank's production UI is a Control Plane for review, debugging, and audit. Direct edits to live terminology, bindings, guardrails, or enrichment state can create configuration drift between GitOps/YAML state, the control-plane database, immutable snapshots, and local runtime agents. For that reason, the primary path for changes is:

```text
proposal → validation → risk policy → review → snapshot / GitOps rollout
```

The legacy cockpit remains available for inspection and local development, but write controls are disabled unless an explicit development flag is enabled.

## Primary UI contract

The daily product navigation remains limited to:

```text
Playground
AI Inbox
Schema & Snapshots
```

Low-level tools remain reachable under Settings or Developer Cockpit, but they do not provide production write affordances by default.

## Locked by default

When legacy writes are locked, the UI disables or replaces unsafe calls to action such as:

- add/edit/delete canonical terms;
- add/edit/delete aliases;
- create/edit Elasticsearch bindings;
- run enrichment jobs directly from the UI;
- edit guardrails/stop lists directly.

Instead, pages show guidance that production changes should flow through proposals, validation, snapshots, and GitOps rollout.

## Local development bypass

For local developer testing only, write controls can be enabled explicitly:

```bash
VITE_SKEINRANK_ENABLE_LEGACY_WRITE_TOOLS=true npm run dev
```

This is intended for local fixtures, API debugging, and manual smoke checks. It should stay disabled for production, demos, and enterprise pilots.

## Safety notes

- No backend endpoints are removed.
- Existing routes remain available.
- Backend RBAC remains authoritative.
- UI lockdown is a product-safety layer, not a replacement for server-side authorization.
