# OpenRouter alias scout example

This example shows a safe agent-assisted terminology discovery workflow for SkeinRank. It mines failed queries, samples compact evidence, asks a bounded OpenRouter/OpenAI-compatible model for structured alias judgments, validates those judgments through the Governance API, and keeps production changes proposal-first.

The safety rule stays unchanged:

```text
LLM / agent -> proposal -> validation -> review/policy -> snapshot -> runtime
```

Agents must not mutate production terminology directly. They can only validate aliases, explain queries, and submit pending proposals through the `/v1/tools/*` facade when submission is explicitly enabled.

For the full operator guide, see `docs/guides/openrouter-agent.md`.

## Files

| File | Purpose |
| --- | --- |
| `agent_config.example.json` | Local runner config. JSON only; no secrets. |
| `env.example` | Environment variable names for local testing. |
| `failed_queries.example.jsonl` | Tiny failed-query sample for local candidate discovery. |
| `evidence_records.example.jsonl` | Tiny search-log/document snippet sample for local evidence windows. |
| `evaluation_outcomes.example.jsonl` | Optional human/policy outcomes for evaluation reports. |
| `review_decisions.example.jsonl` | Optional local review decisions for proposal inbox reports. |
| `candidate_discovery.py` | Dependency-light failed-query candidate mining, pruning, scoring, and fact-pack helpers. |
| `evidence_sampler.py` | Dependency-light compact window sampler for positive, negative, and cluster-aware candidate evidence packs. |
| `demo_report.py` | Local E2E demo report builder for discovery + evidence + review queue output. |
| `openrouter_client.py` | Dependency-light OpenRouter `/chat/completions` client with testable transport injection. |
| `alias_scout_workflow.py` | LangGraph-ready state-machine workflow for LLM review and proposal payload preparation. |
| `model_provider.py` | Provider abstraction for OpenRouter, OpenAI-compatible, and local endpoints. |
| `skeinrank_client.py` | Dependency-light client for `/v1/tools/*`. |
| `openrouter_tools.py` | OpenRouter/OpenAI-compatible tool schemas for the existing SkeinRank tools. |
| `prompts.py` | System prompt, alias-review prompt builder, and compact candidate pack helper. |
| `structured_output.py` | Strict parser for `propose`, `reject`, and `needs_evidence` judgments. |
| `proposal_submission.py` | Safe validation/submission bridge for ready proposal payloads. |
| `proposal_inbox.py` | Local inbox builder for human review of agent-produced proposals. |
| `approved_apply.py` | Offline apply-plan and snapshot-evaluation report helpers. |
| `scheduled_runner.py` | One-shot cycle runner for cron, Airflow, Prefect, GitHub Actions, or Kubernetes CronJob. |
| `artifact_standard.py` | Standard run artifact layout and manifest helpers. |
| `deployment_recipe.py` | Offline Docker Compose deployment recipe report. |
| `docker_demo_scenario.py` | Full local Docker Compose demo plan. |
| `real_es_validation.py` | Reproducible Elasticsearch/OpenSearch validation scenario. |
| `dictionary_quickstart.py` | First-run dictionary import, binding, and snapshot export quickstart. |
| `runtime_api_smoke.py` | Read-only runtime canonicalization/query-plan smoke. |
| `run_alias_scout.py` | CLI entrypoint for plans, reports, smoke tests, and gated live review. |

## Quick local path

From the repository root:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py --dry-run-plan
python examples/agents/openrouter_alias_scout/run_alias_scout.py --discover-candidates
python examples/agents/openrouter_alias_scout/run_alias_scout.py --print-sample-candidate-pack
python examples/agents/openrouter_alias_scout/run_alias_scout.py --sample-evidence
python examples/agents/openrouter_alias_scout/run_alias_scout.py --print-sample-evidence-pack
python examples/agents/openrouter_alias_scout/run_alias_scout.py --run-demo-report
python examples/agents/openrouter_alias_scout/run_alias_scout.py --print-demo-review-prompt
```

Makefile helper:

```bash
make agent-demo
```

The local demo uses `skeinrank.agent_demo_report.v1`. The local demo is network-free: it does not call OpenRouter, does not call Elasticsearch, does not call the SkeinRank API, and does not submit proposals. Candidate discovery ranks surfaces with weighted failed-query support, surface classes, background-language penalties, `jargon_score`, and lightweight tokenizer-risk signals so compact aliases, code-shaped names, and conservative bigram/trigram phrases are prioritized before generic operational words. It also groups related surfaces into candidate clusters before LLM review, so the model can inspect an entity-style pack instead of isolated words. True `oov_score` and `token_fragmentation_score` stay empty in this standalone example because no embedding tokenizer is loaded.

## Tool schemas and prompts

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py --print-tool-schemas
python examples/agents/openrouter_alias_scout/run_alias_scout.py --print-system-prompt
python examples/agents/openrouter_alias_scout/run_alias_scout.py --print-sample-review-prompt
```

