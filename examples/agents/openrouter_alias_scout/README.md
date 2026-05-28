# OpenRouter alias scout foundation

This example is the first step toward a SkeinRank agent workflow. Patch 40F added the dependency-light local runner foundation. Patch 40G adds OpenRouter/OpenAI-compatible tool schemas, safety-focused prompts, and a strict structured output parser. Patch 40H adds candidate discovery and pruning from failed-query JSONL before any LLM call. Patch 40I adds compact evidence windows around discovered candidates. Patch 40K adds a local end-to-end demo report that stitches discovery, evidence, candidate packs, and review prompt preparation together. Patch 40J adds OpenRouter execution through a dependency-light client and a LangGraph-ready workflow plan while keeping proposal submission disabled by default. Patch 40L adds a service-account security profile, Patch 40M adds budget/cache controls, Patch 40N adds offline evaluation, Patch 40O adds a deployable Docker Compose recipe, Patch 41A adds canonical hints, Patch 41B validates/submits ready proposal payloads safely, Patch 41C classifies validation warnings for idempotent/no-op and manual-review handling, Patch 41D adds a controlled new-alias smoke path, and Patch 41E adds an optional read-only Elasticsearch evidence connector.

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
| `proposal_submission.py` | Safe validation/submission bridge for ready proposal payloads. |
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


### Patch 41B — Validate and submit proposals safely

Patch 41B bridges prepared `proposal_payload` objects to the existing SkeinRank
agent tools. It is still governed and safe by default: the runner can validate
ready proposals through `POST /v1/tools/validate-alias`, and it submits through
`POST /v1/tools/suggest-alias` only when `--submit-ready-proposals` is used and
the config/security profile explicitly allow submission.

Preview the saved LLM report without API calls:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --llm-review-report /tmp/skeinrank-41a-llm-report.json \
  --print-proposal-submission-plan
```

Validate ready payloads without submitting them:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --llm-review-report /tmp/skeinrank-41a-llm-report.json \
  --validate-ready-proposals
```

Submission stays opt-in and still creates only pending proposals:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --llm-review-report /tmp/skeinrank-41a-llm-report.json \
  --submit-ready-proposals \
  --write-proposal-submission-report /tmp/skeinrank-proposal-submission.json
```

`--submit-ready-proposals` never writes directly to dictionaries and never
publishes snapshots. The next governed step is human/policy review of pending
proposals.

### Patch 41C — Agent validation statuses and idempotent proposal handling

Patch 41C refines the safe submission bridge by classifying validation warnings
before any optional submit call. Existing aliases that already map to the same
canonical term are reported as `idempotent_existing_alias`, slot mismatches are
reported as `manual_review_required`, and blocked validations remain blocked.

The summary now includes counters such as:

```text
idempotent_existing_aliases
manual_review_required
blocked
validation_warnings
```

This keeps the agent from creating duplicate proposals while still surfacing
edge cases for human/policy review.

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

Patch 41F adds a local JSONL run/document tracking ledger for the OpenRouter alias scout. It is a DB-ready contract for future PostgreSQL persistence, but it does not add migrations or backend routes in this patch.

The tracker records `run_id`, `source_id`, `content_hash`, `processing_context_hash`, `agent_version`, `prompt_version`, model, binding/profile context, and a visit status:

```text
new_document
unchanged_seen
content_changed
context_changed
```

Preview the tracking plan without network calls:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py --print-agent-tracking-plan
```

Write a tracking report without appending the ledger:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --write-agent-tracking-report /tmp/skeinrank-agent-tracking-report.json
```

Append document visits to the local ledger explicitly:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --append-agent-tracking-ledger \
  --agent-tracking-ledger /tmp/skeinrank-agent-ledger.jsonl
```

The ledger is local-only and ignored by Git under `.cache/`. It helps the agent avoid reprocessing unchanged documents and gives a clear handoff point for a later PostgreSQL tracking model.

## Patch 41G — Proposal inbox / review workflow

Patch 41G adds an offline proposal inbox for agent-produced alias proposals. It turns saved LLM review and validation/submission reports into review cards with evidence previews, validation categories, recommended next actions, and optional local review decisions.

Preview the inbox plan without API calls:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py --print-proposal-inbox-plan
```

Build an inbox from a saved LLM review report and proposal submission report:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --llm-review-report /tmp/skeinrank-41a-llm-report.json \
  --proposal-submission-report /tmp/skeinrank-proposal-submission-report.json \
  --build-proposal-inbox
```

Apply local review decisions without mutating SkeinRank state:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --llm-review-report /tmp/skeinrank-41a-llm-report.json \
  --proposal-submission-report /tmp/skeinrank-proposal-submission-report.json \
  --review-decisions examples/agents/openrouter_alias_scout/review_decisions.example.jsonl \
  --write-proposal-inbox /tmp/skeinrank-proposal-inbox.json
