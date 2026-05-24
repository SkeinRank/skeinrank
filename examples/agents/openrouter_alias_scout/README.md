# OpenRouter alias scout foundation

This example is the first step toward a SkeinRank agent workflow. Patch 40F added the dependency-light local runner foundation. Patch 40G adds OpenRouter/OpenAI-compatible tool schemas, safety-focused prompts, and a strict structured output parser. Patch 40H adds candidate discovery and pruning from failed-query JSONL before any LLM call. Patch 40I adds compact evidence windows around discovered candidates. Patch 40K adds a local end-to-end demo report that stitches discovery, evidence, candidate packs, and review prompt preparation together. Patch 40J adds OpenRouter execution through a dependency-light client and a LangGraph-ready workflow plan while keeping proposal submission disabled by default. Patch 40L adds a service-account security profile, Patch 40M adds budget/cache controls, Patch 40N adds offline evaluation, and Patch 40O adds a deployable Docker Compose recipe.

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
| `deployment_recipe.py` | Offline Docker Compose deployment recipe report for the alias scout. |
| `openrouter_client.py` | Dependency-light OpenRouter `/chat/completions` client with testable transport injection. |
| `alias_scout_workflow.py` | LangGraph-ready state-machine workflow for LLM review and proposal payload preparation. |
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
no Elasticsearch calls, no OpenRouter calls, and no proposals are submitted. These
40I preview commands do not call OpenRouter yet. This local evidence mode
does not call OpenRouter yet.

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

## Run OpenRouter LLM review

Patch 40J adds OpenRouter execution for structured alias judgments. Preview the
LangGraph-ready workflow without calling OpenRouter:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py --print-llm-review-plan
```

Run a real model review after exporting a local key:

```bash
export OPENROUTER_API_KEY=...
python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --llm-review \
  --model openai/gpt-4o-mini \
  --max-candidates 3
```

Or write the LLM report to disk:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --write-llm-review-report /tmp/skeinrank-alias-scout-llm-report.json
```

The report schema is `skeinrank.agent_llm_review_report.v1`. The workflow calls
OpenRouter but still does not call SkeinRank API and does not submit proposals.
It prepares proposal payloads only when the model returns a strict `propose`
judgment above the configured confidence threshold. The workflow is
LangGraph-ready (`collect_failed_queries -> discover_candidates -> sample_evidence
-> build_review_queue -> openrouter_review -> parse_structured_judgment ->
prepare_proposal_payload -> write_run_report`) but does not require the
`langgraph` package yet.

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

- Patch 40L: service-account/security profile for real proposal submission.
- Patch 40M: budget limits and cache for model review.

### Patch 40L — Service-account security profile

Patch 40L adds the service-account security profile for the alias scout. It is
still safe by default: OpenRouter review can run, proposal payloads can be
prepared, but proposal submission remains disabled and runtime mutation is
blocked.

Preview the sanitized security profile without network calls:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py --print-security-profile
```

Validate it in CI/local checks:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py --check-security-profile
```

The report schema is `skeinrank.agent_security_profile.v1`. It shows whether
`OPENROUTER_API_KEY` and `SKEINRANK_AGENT_API_TOKEN` are configured, but redacts
secret values. The reference profile expects `SKEINRANK_AGENT_ROLE=contributor`,
blocks direct dictionary writes, snapshot publishing, direct Git pushes, and
runtime mutation, and only documents the existing safe `/v1/tools/*` facade.

### Patch 40M — Run budget and response cache

Patch 40M adds run budgets and response caching for live OpenRouter review.
The runner checks budget limits before every live model call and can reuse cached
responses for identical model/prompt/candidate-pack inputs. Cached responses do
not call OpenRouter and still do not mutate SkeinRank state.

Preview the budget/cache plan without network calls:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py --print-budget-cache-plan
```

Useful controls:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --llm-review \
  --model openai/gpt-4o-mini \
  --max-candidates 3 \
  --max-llm-calls 1 \
  --max-run-cost-usd 0.01
```

Clear the local cache when you want fresh model decisions:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py --clear-llm-cache
```

The offline plan schema is `skeinrank.agent_budget_cache_plan.v1`. The live LLM
report now includes `budget_cache_summary` with live calls, cache hits/misses,
skipped candidates, token usage, and estimated OpenRouter cost.
## Patch 40N — Agent evaluation loop

Patch 40N adds an offline evaluation report for the OpenRouter alias scout. It
can score the local demo pipeline or a saved `skeinrank.agent_llm_review_report.v1`
without calling OpenRouter, SkeinRank, Elasticsearch, or publishing snapshots.

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py --run-evaluation-report
python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --llm-review-report /tmp/skeinrank-alias-scout-llm-report.json \
  --run-evaluation-report
```

The output schema is `skeinrank.agent_evaluation_report.v1`. It reports
evidence coverage, LLM action mix, proposal-ready counts, optional human/policy
outcomes (`accepted`, `rejected`, `blocked`, `ambiguous`, `noisy`, `conflict`),
cost/cache summary, and a quality gate. Snapshot before/after evaluation remains
disabled until approved proposals are applied through the governed workflow.
## Patch 40O — Agent deployment recipe

Patch 40O adds a deployment recipe for the OpenRouter alias scout. It is safe by
default: the Docker Compose service runs an offline evaluation report unless an
operator explicitly overrides the command and provides `OPENROUTER_API_KEY`.
Proposal submission remains disabled and runtime mutation is blocked.

Preview the deployment recipe without network calls:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py --print-deployment-recipe
```

Write the recipe report:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --write-deployment-recipe examples/agents/openrouter_alias_scout/reports/deployment-recipe.json
```

Validate the Compose service shape:

```bash
docker compose \
  --env-file deploy/docker/openrouter-alias-scout.env.example \
  -f deploy/docker/openrouter-alias-scout.compose.yml \
  config
```

Makefile helpers:

```bash
make agent-deploy-plan
make agent-deploy-recipe
make agent-compose-config
```

The report schema is `skeinrank.agent_deployment_recipe.v1`. Generated reports
and cache files are ignored by Git.

## Patch 41A — Canonical hints and stronger review pack

Patch 41A improves the OpenRouter alias scout quality loop without changing backend routes or mutating runtime state. The runner now includes configured canonical hints in each candidate pack, so the model can choose from known terms such as `kubernetes`, `postgresql`, `elasticsearch`, and `rabbitmq` instead of guessing from raw evidence only.

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py --print-canonical-hints
python examples/agents/openrouter_alias_scout/run_alias_scout.py --print-sample-evidence-pack
```

The report schema is `skeinrank.agent_canonical_hints.v1`. Validation-sprint noise such as `queue`, `red`, and `shard` is pruned before LLM review by default, while real alias candidates such as `pg`, `k8s`, and `kube` receive `possible_canonical`, `slot`, `canonical_hint`, `canonical_candidates`, and `known_canonicals` fields in the review pack.