The model-facing tools are:

```text
skeinrank_list_bindings
skeinrank_explain_query
skeinrank_validate_alias
skeinrank_submit_alias_proposal
```

They map to existing API routes and do not introduce new backend calls:

```text
GET  /v1/tools/bindings
POST /v1/tools/explain-query
POST /v1/tools/validate-alias
POST /v1/tools/suggest-alias
```

## Live model review

Preview the workflow first:

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

Write a report:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --write-llm-review-report /tmp/skeinrank-alias-scout-llm-report.json
```

The report schema is `skeinrank.agent_llm_review_report.v1`. Structured judgments use `propose | reject | needs_evidence`. Each reviewed item also includes a `confidence_decision` block. If multiple independent judgments are configured and the model does not converge, the runner abstains with `needs_evidence` instead of preparing a proposal. Proposal submission remains disabled unless config and security checks explicitly allow it. The workflow is LangGraph-ready without requiring the `langgraph` package.


When the workflow records LLM reviews and proposal attempts through the Governance
API, those rows also create DB-backed review dataset events. Human review labels
are attached when pending proposals are approved or rejected, and JSONL can be
exported from `/v1/agents/review-dataset/events/export.jsonl` for later evaluation
or fine-tuning.

Canonical migrations use the same review boundary. If a scout decides that
`checkout` is now documented as `payments-core`, it should create a pending
canonical migration through the Governance API instead of changing dictionaries
directly. Reviewers can inspect the migration plan, approve with an explicit
warning override, and then publish a normal runtime snapshot.

## Security, budgets, and evaluation

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py --print-security-profile
python examples/agents/openrouter_alias_scout/run_alias_scout.py --check-security-profile
python examples/agents/openrouter_alias_scout/run_alias_scout.py --print-budget-cache-plan
python examples/agents/openrouter_alias_scout/run_alias_scout.py --clear-llm-cache
python examples/agents/openrouter_alias_scout/run_alias_scout.py --run-evaluation-report
# Live mode should use --max-llm-calls and --max-run-cost-usd.
```

Schemas used by these reports:

```text
skeinrank.agent_security_profile.v1
skeinrank.agent_budget_cache_plan.v1
skeinrank.agent_evaluation_report.v1
```


## Additional local plans and smoke paths

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py --print-canonical-hints
# Example canonical hints include kubernetes, postgresql, elasticsearch, and rabbitmq.
python examples/agents/openrouter_alias_scout/run_alias_scout.py --print-new-alias-smoke-plan
python examples/agents/openrouter_alias_scout/run_alias_scout.py --run-new-alias-smoke-test
python examples/agents/openrouter_alias_scout/run_alias_scout.py --print-agent-tracking-plan
python examples/agents/openrouter_alias_scout/run_alias_scout.py --append-agent-tracking-ledger
python examples/agents/openrouter_alias_scout/run_alias_scout.py --print-proposal-inbox-plan
python examples/agents/openrouter_alias_scout/run_alias_scout.py --print-integration-smoke-plan
python examples/agents/openrouter_alias_scout/run_alias_scout.py --write-integration-smoke-report /tmp/skeinrank-agent-smoke.json
```

These commands are report-first. They do not approve changes, publish snapshots, or mutate runtime bindings.

## Proposal workflow

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --llm-review-report /tmp/skeinrank-alias-scout-llm-report.json \
  --print-proposal-submission-plan
python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --llm-review-report /tmp/skeinrank-alias-scout-llm-report.json \
  --validate-ready-proposals
python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --proposal-submission-report /tmp/skeinrank-proposal-submission.json \
  --build-proposal-inbox
python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --proposal-submission-report /tmp/skeinrank-proposal-submission.json \
  --write-proposal-inbox /tmp/skeinrank-proposal-inbox.json
python examples/agents/openrouter_alias_scout/run_alias_scout.py --print-approved-apply-plan
python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --proposal-inbox-report /tmp/skeinrank-proposal-inbox.json \
  --build-approved-apply-plan
python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --approved-apply-plan /tmp/skeinrank-approved-apply-plan.json \
  --before-snapshot /tmp/snapshot-before.json \
  --after-snapshot /tmp/snapshot-after.json \
  --run-snapshot-evaluation
```

