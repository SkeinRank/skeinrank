# SkeinRank documentation

This directory keeps repository-level documentation for developers, operators, and contributors. The public product site is available at <https://skeinrank.github.io>.

## Start here

- [`overview.md`](overview.md) — what SkeinRank is, what it solves, and how the repository is organized.
- [`concepts/terminology-control-plane.md`](concepts/terminology-control-plane.md) — terminology, aliases, guardrails, evidence, and snapshots.
- [`concepts/profiles-bindings-snapshots.md`](concepts/profiles-bindings-snapshots.md) — the production runtime model.
- [`concepts/headless-runtime-contracts.md`](concepts/headless-runtime-contracts.md) — headless-first contract map for runtime, agents, snapshots, and UI scope.
- [`concepts/dictionary-spec-v1.md`](concepts/dictionary-spec-v1.md) — stable dictionary import/export contract with `schema_version`.
- [`concepts/coverage-framework.md`](concepts/coverage-framework.md) — slots, tags, ambiguous aliases, binding policies, and evaluation guardrails.
- [`adr/0001-headless-runtime-contracts.md`](adr/0001-headless-runtime-contracts.md) — accepted architecture decision for headless runtime boundaries.
- [`guides/core-sdk-and-cli.md`](guides/core-sdk-and-cli.md) — local dictionary validation, extraction, canonicalization, and document extraction.
- [`guides/governance-console.md`](guides/governance-console.md) — governance API/UI workflow.
- [`guides/coverage-framework.md`](guides/coverage-framework.md) — headless workflow for tags, conflicts, ambiguous candidates, policies, and before/after evaluation.
- [`../examples/agents/openrouter_alias_scout`](../examples/agents/openrouter_alias_scout) — reference OpenRouter alias scout foundation and SkeinRank REST client.
- [`guides/elasticsearch-enrichment.md`](guides/elasticsearch-enrichment.md) — Elasticsearch enrichment, dry-run, evidence, jobs, and cancellation.
- [`guides/development.md`](guides/development.md) — local development checks and package workflow.
- [`api/governance-api.md`](api/governance-api.md) — important HTTP surfaces and runtime endpoints.

## Deployment

- [`deployment/docker-compose.md`](deployment/docker-compose.md) — full Docker Compose dev stack.
- [`deployment/headless-quickstart.md`](deployment/headless-quickstart.md) — API/PostgreSQL-only golden path for headless integrations.
- [`deployment/security.md`](deployment/security.md) — production-oriented security baseline.
- [`deployment/observability.md`](deployment/observability.md) — logs, metrics, tracing, Prometheus, and Grafana.
- [`deployment/dev-stack-troubleshooting.md`](deployment/dev-stack-troubleshooting.md) — common local stack issues.


## Headless dictionary facade

Automation-first integrations should prefer the headless dictionary routes:

```text
POST /v1/headless/dictionaries/validate
POST /v1/headless/dictionaries/apply
GET  /v1/headless/dictionaries/export?profile_name=...
```

They share the same dictionary spec v1 payload as the console migration routes,
but are named for CI/CD, agents, and service-to-service workflows.

- Snapshot artifact export: `GET /v1/headless/snapshots/export?binding_id=...` and `skeinrank-migrate snapshot-export`.

- Runtime artifact file loader/cache: see `docs/concepts/headless-runtime-contracts.md`.

## Headless quickstart

Use `docker-compose.headless.yml` for the API/PostgreSQL-only Phase A path. See `deployment/headless-quickstart.md` for the dictionary apply -> binding -> snapshot artifact workflow.

## Agent MCP tools

Patch 37F adds a minimal MCP stdio adapter for agent workflows:

```bash
cd packages/skeinrank-governance-api
poetry run skeinrank-mcp --api-url http://127.0.0.1:8010
```

It exposes binding discovery, query explanation, alias validation, alias proposal
submission, and proposal status lookup. The adapter delegates to `/v1/tools/*`,
so agents still go through proposal validation and review rather than mutating
runtime terminology directly.

## OpenRouter alias scout foundation

Patch 40F adds a local reference runner under
`examples/agents/openrouter_alias_scout`. Patch 40G adds the OpenRouter-facing
contract layer: tool schemas, safety prompts, compact candidate-pack prompt
helpers, and strict structured output parsing. Patch 40H adds deterministic
failed-query candidate discovery and pruning before any LLM call. Patch 40I adds
compact evidence windows with `max_docs`, `max_windows`, and `max_total_chars`
limits. The example remains LLM-free and does not execute tool calls yet. Local
previews are available through `--print-tool-schemas`, `--print-system-prompt`,
`--print-sample-review-prompt`, `--discover-candidates`,
`--print-sample-candidate-pack`, `--sample-evidence`, and
`--print-sample-evidence-pack`.
