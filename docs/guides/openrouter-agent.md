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

## Patch 41A — Canonical hints and stronger review pack

Patch 41A improves the OpenRouter alias scout quality loop without changing backend routes or mutating runtime state. The runner now includes configured canonical hints in each candidate pack, so the model can choose from known terms such as `kubernetes`, `postgresql`, `elasticsearch`, and `rabbitmq` instead of guessing from raw evidence only.

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py --print-canonical-hints
python examples/agents/openrouter_alias_scout/run_alias_scout.py --print-sample-evidence-pack
```

The report schema is `skeinrank.agent_canonical_hints.v1`. Validation-sprint noise such as `queue`, `red`, and `shard` is pruned before LLM review by default, while real alias candidates such as `pg`, `k8s`, and `kube` receive `possible_canonical`, `slot`, `canonical_hint`, `canonical_candidates`, and `known_canonicals` fields in the review pack.


## Patch 41B — Validate and submit proposals safely

After Patch 41A produces high-confidence `proposal_payload` values, Patch 41B
lets the reference runner validate those payloads against the existing
SkeinRank tools facade.

Preview what would be validated without any network calls:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --llm-review-report /tmp/skeinrank-41a-llm-report.json \
  --print-proposal-submission-plan
```

Validate ready proposals through the Governance API without saving them:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --llm-review-report /tmp/skeinrank-41a-llm-report.json \
  --validate-ready-proposals
```

Submit mode is deliberately gated. `--submit-ready-proposals` first validates via
`POST /v1/tools/validate-alias` and then creates a pending proposal through
`POST /v1/tools/suggest-alias` only when the security profile and
`proposal_submission.submit_enabled` allow it. It does not publish snapshots or
mutate runtime state.

## Patch 41C — Agent validation statuses and idempotent proposal handling

Patch 41C keeps proposal submission safe while making validation reports more
useful for agent workflows. Validation warnings are now classified before any
optional submission: existing aliases that already map to the requested canonical
are treated as idempotent no-ops, slot mismatches are routed to manual review,
and blocked validations are never submitted.

This means an agent run can distinguish:

```text
passed → eligible for optional submission
existing alias warning → idempotent_existing_alias
slot mismatch warning → manual_review_required
blocked → blocked
```

The runner still does not mutate runtime dictionaries or publish snapshots.


## Patch 41D — New alias proposal smoke test

Patch 41D adds a controlled smoke path for a brand-new alias proposal. It does not call OpenRouter and does not publish snapshots. The runner can generate a proposal-ready LLM report for the configured smoke alias, validate it through `POST /v1/tools/validate-alias`, and, only with an explicit submit flag, create a pending proposal through `POST /v1/tools/suggest-alias`.

Preview the smoke plan without network calls:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py --print-new-alias-smoke-plan
```

Write a proposal-ready smoke report:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --write-new-alias-smoke-llm-report /tmp/skeinrank-new-alias-smoke-llm.json
```

Validate the smoke proposal without saving it:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py --run-new-alias-smoke-test
```

Create one pending proposal and verify idempotent retry explicitly:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --submit-new-alias-smoke-test \
  --write-new-alias-smoke-report /tmp/skeinrank-new-alias-smoke-report.json
```

The default smoke alias is `pgx → postgresql` in the `infra_incidents` profile. Re-running the submit smoke should not create duplicate proposals; the second `suggest-alias` call is expected to return an idempotent retry.
