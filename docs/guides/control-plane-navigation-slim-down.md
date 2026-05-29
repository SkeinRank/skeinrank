# Control Plane navigation slim-down

Patch 58F keeps the SkeinRank UI focused on the three screens that matter for a production-style human-in-the-loop control plane:

1. **Playground** — debug query canonicalization and compare snapshot behavior.
2. **AI Inbox** — review agent-submitted proposals with evidence, validation, and risk context.
3. **Schema & Snapshots** — inspect schema, bindings, terminology hierarchy, and snapshot history.

The patch does **not** delete legacy pages or remove backend capabilities. It only moves low-level pages out of the primary navigation and into utility groups.

## Primary navigation contract

The main sidebar's primary product navigation contains only:

```text
Playground
AI Inbox
Schema & Snapshots
```

This avoids presenting SkeinRank as a broad CRUD admin console. The UI is now positioned as a read-heavy/debug/moderation surface over a headless/API-first platform.

## Utility navigation

Operational and developer workflows remain available below the primary section:

```text
Settings
  API Access
  Users
  Integrations

Developer Cockpit
  Dashboard
  Terms
  Suggestions
  Guardrails
```

These pages are intentionally retained for local development, pilot debugging, and compatibility with existing backend workflows. They are not the daily workflow for a knowledge manager or reviewer.

## Default landing page

The UI now opens on **Playground** by default. This makes the first screen an immediately useful debug surface instead of a dashboard. Infrastructure metrics should still live in Grafana/Prometheus/Datadog, while SkeinRank focuses on terminology behavior, proposal review, and snapshot audit.

## Safety and scope

This is a frontend navigation-only patch:

- no backend endpoints are added;
- no routes/pages are deleted;
- no database migrations are added;
- no proposal apply, snapshot publish, enrichment, OpenRouter, or Elasticsearch behavior changes;
- legacy/dev pages are still reachable from the utility navigation.

## Manual check

Start the UI and confirm the top sidebar section contains only the three product tabs:

```bash
cd packages/skeinrank-ui
npm run dev
```

Then open `http://127.0.0.1:5173` and check:

- the initial page is Search Playground;
- `Playground`, `AI Inbox`, and `Schema & Snapshots` are the only primary items;
- `API Access`, `Users`, `Integrations`, `Dashboard`, `Terms`, `Suggestions`, and `Guardrails` remain available below as utility/developer tools.