Validation statuses are classified before submission. `--submit-ready-proposals` and `--submit-new-alias-smoke-test` are explicit gates. They create pending proposals only; they do not publish snapshots or mutate runtime bindings.

## Elasticsearch and runtime validation

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py --print-elasticsearch-evidence-plan
python examples/agents/openrouter_alias_scout/run_alias_scout.py --sample-evidence-from-elasticsearch
python examples/agents/openrouter_alias_scout/run_alias_scout.py --print-real-elasticsearch-validation-plan
python examples/agents/openrouter_alias_scout/run_alias_scout.py --run-real-elasticsearch-validation
python examples/agents/openrouter_alias_scout/run_alias_scout.py --print-runtime-api-smoke-plan
python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --write-runtime-api-smoke-report /tmp/sr-runtime-smoke.json
```

Dictionary quickstart:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py --print-dictionary-quickstart-plan
python examples/agents/openrouter_alias_scout/run_alias_scout.py --write-dictionary-quickstart-payloads
python examples/agents/openrouter_alias_scout/run_alias_scout.py --run-dictionary-quickstart
```

## Scheduled jobs and artifacts

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py --print-scheduled-runner-plan
python examples/agents/openrouter_alias_scout/run_alias_scout.py --run-agent-cycle
python examples/agents/openrouter_alias_scout/run_alias_scout.py --print-artifacts-standard-plan
python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --write-agent-cycle-report /tmp/sr-cycle.json \
  --agent-cycle-artifacts-dir /tmp/sr-artifacts
```

Standard layout:

```text
reports/<run_id>/
  manifest.json
  run_summary.json
  reports/<artifact>.json
```

## Deployment

Inspect the deployment recipe (`skeinrank.agent_deployment_recipe.v1`):

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py --print-deployment-recipe
make agent-compose-config
```

Full local Docker demo:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py --print-docker-demo-plan
deploy/docker/scripts/openrouter-agent-full-demo.sh config
deploy/docker/scripts/openrouter-agent-full-demo.sh run
```

Related docs:

```text
docs/deployment/openrouter-alias-scout.md
docs/deployment/openrouter-agent-full-demo.md
```

## Live pilot

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py --print-openrouter-live-pilot-plan
python examples/agents/openrouter_alias_scout/run_alias_scout.py --run-openrouter-live-pilot
python examples/agents/openrouter_alias_scout/run_alias_scout.py --print-openrouter-validated-pilot-plan
python examples/agents/openrouter_alias_scout/run_alias_scout.py --run-openrouter-validated-pilot
```

Live pilot reports use `skeinrank.openrouter_live_pilot_report.v1`; validated pilot reports use `skeinrank.openrouter_validated_pilot_report.v1`.

Optional gates:

```bash
--pilot-validate-proposals
--pilot-submit-proposals
--pilot-use-tools
--max-proposals 3
```

## Provider adapters

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py --print-model-provider-plan
python examples/agents/openrouter_alias_scout/run_alias_scout.py --print-company-model-integration-plan
```

Supported provider types:

```text
openrouter
openai_compatible
local_endpoint
```

Local evidence mode has no Elasticsearch calls, no OpenRouter calls, and no proposal submission by default. Evidence packs now separate positive windows from negative/contrast windows when known conflicts are provided, include nearby terms from each window, and can carry the candidate cluster that will be shown to the model.
The local foundation path does not call OpenRouter yet; live model calls are enabled only through the guarded live-pilot commands below.
