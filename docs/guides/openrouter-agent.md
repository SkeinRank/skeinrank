# OpenRouter alias scout agent example

The OpenRouter alias scout example is a safe reference path for agent-assisted
terminology discovery. It keeps the production invariant simple:

```text
LLM / agent -> proposal -> validation -> review/policy -> snapshot -> runtime
```

Patch 40F introduced the dependency-light runner foundation. Patch 40G added
OpenRouter/OpenAI-compatible tool schemas and safety prompts. Patch 40H added
failed-query candidate discovery and pruning. Patch 40I added compact evidence
windows. Patch 40K adds the local E2E demo report.

## Run the local demo

From the repository root:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py --run-demo-report
python examples/agents/openrouter_alias_scout/run_alias_scout.py --print-demo-review-prompt
```

Or use the Makefile helper:

```bash
make agent-demo
```

The demo report schema is `skeinrank.agent_demo_report.v1`. It is intentionally
local-only: no OpenRouter calls, no Elasticsearch calls, no SkeinRank API calls,
and no proposals are submitted.

## What the report contains

The report joins these local stages:

```text
failed queries -> candidate discovery -> evidence windows -> candidate packs -> review queue
```

It includes:

- discovered alias-like surfaces such as `pg`, `k8s`, and `kube`;
- compact evidence windows with explicit character and document limits;
- idempotency keys for future proposal retries;
- `source_quality` placeholders for future accepted/rejected proposal metrics;
- safety metadata that blocks direct dictionary writes, direct Git pushes, and
  snapshot publishing.

## What it does not do yet

Patch 40K does not call OpenRouter and does not submit proposals. Later patches
can consume the review queue, call a model, validate `propose` judgments through
`/v1/tools/validate-alias`, and submit pending proposals through
`/v1/tools/suggest-alias`. Runtime snapshot publishing remains part of the
reviewed governance workflow, not the agent runner.

### Patch 40J — OpenRouter execution / LangGraph-ready workflow

Patch 40J adds the first live OpenRouter execution path for the alias scout. Use
`--print-llm-review-plan` to preview the LangGraph-ready state-machine workflow
without network calls, then set `OPENROUTER_API_KEY` and run `--llm-review` to
call OpenRouter `/chat/completions` for strict `propose`, `reject`, or
`needs_evidence` judgments. The output schema is
`skeinrank.agent_llm_review_report.v1`. Proposal submission remains disabled by
default, so the workflow prepares proposal payloads but does not mutate SkeinRank
state.

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py --print-llm-review-plan
OPENROUTER_API_KEY=... python examples/agents/openrouter_alias_scout/run_alias_scout.py --llm-review --model openai/gpt-4o-mini --max-candidates 3
```

## Patch 40L — Agent security profile

Patch 40L adds a sanitized service-account security profile for the OpenRouter
alias scout. This does not introduce new backend routes and it does not enable
proposal submission. It makes the safety envelope explicit before later patches
add validation/submission, budget controls, evaluation, and deployment recipes.

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py --print-security-profile
python examples/agents/openrouter_alias_scout/run_alias_scout.py --check-security-profile
```

The output schema is `skeinrank.agent_security_profile.v1`. It redacts secret
environment variables, verifies the configured role, documents allowed
`/v1/tools/*` paths, and keeps these actions blocked for the reference agent:

```text
direct_dictionary_write
snapshot_publish
direct_git_push
runtime_mutation
```

Recommended local environment:

```bash
export SKEINRANK_AGENT_ROLE=contributor
export SKEINRANK_AGENT_API_TOKEN=...   # scoped contributor/service token; never commit
export OPENROUTER_API_KEY=...          # model key; never commit
```

`llm_review.submit_proposals` stays `false` in the example config. If someone
sets it to `true` without an explicit security policy and scoped token,
`--check-security-profile` exits non-zero and live review fails before model
execution.

## Patch 40M — OpenRouter agent budget and cache

Patch 40M adds run budgets and JSON response caching to the OpenRouter alias
scout. It keeps the agent safe by default: no backend routes are changed,
proposal submission stays disabled, and cached responses never mutate runtime
state. Use `--print-budget-cache-plan` for an offline `skeinrank.agent_budget_cache_plan.v1`
preview, `--max-llm-calls` / `--max-run-cost-usd` for live-run limits, and
`--clear-llm-cache` to remove the configured local cache.
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

### Patch 40O — Agent deployment recipe

Patch 40O adds a Docker Compose deployment recipe for the OpenRouter alias scout.
Use `--print-deployment-recipe` to inspect the offline `skeinrank.agent_deployment_recipe.v1` report, or `make agent-deploy-plan` / `make agent-compose-config` from the repository root. The reference service defaults to an offline evaluation report; proposal submission and runtime mutation remain disabled.

