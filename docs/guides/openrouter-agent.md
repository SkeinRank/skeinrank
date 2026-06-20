# OpenRouter alias scout guide

The OpenRouter alias scout is a reference workflow for agent-assisted terminology discovery. It helps teams mine failed queries and evidence snippets, ask a bounded LLM for structured alias judgments, validate those judgments through the Governance API, and keep production changes proposal-first.

The invariant is intentionally strict:

```text
LLM / agent -> proposal -> validation -> review / policy -> snapshot -> runtime
```

Agents can collect evidence, prepare proposal payloads, validate aliases, and create pending proposals when explicitly enabled. They do not approve proposals, publish snapshots, write dictionaries directly, or mutate runtime bindings.

## Where the example lives

```text
examples/agents/openrouter_alias_scout/
  agent_config.example.json
  env.example
  failed_queries.example.jsonl
  evidence_records.example.jsonl
  evaluation_outcomes.example.jsonl
  review_decisions.example.jsonl
  run_alias_scout.py
```

Related deployment files:

```text
deploy/docker/openrouter-alias-scout.Dockerfile
deploy/docker/openrouter-alias-scout.compose.yml
deploy/docker/openrouter-alias-scout.env.example
deploy/docker/openrouter-agent-full-demo.compose.yml
deploy/docker/openrouter-agent-full-demo.env.example
deploy/docker/scripts/openrouter-agent-full-demo.sh
```

## Safety model

The reference agent is safe by default:

- local discovery and evidence sampling do not call OpenRouter;
- default Compose recipes do not call OpenRouter;
- proposal submission is disabled unless explicitly enabled;
- runtime mutation and snapshot publication are not available from the agent;
- live model review is budgeted and can use a local cache;
- the Governance API remains the source of truth for validation and proposal state.

Blocked actions for the reference agent:

```text
direct_dictionary_write
snapshot_publish
direct_git_push
runtime_mutation
```

Recommended service-account scopes for scheduled jobs:

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

Use fewer scopes for read-only or validation-only jobs.

## Local configuration

Copy or export local values from the example environment file. Never commit real secrets.

```bash
export SKEINRANK_AGENT_API_URL=http://127.0.0.1:8010
export SKEINRANK_AGENT_ROLE=contributor
export SKEINRANK_AGENT_SERVICE_ACCOUNT=openrouter-alias-scout
export SKEINRANK_AGENT_API_TOKEN=...
export OPENROUTER_API_KEY=...
export OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
export OPENROUTER_MODEL=openai/gpt-4o-mini
```

The checked-in `agent_config.example.json` keeps `llm_review.submit_proposals` disabled. If proposal submission is enabled without a scoped token and explicit security policy, the security check exits non-zero before live model execution.

## Dry-run plan

Preview the runner shape without network calls:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py --dry-run-plan
```

The output schema is `skeinrank.agent_run_plan.v1`.

## Tool schemas and prompts

Inspect the OpenRouter/OpenAI-compatible tools and prompts:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py --print-tool-schemas
python examples/agents/openrouter_alias_scout/run_alias_scout.py --print-system-prompt
python examples/agents/openrouter_alias_scout/run_alias_scout.py --print-sample-review-prompt
```

The exposed tool names are:

```text
skeinrank_list_bindings
skeinrank_explain_query
skeinrank_validate_alias
skeinrank_submit_alias_proposal
```

They map to the existing Governance API facade:

```text
GET  /v1/tools/bindings
POST /v1/tools/explain-query
POST /v1/tools/validate-alias
POST /v1/tools/suggest-alias
```

`validate-alias` and `explain-query` are read-only. `suggest-alias` creates a pending proposal with idempotency support; it does not approve, apply, or publish a snapshot.

## Candidate discovery