```

Supported decision actions are `approve`, `reject`, `edit`, and `defer`. The inbox is offline-only in this patch: it does not approve proposals in the backend, does not apply dictionary changes, and does not publish snapshots.


## Patch 41H — Apply approved proposals + snapshot evaluation

Patch 41H adds an offline apply/evaluation step after the proposal inbox. It consumes locally approved inbox items, creates a governed apply plan, and optionally compares before/after snapshot artifacts. It does not mutate the dictionary, publish snapshots, or call SkeinRank APIs.

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py --print-approved-apply-plan

python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --proposal-inbox-report /tmp/proposal-inbox.json \
  --build-approved-apply-plan\n\npython examples/agents/openrouter_alias_scout/run_alias_scout.py \\
  --proposal-inbox-report /tmp/proposal-inbox.json \\
  --write-approved-apply-plan /tmp/approved-apply-plan.json

python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --approved-apply-plan /tmp/approved-apply-plan.json \
  --run-snapshot-evaluation
```

## Patch 41I — scheduled runner / worker mode

Patch 41I adds a production-friendly single-run cycle that can be invoked from cron,
Airflow, Prefect, GitHub Actions, Kubernetes CronJob, or Docker Compose without adding
an orchestration dependency.

Safe preview:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --print-scheduled-runner-plan
```

Run the safe offline cycle:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --run-agent-cycle
```

Write a final cycle report and per-step artifacts:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --write-agent-cycle-report examples/agents/openrouter_alias_scout/reports/scheduled/agent-cycle-report.json
```

The default cycle writes local reports only. It does not call OpenRouter, does not
submit proposals, does not mutate dictionaries, and does not publish snapshots. Live
steps require explicit flags such as `--agent-cycle-live-llm` and
`--agent-cycle-validate-proposals`; proposal submission still requires the explicit
`--agent-cycle-submit-proposals` flag plus the existing security/config guardrails.

## Patch 42A — full agent integration smoke test

Patch 42A adds a network-free smoke test for the full headless agent contour:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --print-integration-smoke-plan

python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --write-integration-smoke-report /tmp/skeinrank-agent-smoke.json \
  --integration-smoke-artifacts-dir /tmp/skeinrank-agent-smoke-artifacts
```

The smoke builds deterministic reports for demo discovery, synthetic LLM review,
synthetic validation, proposal inbox, approved apply planning, snapshot evaluation,
and a cycle summary. It does not call OpenRouter, Elasticsearch, or the SkeinRank API,
and it does not submit proposals, apply dictionary changes, or publish snapshots.
Use it as a fast CI/Airflow/Kubernetes preflight before running live 41I cycles.

## Patch 42B — Real Elasticsearch validation scenario

Patch 42B adds a reproducible real Elasticsearch/OpenSearch validation scenario for the alias scout. It uses a tiny fixture corpus, an isolated validation index, and the existing read-only Elasticsearch evidence connector.

Useful commands:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py --print-real-elasticsearch-validation-plan
python examples/agents/openrouter_alias_scout/run_alias_scout.py --write-real-elasticsearch-validation-fixtures
python examples/agents/openrouter_alias_scout/run_alias_scout.py --index-real-elasticsearch-validation-docs
python examples/agents/openrouter_alias_scout/run_alias_scout.py --run-real-elasticsearch-validation
```

The indexing command is explicit because it writes sample documents to the configured validation index. The validation command is read-only and does not call OpenRouter, SkeinRank API, proposal submission, runtime mutation, or snapshot publishing.

## Patch 42C — Reports/artifacts standard

Patch 42C standardizes agent run artifacts so cron, Airflow, GitHub Actions,
Docker Compose, and Kubernetes CronJobs can collect the same output shape.

Default layout:

```text
reports/<run_id>/
  manifest.json
  run_summary.json
  reports/
    demo_report.json
    tracking_report.json
    llm_review_report.json
    proposal_submission_report.json
    proposal_inbox_report.json
    approved_apply_plan.json
    snapshot_evaluation_report.json
    evaluation_report.json
    cycle_report.json
```

Preview the standard without network calls:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --print-artifacts-standard-plan
```

Run a safe cycle and produce a normalized manifest:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --write-agent-cycle-report /tmp/sr-cycle.json \
  --agent-cycle-artifacts-dir /tmp/sr-artifacts
```

The cycle report includes `artifact_manifest.path`, and the manifest lists every
artifact with `relative_path`, `schema_version`, size, and checksum.

## Patch 42E — Dictionary quickstart

Patch 42E adds a quickstart for importing a starter dictionary, creating an Elasticsearch binding, and exporting a headless source=latest snapshot artifact.

```bash
python run_alias_scout.py --print-dictionary-quickstart-plan
python run_alias_scout.py --write-dictionary-quickstart-payloads
python run_alias_scout.py --run-dictionary-quickstart
```

Use `--dictionary-quickstart-apply-import`, `--dictionary-quickstart-create-binding`, and `--dictionary-quickstart-export-snapshot` only after reviewing the validate-first report.

- Backend hardening note: after building an approved apply plan, preview the backend proposal batch before applying. Validation warnings require explicit reviewer opt-in via `allow_warnings`.

## Patch 42G — Runtime API final smoke

Use the runtime smoke after dictionary import/binding quickstart to verify that the profile is actually served by runtime APIs:

```bash
python run_alias_scout.py --print-runtime-api-smoke-plan
python run_alias_scout.py --write-runtime-api-smoke-report reports/runtime-smoke.json
```

Optional binding-scoped snapshot export smoke:

```bash
python run_alias_scout.py \
  --run-runtime-api-smoke \
  --runtime-smoke-binding-id 1 \
  --runtime-smoke-export-snapshot
