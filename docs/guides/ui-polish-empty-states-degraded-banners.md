# UI polish, empty states, and degraded banners

Patch 58E keeps the Control Plane UI focused on the three enterprise review/debug surfaces:

- AI Proposals Inbox
- Search Playground
- Schema & Snapshots

The patch adds a global degraded-state banner and clearer empty states without adding new write workflows or operational dashboards.

## Global degraded-state banner

The shell now reads the existing alerting endpoint:

```http
GET /v1/ops/alerts/report
```

If the report is degraded and contains events, the UI shows a compact banner under the main header. The banner is intentionally non-mutating:

- no webhooks are sent;
- no database rows are changed;
- no OpenRouter calls are made;
- no Elasticsearch calls are made by the UI banner;
- the banner only displays the alert report returned by the Governance API.

The goal is to make degraded state visible before a reviewer approves proposals or before an operator trusts snapshot/runtime behavior.

## Empty-state guidance

The three-tab UI should not feel broken when no pilot data has been seeded yet.

The updated empty states explain what to do next:

- AI Inbox: seed/import a profile before reviewing agent proposals.
- Proposal queue: an empty queue can be healthy; it means there is no current moderation work.
- Playground: create/seed a binding before query-plan or snapshot compare can run.

These states reinforce the product model: write-heavy setup stays in headless/API/GitOps flows, while the UI focuses on review, debugging, and audit.

## Scope

Patch 58E does not add:

- manual terminology CRUD;
- enrichment triggers;
- snapshot publish/rollback buttons;
- custom monitoring dashboards;
- new backend endpoints.

Infrastructure monitoring still belongs in Grafana/Prometheus/Datadog. The UI only surfaces operational warnings that affect review confidence.