Mine alias-like surfaces from failed-query JSONL before any LLM call:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py --discover-candidates
python examples/agents/openrouter_alias_scout/run_alias_scout.py --print-sample-candidate-pack
```

The report schema is `skeinrank.agent_candidate_discovery.v1`. It extracts surfaces such as `pg`, `k8s`, `PAY-1842`, `checkout-v2`, `payment_service`, and conservative bigram/trigram phrases, prunes configured noise and known terms, and produces compact candidate packs. Candidate scoring includes a compact breakdown with weighted failed-query support, surface class, background-language penalty, `jargon_score`, and lightweight tokenizer-risk signals. The report also includes candidate clusters, grouping related surfaces before LLM review so the model receives an entity-style context instead of a flat list of words. The standalone scout keeps true `oov_score` and `token_fragmentation_score` empty until a tokenizer provider is connected, so model-specific risk is never implied when it was not measured.

## Compact evidence windows

Sample short evidence windows around discovered candidates:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py --sample-evidence
python examples/agents/openrouter_alias_scout/run_alias_scout.py --print-sample-evidence-pack
```

The report schema is `skeinrank.agent_evidence_sampling.v1`. The sampler enforces `max_docs`, `max_windows`, and `max_total_chars` limits so the model never receives full documents by default. Candidate packs separate positive evidence from negative/contrast evidence when conflicts are known, attach nearby terms from each window, and can include the candidate cluster used for review.

## Elasticsearch / OpenSearch evidence

The optional evidence connector can search a configured validation index and normalize hits into the same evidence-record format:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py --print-elasticsearch-evidence-plan
python examples/agents/openrouter_alias_scout/run_alias_scout.py --sample-evidence-from-elasticsearch
python examples/agents/openrouter_alias_scout/run_alias_scout.py --write-elasticsearch-evidence-records /tmp/sr-es-evidence.jsonl
```

Common options:

```bash
--elasticsearch-url http://127.0.0.1:9200
--elasticsearch-index skeinrank_agent_demo
--elasticsearch-text-field text
--elasticsearch-max-docs 20
--elasticsearch-api-key-env ELASTICSEARCH_API_KEY
```

This connector is read-only for search. The fixture indexing commands in the validation scenario write only to the configured validation index.

## Demo report

Run the deterministic local report that joins discovery, evidence windows, candidate packs, and review prompt preparation:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py --run-demo-report
python examples/agents/openrouter_alias_scout/run_alias_scout.py --print-demo-review-prompt
python examples/agents/openrouter_alias_scout/run_alias_scout.py --write-demo-report /tmp/skeinrank-alias-scout-report.json
```

Makefile helper:

```bash
make agent-demo
```

The report schema is `skeinrank.agent_demo_report.v1`. It is local-only: no OpenRouter calls, no Elasticsearch calls, no SkeinRank API calls, and no proposals are submitted.

## Live OpenRouter review

Preview the LangGraph-ready flow without network calls:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py --print-llm-review-plan
```

Run a bounded live review:

```bash
OPENROUTER_API_KEY=... python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --llm-review \
  --model openai/gpt-4o-mini \
  --max-candidates 3 \
  --max-llm-calls 3 \
  --max-run-cost-usd 0.01
```

Write the report to disk:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --write-llm-review-report /tmp/skeinrank-alias-scout-llm-report.json
```

The report schema is `skeinrank.agent_llm_review_report.v1`. The model must return a strict structured judgment:

```text
action: propose | reject | needs_evidence
confidence: 0..1
reason: string
risk_flags: string[]
```

`propose` also requires `alias_value`, `canonical_value`, and `slot`. Proposal payloads still have to pass Governance API validation before they can be saved.

## Model provider options

OpenRouter is the default adapter, but the runner can also use OpenAI-compatible company endpoints and local endpoint adapters.

Inspect the provider plans:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py --print-model-provider-plan
python examples/agents/openrouter_alias_scout/run_alias_scout.py --print-company-model-integration-plan
```

Supported operator-facing provider types include:

```text
openrouter
openai_compatible
local_endpoint
```

For a local OpenAI-compatible endpoint, configure:

```bash
export SKEINRANK_MODEL_PROVIDER_TYPE=local_endpoint
export SKEINRANK_MODEL_PROVIDER_BASE_URL=http://127.0.0.1:8000/v1
export SKEINRANK_MODEL_PROVIDER_MODEL=local-model
```

## Security profile

Print or enforce the service-account security profile:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py --print-security-profile
python examples/agents/openrouter_alias_scout/run_alias_scout.py --check-security-profile
```

