# Platform operations demo seed

This example fills a local SkeinRank Docker Compose stack with a realistic platform-operations dataset for product walkthroughs and screenshots.

It demonstrates the complete Control Plane story:

- Elasticsearch index `platform_knowledge_base`;
- incident, runbook, ticket, and design-note documents;
- governance profile `platform_ops`;
- canonical terms, aliases, tags, and stop-list entries;
- Elasticsearch binding `Production knowledge base`;
- AI Inbox proposals with evidence and risk signals;
- immutable runtime snapshot state;
- operator-controlled search delivery that publishes the runtime alias `platform_knowledge_base_search`.

## Start the stack

From the repository root:

```bash
ES_JAVA_OPTS="-Xms512m -Xmx512m" docker compose -f docker-compose.dev.yml up --build -d
```

Verify the API and Elasticsearch are ready:

```bash
curl -s http://127.0.0.1:8010/readyz | python3 -m json.tool
curl -s http://127.0.0.1:19200 | python3 -m json.tool
```

## Seed the demo

Reset and seed the local preview dataset:

```bash
make demo-reset
```

`demo-reset` deletes the demo Elasticsearch indices before loading the preview dataset. It does not delete PostgreSQL volumes or unrelated data.

For a non-destructive seed run:

```bash
make demo-seed
```

Check the current demo status without writing data:

```bash
make demo-status
```

## One-command product tour

Plan the tour without making service calls:

```bash
make demo-tour-plan
```

Run a read-oriented smoke check against an already seeded stack:

```bash
make demo-tour-smoke
```

Run the full local tour from a running stack:

```bash
make demo-tour
```

`make demo-tour` resets the preview dataset, then checks Playground, AI Inbox, Schema & Snapshots, and the committed walkthrough contract. It writes:

```text
examples/platform_ops_demo/reports/platform_ops_demo_tour_report.json
```

Inspect the report with:

```bash
make demo-tour-show
```

The underlying stdlib-only script is:

```text
examples/platform_ops_demo/demo_product_tour.py
```

## Guided Control Plane walkthrough

Use the seeded console to walk through the focused product tabs:

1. **Playground** — run `k8s pg timeout during phoenix rollout` and inspect deterministic canonicalization.
2. **AI Inbox** — review proposals with evidence, risk labels, and apply-policy decisions.
3. **Schema & Snapshots** — inspect the `platform_ops` profile tree, binding, aliases, and runtime snapshot state.

The committed walkthrough contract is:

```text
examples/platform_ops_demo/platform_ops_demo_walkthrough.json
```

The seed also demonstrates the read-only legacy cockpit model: old developer routes remain available for inspection, but production-style demos should not enable `VITE_SKEINRANK_ENABLE_LEGACY_WRITE_TOOLS`.

## Open the console

```text
http://127.0.0.1:5173
```

Default development login:

```text
admin / change-me
```

Useful demo query for Search Playground:

```text
k8s pg timeout during phoenix rollout
```

## Environment overrides

The script is local-first and refuses non-local API/Elasticsearch URLs unless explicitly overridden.

```bash
SKEINRANK_DEMO_API_URL=http://127.0.0.1:8010 \
SKEINRANK_DEMO_ELASTICSEARCH_URL=http://127.0.0.1:19200 \
SKEINRANK_DEMO_ADMIN_USERNAME=admin \
SKEINRANK_DEMO_ADMIN_PASSWORD=change-me \
make demo-reset
```

For a custom local port:

```bash
make demo-reset DEMO_ARGS="--api-url http://127.0.0.1:18010 --elasticsearch-url http://127.0.0.1:19200"
```

To seed a non-local sandbox intentionally:

```bash
python3 examples/platform_ops_demo/seed_platform_demo.py \
  --api-url https://example.invalid \
  --elasticsearch-url https://example.invalid \
  --force-non-local
```

## Safety notes

- The demo is intended for local preview and isolated sandboxes.
- Production delivery should follow the operator-controlled search delivery runbooks.
- Runtime terminology still follows the proposal → review → snapshot → binding lifecycle.
