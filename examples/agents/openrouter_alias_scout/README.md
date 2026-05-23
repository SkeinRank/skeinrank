# OpenRouter alias scout foundation

This example is the first step toward a SkeinRank agent workflow. Patch 40F added the dependency-light local runner foundation. Patch 40G adds OpenRouter/OpenAI-compatible tool schemas, safety-focused prompts, and a strict structured output parser. Patch 40H adds candidate discovery and pruning from failed-query JSONL before any LLM call. Patch 40I adds compact evidence windows around discovered candidates. Patch 40K adds a local end-to-end demo report that stitches discovery, evidence, candidate packs, and review prompt preparation together, still without OpenRouter calls or model-requested tool execution.

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
| `failed_queries.example.jsonl` | Tiny failed-query sample for local candidate discovery. |
| `evidence_records.example.jsonl` | Tiny search-log/document snippet sample for local evidence windows. |
| `candidate_discovery.py` | Dependency-light failed-query candidate mining, pruning, scoring, and fact-pack helpers. |
| `evidence_sampler.py` | Dependency-light compact window sampler for candidate evidence packs. |
| `demo_report.py` | Local E2E demo report builder for discovery + evidence + review queue output. |
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

## Discover and prune candidates locally

Patch 40H adds a deterministic pre-LLM discovery step. It reads failed-query rows,
extracts alias-like surfaces such as `pg`, `k8s`, and `kube`, prunes configured
noise/known terms, and prints a compact JSON report:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py --discover-candidates
python examples/agents/openrouter_alias_scout/run_alias_scout.py --print-sample-candidate-pack
```

The report is `skeinrank.agent_candidate_discovery.v1`. It does not call
OpenRouter, does not infer canonical values, and does not submit proposals.

## Sample compact evidence windows

Patch 40I adds a local evidence sampler. It reads search-log/document JSONL
records, finds short windows around discovered candidates, and enforces
`max_docs`, `max_windows`, and `max_total_chars` limits so the future LLM step
never sees full documents:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py --sample-evidence
python examples/agents/openrouter_alias_scout/run_alias_scout.py --print-sample-evidence-pack
```

The report is `skeinrank.agent_evidence_sampling.v1`. It is still local-only:
no Elasticsearch calls, no OpenRouter calls, and no proposals are submitted. The
example does not call OpenRouter yet.

## Run the local E2E demo report

Patch 40K stitches together the local pre-LLM stages into one deterministic report:

```text
failed queries -> candidate discovery -> evidence windows -> candidate packs -> review queue
```

Run it from the repository root:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py --run-demo-report
python examples/agents/openrouter_alias_scout/run_alias_scout.py --print-demo-review-prompt
```

You can also write the JSON report to a file:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py --write-demo-report /tmp/skeinrank-alias-scout-report.json
```

Or use the Makefile helper:

```bash
make agent-demo
```

The report schema is `skeinrank.agent_demo_report.v1`. It is still local-only:
no OpenRouter calls, no Elasticsearch calls, no SkeinRank API calls, and no
proposals are submitted. The report shows which candidates are ready for later
LLM review, how many compact evidence windows were found, and a source-quality
placeholder for future accepted/rejected proposal metrics.

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

- Patch 40J: optional LangGraph workflow wrapper after the plain runner is proven.
- Patch 40L: service-account/security profile for real proposal submission.
