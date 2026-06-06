# Demo smoke command and one-command product tour

The product-tour smoke command validates the seeded `platform_ops` demo after the local Docker stack is running.

Use it for screenshots, demos, and release checks when you need to prove that the guided walkthrough is usable in the focused Control Plane UI.

## Commands

Plan the tour without touching any service:

```bash
make demo-tour-plan
```

Run a read-oriented smoke check against an already seeded stack:

```bash
make demo-tour-smoke
```

Run the one-command product tour from a running local stack:

```bash
make demo-tour
```

`make demo-tour` runs `make demo-reset` first, then runs `make demo-tour-smoke` and writes:

```text
examples/platform_ops_demo/reports/platform_ops_demo_tour_report.json
```

Inspect the last report:

```bash
make demo-tour-show
```

Clean generated tour reports:

```bash
make demo-tour-clean
```

## What the smoke command checks

The read-only smoke checks verify:

- Governance API `/livez` and `/readyz` are reachable;
- Elasticsearch is reachable;
- the UI root is reachable;
- admin login works;
- `platform_ops` profile has the expected seeded terms;
- `Production knowledge base` binding exists;
- `platform_knowledge_base` contains the seeded documents;
- `platform_knowledge_base_search` exists after enrichment;
- Playground query planning returns `kubernetes`, `postgresql`, and `project phoenix`;
- AI Inbox has pending demo proposals for `edge`, `EKS`, `OpenSearch`, and `prod`;
- the committed walkthrough contract still describes the three-tab UI.

The demo query is:

```text
k8s pg timeout during phoenix rollout
```

## Safety scope

`make demo-tour-smoke` is read-oriented. It does not create proposals, approve proposals, apply changes, publish snapshots, or start enrichment.

`make demo-tour` is intentionally a reset-and-tour command for local demo setup. It calls `make demo-reset`, which rebuilds the local demo index and seeded data before running the read-only smoke check.

Both commands refuse non-local API/Elasticsearch URLs unless the underlying scripts are run with `--force-non-local`.

Generated reports are ignored by git:

```text
examples/platform_ops_demo/reports/
```

## Credentials

If your dev stack uses custom bootstrap admin credentials, pass them through environment variables:

```bash
SKEINRANK_DEMO_ADMIN_USERNAME=admin \
SKEINRANK_DEMO_ADMIN_PASSWORD="CHANGE_ME_STRONG_BOOTSTRAP_ADMIN_PASSWORD" \
make demo-tour
```

For a smoke-only check:

```bash
SKEINRANK_DEMO_ADMIN_USERNAME=admin \
SKEINRANK_DEMO_ADMIN_PASSWORD="CHANGE_ME_STRONG_BOOTSTRAP_ADMIN_PASSWORD" \
make demo-tour-smoke
```

## Manual script usage

The Makefile targets call:

```bash
python3 examples/platform_ops_demo/demo_product_tour.py --write-report examples/platform_ops_demo/reports/platform_ops_demo_tour_report.json
```

Plan mode:

```bash
python3 examples/platform_ops_demo/demo_product_tour.py --plan
```

Skip only the UI HTTP check when you want to validate API/Elasticsearch state before opening the React app:

```bash
python3 examples/platform_ops_demo/demo_product_tour.py --skip-ui-check
```