The output schema is `skeinrank.agent_security_profile.v1`. It redacts secret environment variables, verifies the configured role, documents allowed `/v1/tools/*` paths, and blocks direct runtime mutation.

## Budget and cache controls

Inspect budget/cache behavior or clear the local response cache:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py --print-budget-cache-plan
python examples/agents/openrouter_alias_scout/run_alias_scout.py --clear-llm-cache
```

Live-review controls:

```bash
--max-llm-calls 3
--max-run-cost-usd 0.01
--no-llm-cache
--force-refresh-cache
```

The plan schema is `skeinrank.agent_budget_cache_plan.v1`. Cached responses never mutate runtime state.

## Evaluation loop

Score the local demo pipeline or a saved LLM review report without calling external services:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py --run-evaluation-report
python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --llm-review-report /tmp/skeinrank-alias-scout-llm-report.json \
  --run-evaluation-report
python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --write-evaluation-report /tmp/skeinrank-alias-scout-evaluation.json
```

The output schema is `skeinrank.agent_evaluation_report.v1`. It reports evidence coverage, action mix, proposal-ready counts, cost/cache summary, optional human/policy outcomes, and a quality gate.

## Deployment recipe

Inspect the safe Docker Compose deployment recipe:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py --print-deployment-recipe
python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --write-deployment-recipe examples/agents/openrouter_alias_scout/reports/deployment-recipe.json
```

Makefile helpers:

```bash
make agent-deploy-plan
make agent-compose-config
```

Deployment documentation:

```text
docs/deployment/openrouter-alias-scout.md
docs/deployment/openrouter-agent-full-demo.md
```

The deployment report schema is `skeinrank.agent_deployment_recipe.v1`. The reference service defaults to an offline evaluation report; live model review must be enabled explicitly with bounded budget settings.

## Canonical hints

Print configured canonical hints and a sample evidence pack:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py --print-canonical-hints
python examples/agents/openrouter_alias_scout/run_alias_scout.py --print-sample-evidence-pack
```

The output schema is `skeinrank.agent_canonical_hints.v1`. Candidate packs can include `possible_canonical`, `slot`, `canonical_hint`, `canonical_candidates`, and `known_canonicals` for terms such as `kubernetes`, `postgresql`, `elasticsearch`, and `rabbitmq`.

## Proposal validation and submission

Preview proposal validation from a saved LLM report:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --llm-review-report /tmp/skeinrank-alias-scout-llm-report.json \
  --print-proposal-submission-plan
```

Validate ready proposals through the Governance API without saving them:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --llm-review-report /tmp/skeinrank-alias-scout-llm-report.json \
  --validate-ready-proposals
```

Create pending proposals only when the security profile and config explicitly allow it:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --llm-review-report /tmp/skeinrank-alias-scout-llm-report.json \
  --submit-ready-proposals \
  --write-proposal-submission-report /tmp/skeinrank-proposal-submission.json
```

Validation statuses are classified before submission:

```text
passed -> eligible for optional submission
existing alias warning -> idempotent_existing_alias
slot mismatch warning -> manual_review_required
blocked -> blocked
```

## New-alias smoke path

Run a controlled smoke path for a brand-new alias proposal:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py --print-new-alias-smoke-plan
python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --write-new-alias-smoke-llm-report /tmp/skeinrank-new-alias-smoke-llm.json
python examples/agents/openrouter_alias_scout/run_alias_scout.py --run-new-alias-smoke-test
python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --submit-new-alias-smoke-test \
  --write-new-alias-smoke-report /tmp/skeinrank-new-alias-smoke-report.json
```

The submit command still creates only a pending proposal and verifies idempotent retry behavior.

## Agent run and document tracking

Preview or write local run/document tracking artifacts:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py --print-agent-tracking-plan
python examples/agents/openrouter_alias_scout/run_alias_scout.py --write-agent-tracking-report /tmp/sr-agent-tracking.json
python examples/agents/openrouter_alias_scout/run_alias_scout.py --append-agent-tracking-ledger
```

Optional ledger path:

```bash
--agent-tracking-ledger .cache/openrouter_alias_scout_run_ledger.jsonl
```

The local tracking contract is DB-ready: scheduled runs can attach source documents, content hashes, processing-context hashes, candidate observations, LLM reviews, and proposal attempts to one run identity.

## Proposal inbox and review workflow

Build a local proposal inbox from saved reports:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py --print-proposal-inbox-plan
python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --proposal-submission-report /tmp/skeinrank-proposal-submission.json \
  --build-proposal-inbox
python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --proposal-submission-report /tmp/skeinrank-proposal-submission.json \
  --review-decisions examples/agents/openrouter_alias_scout/review_decisions.example.jsonl \
  --write-proposal-inbox /tmp/skeinrank-proposal-inbox.json
```

