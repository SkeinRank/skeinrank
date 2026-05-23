# OpenRouter alias scout foundation

This example is the first step toward a SkeinRank agent workflow. It does not call OpenRouter yet. Patch 40F only adds the local runner foundation: config, environment placeholders, failed-query input, and a small SkeinRank REST client for the existing agent tools.

The safety rule stays unchanged:

```text
LLM / agent -> proposal -> validation -> review/policy -> snapshot -> runtime
```

Agents must not mutate production terminology directly. They can only validate aliases, explain queries, and submit pending proposals through the `/v1/tools/*` facade.

## Files

| File | Purpose |
| --- | --- |
| `agent_config.example.json` | Local runner config. JSON only; no secrets. |
| `env.example` | Environment variable names for local testing. |
| `failed_queries.example.jsonl` | Tiny failed-query sample for later candidate discovery. |
| `skeinrank_client.py` | Dependency-light client for `/v1/tools/*`. |
| `run_alias_scout.py` | Dry-run runner skeleton. |

## Dry-run plan

From the repository root:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py --dry-run-plan
```

The output is a deterministic `skeinrank.agent_run_plan.v1` JSON document with sample query scopes and idempotency keys. It does not call OpenRouter.

## List SkeinRank bindings

Start the headless stack first:

```bash
make headless-up
make headless-golden-path
```

Then list available runtime contexts:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py --list-bindings
```

The runner uses:

```text
GET /v1/tools/bindings
```

## Current tool surface

The REST client wraps the existing agent-safe API:

```text
GET  /v1/tools/bindings
POST /v1/tools/explain-query
POST /v1/tools/validate-alias
POST /v1/tools/suggest-alias
```

`validate-alias` and `explain-query` are read-only. `suggest-alias` creates a pending proposal with idempotency support; it does not publish a runtime snapshot.

## What comes next

- Patch 40G: OpenRouter tool schemas and prompts.
- Patch 40H: candidate discovery and pruning.
- Patch 40I: compact evidence windows, so the agent does not read entire documents.
- Patch 40J: optional LangGraph workflow wrapper after the plain runner is proven.
