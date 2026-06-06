# Seeded demo scenario and guided product walkthrough

The `examples/platform_ops_demo` seed provides a guided product walkthrough for the focused three-tab Control Plane UI.

The goal is not to create a new write surface. The seed gives operators a screenshot-ready local state that demonstrates the production-safe workflow:

```text
Playground -> AI Inbox -> Schema & Snapshots -> read-only legacy cockpit
```

Production changes are still expected to flow through proposals, validation, risk policy, review, snapshots, and GitOps delivery.

## Seed the local demo

Start the local dev stack, then run:

```bash
make demo-reset
```

For a non-destructive run:

```bash
make demo-seed
```

For read-only inspection:

```bash
make demo-status
```

The seed uses:

- profile: `platform_ops`
- index: `platform_knowledge_base`
- binding: `Production knowledge base`
- runtime alias: `platform_knowledge_base_search`
- demo query: `k8s pg timeout during phoenix rollout`

The committed walkthrough contract lives in:

```text
examples/platform_ops_demo/platform_ops_demo_walkthrough.json
```

## Product tour

### 1. Playground

Open the UI and start with **Playground**.

Run:

```text
k8s pg timeout during phoenix rollout
```

Expected story:

- `k8s` resolves to `kubernetes`;
- `pg` resolves to `postgresql`;
- `phoenix rollout` resolves to `project phoenix` / rollout context;
- compare mode can use the same binding in both columns before a draft snapshot exists.

### 2. AI Inbox

Open **AI Inbox** and review the seeded proposal cards.

The demo intentionally creates a range of proposal risk states:

| Alias | Canonical | Expected risk | Why it exists |
| --- | --- | --- | --- |
| `edge` | `api-gateway` | low | shows a simple evidence-backed alias proposal |
| `EKS` | `kubernetes` | medium | confidence is below the low-risk threshold |
| `OpenSearch` | `elasticsearch` | medium | cross-vendor terminology needs reviewer judgment |
| `prod` | `production environment` | high | ambiguous alias that should not be blindly applied |

The detail panel should show evidence snapshots, validation findings, and apply-policy decisions.

### 3. Schema & Snapshots

Open **Schema & Snapshots**.

Use the tree/detail view to inspect:

- `platform_ops` profile;
- `Production knowledge base` binding;
- category/slot groups;
- canonical terms;
- aliases;
- runtime snapshot/enrichment state.

This screen is read-heavy by design. It should explain the schema and runtime state without encouraging direct CRUD mutations.

### 4. Read-only legacy cockpit

Open a legacy/developer page from the utility navigation.

Expected behavior:

- legacy routes remain available for inspection;
- legacy write controls are locked by default;
- the UI explains that production changes should go through AI Inbox, validation, snapshots, and GitOps rollout;
- direct legacy writes require an explicit local-development bypass:

```bash
VITE_SKEINRANK_ENABLE_LEGACY_WRITE_TOOLS=true npm run dev
```

Do not enable the bypass for product demos or production-like walkthroughs.

## Safety scope

The seeded walkthrough is intended for local demos only.

- It refuses non-local API/Elasticsearch URLs unless `--force-non-local` is passed.
- It does not require manual CRUD pages.
- It does not enable legacy write tools.
- It creates proposals for review; it does not auto-approve or auto-apply them.
- It keeps the Control Plane story focused on review, debugging, audit, and snapshot rollout.
