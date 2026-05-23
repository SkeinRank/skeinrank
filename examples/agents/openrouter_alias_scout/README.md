# OpenRouter alias scout foundation

This example is the first step toward a SkeinRank agent workflow. Patch 40F added the dependency-light local runner foundation. Patch 40G adds OpenRouter/OpenAI-compatible tool schemas, safety-focused prompts, and a strict structured output parser. The example does not call OpenRouter yet and does not execute model-requested tools yet.

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
| `openrouter_tools.py` | OpenRouter/OpenAI-compatible tool schemas for the existing SkeinRank tools. |
| `prompts.py` | System prompt, alias-review prompt builder, and compact candidate pack helper. |
| `structured_output.py` | Strict parser for `propose`, `reject`, and `needs_evidence` judgments. |
| `run_alias_scout.py` | Dry-run runner skeleton and local schema/prompt preview helpers. |

## Dry-run plan

From the repository root:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py --dry-run-plan
```

The output is a deterministic `skeinrank.agent_run_plan.v1` JSON document with sample query scopes and idempotency keys. It does not call OpenRouter.

## Preview OpenRouter tool schemas and prompts

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py --print-tool-schemas
python examples/agents/openrouter_alias_scout/run_alias_scout.py --print-system-prompt
python examples/agents/openrouter_alias_scout/run_alias_scout.py --print-sample-review-prompt
```

The tool schemas expose only the existing safe REST facade:

```text
skeinrank_list_bindings
skeinrank_explain_query
skeinrank_validate_alias
skeinrank_submit_alias_proposal
```

They map to existing Governance API routes and do not introduce new backend calls.

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

## Structured judgment contract

The model-facing review prompt expects one JSON object with:

```text
action: propose | reject | needs_evidence
confidence: 0..1
reason: string
risk_flags: string[]
```

`propose` additionally requires `alias_value`, `canonical_value`, and `slot`. The runner must still validate proposal payloads through SkeinRank before saving anything.

## What comes next

- Patch 40H: candidate discovery and pruning.
- Patch 40I: compact evidence windows, so the agent does not read entire documents.
- Patch 40K: end-to-end agent demo and run report.
- Patch 40J: optional LangGraph workflow wrapper after the plain runner is proven.