Useful controls:

```bash
--max-inbox-items 50
```

The inbox remains offline. It records review intent and evidence context; governed apply/snapshot steps remain separate.

## Approved apply plan and snapshot evaluation

Create an offline apply plan from locally approved inbox items:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py --print-approved-apply-plan
python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --proposal-inbox-report /tmp/skeinrank-proposal-inbox.json \
  --build-approved-apply-plan
python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --proposal-inbox-report /tmp/skeinrank-proposal-inbox.json \
  --write-approved-apply-plan /tmp/skeinrank-approved-apply-plan.json
```

Compare before/after snapshot artifacts:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --approved-apply-plan /tmp/skeinrank-approved-apply-plan.json \
  --before-snapshot /tmp/snapshot-before.json \
  --after-snapshot /tmp/snapshot-after.json \
  --run-snapshot-evaluation
```

Schemas:

```text
skeinrank.agent_approved_apply_plan.v1
skeinrank.agent_snapshot_evaluation_report.v1
```

The apply plan is a report, not a direct dictionary mutation.

## Scheduled runner / worker mode

Run one agent cycle suitable for cron, Airflow, Prefect, GitHub Actions, or a Kubernetes CronJob:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py --print-scheduled-runner-plan
python examples/agents/openrouter_alias_scout/run_alias_scout.py --run-agent-cycle
python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --run-agent-cycle \
  --write-agent-cycle-report /tmp/sr-cycle.json \
  --agent-cycle-artifacts-dir /tmp/sr-artifacts
```

Optional live mode is explicit:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --run-agent-cycle \
  --agent-cycle-live-llm \
  --max-llm-calls 3 \
  --max-run-cost-usd 0.05
```

Validation and submission remain separate gates:

```bash
--agent-cycle-validate-proposals
--agent-cycle-submit-proposals
--agent-cycle-append-tracking-ledger
--agent-cycle-fail-on-needs-review
```

## Integration smoke test

Run the network-free smoke path for the full headless agent contour:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py --print-integration-smoke-plan
python examples/agents/openrouter_alias_scout/run_alias_scout.py --run-integration-smoke-test
python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --write-integration-smoke-report /tmp/skeinrank-agent-smoke.json \
  --integration-smoke-artifacts-dir /tmp/skeinrank-agent-smoke-artifacts
```

The smoke creates artifacts for candidate/evidence discovery, synthetic LLM review, validation, proposal inbox, approved apply planning, snapshot evaluation, agent evaluation, and scheduled-cycle summary. It keeps OpenRouter, Elasticsearch, SkeinRank API calls, proposal submission, runtime mutation, and snapshot publication disabled.

## Real Elasticsearch validation scenario

Generate fixtures, index a tiny sample corpus into an isolated local Elasticsearch/OpenSearch index, and run read-only evidence validation:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py --print-real-elasticsearch-validation-plan
python examples/agents/openrouter_alias_scout/run_alias_scout.py --write-real-elasticsearch-validation-fixtures
python examples/agents/openrouter_alias_scout/run_alias_scout.py --index-real-elasticsearch-validation-docs
python examples/agents/openrouter_alias_scout/run_alias_scout.py --run-real-elasticsearch-validation
python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --write-real-elasticsearch-validation-report /tmp/sr-real-es-validation.json
```

Useful controls:

```bash
--real-es-validation-artifacts-dir /tmp/sr-real-es-validation
--real-es-validation-reset-index
```

## Standard report artifacts

Use the standard artifact layout for scheduled jobs and external orchestrators:

```text
reports/<run_id>/
  manifest.json
  run_summary.json
  reports/<artifact>.json
```