```

The smoke is read-only: no OpenRouter calls, no proposals, no dictionary mutation, and no snapshot publishing.

### Patch 42D — Docker Compose full demo scenario

The `openrouter-agent-full-demo` Compose overlay provides a report-only full demo path for the OpenRouter alias scout. Use `--print-docker-demo-plan` to inspect the plan before running Docker Compose.



### Lifecycle-aware proposal review

When consuming SkeinRank suggestion responses, prefer `lifecycle_status`, `validation_status`, `can_approve`, and `can_apply` over raw validation JSON. Agent-created warning proposals should remain in the inbox unless a human or policy explicitly allows warnings.

### Idempotent apply flow

When proposal batches are applied through the governance API, retries with the same suggestion ids are safe: already-applied suggestions are reported as idempotent no-ops.

### Patch 43C — RBAC/scoped token enforcement for agent actions

Agent-facing APIs now enforce API-token scopes in addition to role checks. Session
login tokens and local-dev mode keep the existing role-based behavior, while
personal/service-account API tokens must include the required scopes.

Recommended service-account scopes:

```text
agent:runs:read
agent:runs:write
agent:tracking:read
agent:tracking:write
agent:tools:read
agent:tools:validate
agent:tools:suggest
agent:tools:explain
```

This keeps scheduled agents and CI jobs least-privileged: read-only jobs can list
runs and tracking records, validation-only jobs can call `validate-alias`, and
proposal-writing jobs must explicitly carry `agent:tools:suggest`.


## Patch 48B — OpenRouter live pilot mode

Patch 48B adds OpenRouter live pilot mode for manual, cost-safe checks of the alias scout against a real model. The default flow is still safe: it can prepare proposal payloads, but it does not approve/apply proposals, publish snapshots, or write dictionaries directly.

Preview the plan without network calls:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --print-openrouter-live-pilot-plan \
  --max-candidates 1 \
  --max-llm-calls 1
```

Run a tiny live pilot with a local key:

```bash
OPENROUTER_API_KEY=sk-or-... \
python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --run-openrouter-live-pilot
```

Or write the report to disk:

```bash
OPENROUTER_API_KEY=sk-or-... \
python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --run-openrouter-live-pilot \
  --write-openrouter-live-pilot-report \
  examples/agents/openrouter_alias_scout/reports/live-pilot/openrouter-live-pilot-report.json \
  --max-candidates 1 \
  --max-llm-calls 1
```

Report schema: `skeinrank.openrouter_live_pilot_report.v1`. When the report is written to disk, the CLI also prints a short operator summary to stdout.

Use `--pilot-validate-proposals` only when the Governance API is running and the agent has a scoped token for validation. Validation now preflights `/livez` before the OpenRouter call, so a stopped API fails fast without spending model budget. Proposal submission requires an additional explicit `--pilot-submit-proposals` flag and still creates pending suggestions only.


### Patch 49D — Live OpenRouter validated pilot

Adds an explicit validate-only live pilot flow for OpenRouter proposals against the SkeinRank Governance API. Use `make benchmark-agent-live-validated-pilot-plan` to preview and `make benchmark-agent-live-validated-pilot-report` or `make benchmark-agent-live-validated-pilot-stack` for guarded live validation. Reports include `validated_pilot` diagnostics and keep runtime mutation disabled.


### Validated pilot stack auth

`make benchmark-agent-live-validated-pilot-stack` starts the isolated benchmark
stack, logs in with the benchmark admin credentials from
`deploy/docker/benchmark.env.example`, and passes the temporary token to the
agent through `SKEINRANK_AGENT_API_TOKEN`. Manual validated runs still require
you to provide your own token when Governance API auth is enabled.

### Patch 53A.1 — validated pilot preflight hotfix

Validated live pilots now verify the `validate-alias` tool before any OpenRouter call. The preflight is read-only and uses a synthetic alias validation payload to confirm that the selected profile/binding context is available. If the Governance API returns 404, the runner fails before spending LLM budget and suggests seeding the benchmark stack or passing an existing `--profile-name` / `--binding-id`.

## Patch 57A — Model provider abstraction

Patch 57A adds `model_provider.py`, a small provider abstraction for chat-completion backends. OpenRouter remains the default production adapter, but the workflow can now accept a provider object through the same `create_chat_completion(...)` interface.

Preview the configured provider without network calls:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --print-model-provider-plan
```

The response schema is `skeinrank.model_provider_plan.v1`. It redacts secrets and keeps live execution behind the existing explicit `--llm-review` / live-pilot flags.
