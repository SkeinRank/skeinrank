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

## Patch 41E — Elasticsearch evidence connector

Patch 41E adds an optional, read-only Elasticsearch/OpenSearch evidence connector for the OpenRouter alias scout. It does not change backend routes, does not call OpenRouter, and does not mutate dictionaries, snapshots, or runtime state. The connector searches a configured index for discovered candidates, normalizes hits into local evidence records, and reuses the existing compact evidence sampler.

Preview the connector plan without network calls:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py --print-elasticsearch-evidence-plan
```

Sample evidence from Elasticsearch for discovered candidates:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --sample-evidence-from-elasticsearch \
  --elasticsearch-url http://127.0.0.1:9200 \
  --elasticsearch-index skeinrank-agent-evidence \
  --elasticsearch-text-field title \
  --elasticsearch-text-field text
```

Export normalized Elasticsearch hits to JSONL for offline review:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --write-elasticsearch-evidence-records /tmp/skeinrank-es-evidence.jsonl
```


## Patch 41F — Agent run/document tracking

Patch 41F adds a local JSONL tracking contract for agent runs and document visits. This is intentionally local and dependency-light: it does not call OpenRouter, Elasticsearch, or the SkeinRank API, and it does not mutate runtime state.

The tracker fingerprints evidence/source records with a `content_hash` and combines `agent_version`, `prompt_version`, model, profile, and binding into a `processing_context_hash`. Repeated runs can therefore distinguish unchanged documents from changed content or changed processing context.

Useful commands:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py --print-agent-tracking-plan

python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --write-agent-tracking-report /tmp/skeinrank-agent-tracking-report.json

python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --append-agent-tracking-ledger \
  --agent-tracking-ledger /tmp/skeinrank-agent-ledger.jsonl
```

The future production version can move the same fields into PostgreSQL tables such as `agent_runs`, `agent_source_documents`, and `agent_document_visits`.

## Patch 41G — Proposal inbox / review workflow

Patch 41G adds a local proposal inbox for human-in-the-loop review. The inbox combines a saved LLM review report with an optional proposal validation/submission report and optional JSONL review decisions.

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py --print-proposal-inbox-plan
```

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --llm-review-report /tmp/skeinrank-41a-llm-report.json \
  --proposal-submission-report /tmp/skeinrank-proposal-submission-report.json \
  --build-proposal-inbox
```

Review decisions are local JSONL records:

```jsonl
{"candidate_alias":"pg","action":"defer","reviewer":"knowledge-manager","comment":"Already exists; no proposal is needed."}
{"candidate_alias":"k8s","action":"edit","reviewer":"knowledge-manager","comment":"Resolve slot mismatch before apply.","edited_slot":"tool"}
```

This patch is still offline: it records review intent for the agent workflow, but it does not mutate production terminology. A later apply/snapshot step should consume approved decisions through the governed pipeline.

Write the inbox JSON to disk:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --llm-review-report /tmp/skeinrank-41a-llm-report.json \
  --proposal-submission-report /tmp/skeinrank-proposal-submission-report.json \
  --write-proposal-inbox /tmp/skeinrank-proposal-inbox.json
```


## Patch 41H — Apply approved proposals + snapshot evaluation

Patch 41H adds an offline bridge from reviewed proposal inbox cards to a governed apply plan. It is intentionally read/report-only: it does not directly write dictionaries, approve backend proposals, or publish snapshots.

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --proposal-inbox-report /tmp/proposal-inbox.json \
  --build-approved-apply-plan

python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --approved-apply-plan /tmp/approved-apply-plan.json \
  --before-snapshot /tmp/snapshot-before.json \
  --after-snapshot /tmp/snapshot-after.json \
  --run-snapshot-evaluation
```

The report uses the schema `skeinrank.agent_approved_apply_plan.v1` for apply planning and `skeinrank.agent_snapshot_evaluation_report.v1` for before/after snapshot diffs.

Patch 41H CLI flags: `--print-approved-apply-plan`.

## Patch 41I — scheduled runner / worker mode

Patch 41I introduces a single worker-style entrypoint for orchestrators. Instead of
calling every stage manually, an external scheduler can run one command and collect a
cycle report plus per-step JSON artifacts.

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --print-scheduled-runner-plan

python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --run-agent-cycle
```

For Airflow, Prefect, cron, GitHub Actions, or Kubernetes CronJob, use the same command
as a one-shot job. By default the cycle is offline and safe: no OpenRouter calls, no
SkeinRank proposal submission, no dictionary writes, and no snapshot publication.

Optional live mode is explicit:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --run-agent-cycle \
  --agent-cycle-live-llm \
  --max-llm-calls 3 \
  --max-run-cost-usd 0.05
```

Validation and submission remain gated separately:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --run-agent-cycle \
  --agent-cycle-live-llm \
  --agent-cycle-validate-proposals
```

`--agent-cycle-submit-proposals` is intentionally separate and still cannot publish
snapshots or mutate runtime state.

## Patch 42A — full agent integration smoke test

Patch 42A packages the manually verified agent contour into one reproducible,
network-free smoke test. It exercises the report chain without external services:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --print-integration-smoke-plan

python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --write-integration-smoke-report /tmp/skeinrank-agent-smoke.json \
  --integration-smoke-artifacts-dir /tmp/skeinrank-agent-smoke-artifacts
```

The smoke creates artifacts for:

1. demo candidate/evidence report;
2. synthetic proposal-ready LLM review report;
3. synthetic validation report;
4. proposal inbox report;
5. approved apply plan;
6. snapshot evaluation report;
7. agent evaluation report;
8. scheduled cycle summary.

It keeps `openrouter_calls=false`, `elasticsearch_calls=false`,
`skeinrank_api_calls=false`, `proposal_submission_enabled=false`,
`runtime_mutation_enabled=false`, and `snapshot_publish_enabled=false`. This makes it
safe to run in CI as a fast preflight before live OpenRouter/API validation.

### Patch 42B — Real Elasticsearch validation scenario

Patch 42B turns the Elasticsearch evidence connector into a reproducible validation scenario. The scenario can generate fixture files, index a tiny sample corpus into an isolated local Elasticsearch/OpenSearch index, and run read-only evidence validation against that index.

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py --print-real-elasticsearch-validation-plan
python examples/agents/openrouter_alias_scout/run_alias_scout.py --write-real-elasticsearch-validation-fixtures
python examples/agents/openrouter_alias_scout/run_alias_scout.py --index-real-elasticsearch-validation-docs
python examples/agents/openrouter_alias_scout/run_alias_scout.py --run-real-elasticsearch-validation
```

The sample indexing step mutates only the configured validation index. The validation step is read-only and does not call OpenRouter or SkeinRank proposal APIs.

## Patch 42C — Standard report artifacts

Patch 42C gives the alias scout a stable artifact layout for scheduled jobs and
external orchestrators.

```text
reports/<run_id>/
  manifest.json
  run_summary.json
  reports/<artifact>.json
```

Use it to make agent runs easy to archive from Airflow, cron, GitHub Actions, or
Kubernetes CronJobs:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --print-artifacts-standard-plan

python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --write-agent-cycle-report /tmp/sr-cycle.json \
  --agent-cycle-artifacts-dir /tmp/sr-artifacts
```

The generated `manifest.json` is network-free metadata. It does not imply
OpenRouter, Elasticsearch, SkeinRank API calls, runtime mutation, or snapshot
publication.