Commands:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py --print-artifacts-standard-plan
python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --write-artifacts-manifest \
  --artifacts-root-dir reports \
  --artifacts-run-id local-demo
```

The manifest layout schema is `skeinrank.agent_artifacts_layout.v1`.

## Dictionary quickstart

Use the first-run quickstart before enabling discovery agents:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py --print-dictionary-quickstart-plan
python examples/agents/openrouter_alias_scout/run_alias_scout.py --write-dictionary-quickstart-payloads
python examples/agents/openrouter_alias_scout/run_alias_scout.py --run-dictionary-quickstart
python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --write-dictionary-quickstart-report /tmp/sr-dictionary-quickstart.json
```

Optional controls:

```bash
--dictionary-quickstart-artifacts-dir reports/dictionary-quickstart
--dictionary-quickstart-index skeinrank_agent_demo
--dictionary-quickstart-profile infra_incidents
--dictionary-quickstart-apply-import
--dictionary-quickstart-create-binding
--dictionary-quickstart-export-snapshot
--dictionary-quickstart-binding-id <id>
```

The flow uses existing Governance API endpoints only:

```text
POST /v1/console/dictionary/validate
POST /v1/console/dictionary/import
POST /v1/governance/elasticsearch/bindings
GET  /v1/headless/snapshots/export?source=latest
```

Safe defaults are validation-first: no OpenRouter calls, no runtime mutation, and no snapshot publishing.

## Runtime API smoke

Verify that governed terminology is served by runtime APIs:

```bash
cd packages/skeinrank-governance-api
poetry run python ../../examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --print-runtime-api-smoke-plan
poetry run python ../../examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --write-runtime-api-smoke-report /tmp/sr-runtime-smoke.json
```

For binding-scoped smoke:

```bash
--runtime-smoke-binding-id <id>
--runtime-smoke-export-snapshot
--runtime-smoke-profile infra_incidents
--runtime-smoke-text "k8s pg timeout"
--runtime-smoke-query "k8s pg timeout"
```

The smoke is read-only and calls only canonicalization, query planning, and optional headless snapshot export.

## Docker Compose full demo

Inspect or run the local full demo scenario:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py --print-docker-demo-plan
deploy/docker/scripts/openrouter-agent-full-demo.sh config
deploy/docker/scripts/openrouter-agent-full-demo.sh run
```

Makefile helper:

```bash
make agent-docker-demo-config
```

The full demo combines the local stack with a one-shot agent service that indexes validation documents into an isolated Elasticsearch index and writes standard artifacts under `examples/agents/openrouter_alias_scout/reports/docker-demo/`. By default it does not call OpenRouter and does not submit proposals.

## Database-backed agent registry

The Governance API can persist agent run metadata and tracking records so scheduled runners do not rely only on local JSONL files. The registry supports:

- top-level agent runs with profile, binding, model, lifecycle status, and artifact URIs;
- document visits with content and processing-context hashes;
- candidate observations, evidence metadata, LLM reviews, and proposal attempts;
- retry-safe proposal attempt status for idempotent workers.

Before scheduled agents run proposal/apply workflows, verify migration state:

```bash
cd packages/skeinrank-governance-api
poetry run python -m skeinrank_governance_api.migrations upgrade head
poetry run python -m skeinrank_governance_api.migrations check
```

For running services, use:

```text
GET /schema/health
GET /readyz
```

`/readyz` incorporates schema-health checks so agents do not start against a stale or partially migrated control-plane schema.

## Live pilot mode

For manual, cost-safe checks against a real model, inspect and run the live pilot flow:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py --print-openrouter-live-pilot-plan
python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --run-openrouter-live-pilot \
  --write-openrouter-live-pilot-report /tmp/sr-openrouter-live-pilot.json
```

Validated pilot flow:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py --print-openrouter-validated-pilot-plan
python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --run-openrouter-validated-pilot \
  --write-openrouter-validated-pilot-report /tmp/sr-openrouter-validated-pilot.json
```

Optional gates:

```bash
--pilot-validate-proposals
--pilot-submit-proposals
--pilot-use-tools
--max-proposals 3
```

The default pilot can prepare proposal payloads, but it does not approve/apply proposals, publish snapshots, or write dictionaries directly.
