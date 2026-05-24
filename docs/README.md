# SkeinRank documentation

This directory keeps repository-level documentation for developers, operators, and contributors. The public product site is available at <https://skeinrank.github.io>.

## Start here

- [`overview.md`](overview.md) — what SkeinRank is, what it solves, and how the repository is organized.
- [`concepts/terminology-control-plane.md`](concepts/terminology-control-plane.md) — terminology, aliases, guardrails, evidence, and snapshots.
- [`concepts/profiles-bindings-snapshots.md`](concepts/profiles-bindings-snapshots.md) — the production runtime model.
- [`concepts/headless-runtime-contracts.md`](concepts/headless-runtime-contracts.md) — headless-first contract map for runtime, agents, snapshots, and UI scope.
- [`concepts/dictionary-spec-v1.md`](concepts/dictionary-spec-v1.md) — stable dictionary import/export contract with `schema_version`.
- [`concepts/coverage-framework.md`](concepts/coverage-framework.md) — slots, tags, ambiguous aliases, binding policies, and evaluation guardrails.
- [`adr/0001-headless-runtime-contracts.md`](adr/0001-headless-runtime-contracts.md) — accepted architecture decision for headless runtime boundaries.
- [`guides/core-sdk-and-cli.md`](guides/core-sdk-and-cli.md) — local dictionary validation, extraction, canonicalization, and document extraction.
- [`guides/governance-console.md`](guides/governance-console.md) — governance API/UI workflow.
- [`guides/coverage-framework.md`](guides/coverage-framework.md) — headless workflow for tags, conflicts, ambiguous candidates, policies, and before/after evaluation.
- [`../examples/agents/openrouter_alias_scout`](../examples/agents/openrouter_alias_scout) — reference OpenRouter alias scout foundation and SkeinRank REST client.
- [`guides/elasticsearch-enrichment.md`](guides/elasticsearch-enrichment.md) — Elasticsearch enrichment, dry-run, evidence, jobs, and cancellation.
- [`guides/development.md`](guides/development.md) — local development checks and package workflow.
- [`api/governance-api.md`](api/governance-api.md) — important HTTP surfaces and runtime endpoints.

## Deployment

- [`deployment/docker-compose.md`](deployment/docker-compose.md) — full Docker Compose dev stack.
- [`deployment/headless-quickstart.md`](deployment/headless-quickstart.md) — API/PostgreSQL-only golden path for headless integrations.
- [`deployment/security.md`](deployment/security.md) — production-oriented security baseline.
- [`deployment/observability.md`](deployment/observability.md) — logs, metrics, tracing, Prometheus, and Grafana.
- [`deployment/dev-stack-troubleshooting.md`](deployment/dev-stack-troubleshooting.md) — common local stack issues.


## Headless dictionary facade

Automation-first integrations should prefer the headless dictionary routes:

```text
POST /v1/headless/dictionaries/validate
POST /v1/headless/dictionaries/apply
GET  /v1/headless/dictionaries/export?profile_name=...
```

They share the same dictionary spec v1 payload as the console migration routes,
but are named for CI/CD, agents, and service-to-service workflows.

- Snapshot artifact export: `GET /v1/headless/snapshots/export?binding_id=...` and `skeinrank-migrate snapshot-export`.

- Runtime artifact file loader/cache: see `docs/concepts/headless-runtime-contracts.md`.

## Headless quickstart

Use `docker-compose.headless.yml` for the API/PostgreSQL-only Phase A path. See `deployment/headless-quickstart.md` for the dictionary apply -> binding -> snapshot artifact workflow.

## Agent MCP tools

Patch 37F adds a minimal MCP stdio adapter for agent workflows:

```bash
cd packages/skeinrank-governance-api
poetry run skeinrank-mcp --api-url http://127.0.0.1:8010
```

It exposes binding discovery, query explanation, alias validation, alias proposal
submission, and proposal status lookup. The adapter delegates to `/v1/tools/*`,
so agents still go through proposal validation and review rather than mutating
runtime terminology directly.

## OpenRouter alias scout foundation

Patch 40F adds a local reference runner under
`examples/agents/openrouter_alias_scout`. Patch 40G adds the OpenRouter-facing
contract layer: tool schemas, safety prompts, compact candidate-pack prompt
helpers, and strict structured output parsing. Patch 40H adds deterministic
failed-query candidate discovery and pruning before any LLM call. Patch 40I adds
compact evidence windows with `max_docs`, `max_windows`, and `max_total_chars`
limits. Patch 40K adds a local E2E demo report (`skeinrank.agent_demo_report.v1`)
that prepares a review queue and source-quality placeholder without calling
OpenRouter, Elasticsearch, or the SkeinRank API. Local previews are available
through `--print-tool-schemas`, `--print-system-prompt`,
`--print-sample-review-prompt`, `--discover-candidates`,
`--print-sample-candidate-pack`, `--sample-evidence`,
`--print-sample-evidence-pack`, `--run-demo-report`, and
`--print-demo-review-prompt`. See `docs/guides/openrouter-agent.md` for the
agent milestone walkthrough.

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

## Patch 40L — OpenRouter agent security profile

Patch 40L adds a safe service-account profile to the OpenRouter alias scout. The
runner can now print and validate a redacted security report before live model
review:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py --print-security-profile
python examples/agents/openrouter_alias_scout/run_alias_scout.py --check-security-profile
```

The report schema is `skeinrank.agent_security_profile.v1`. Proposal submission
remains disabled by default; the agent may prepare proposal payloads, but it
must not directly write dictionaries, publish snapshots, push to Git, or mutate
runtime state.

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

Patch 41B connects high-confidence agent `proposal_payload` values to the
existing SkeinRank agent tools without changing backend routes. The runner can
preview a submission plan, validate ready proposals through
`POST /v1/tools/validate-alias`, and optionally submit pending proposals through
`POST /v1/tools/suggest-alias` only when explicitly requested and allowed by
security/config.

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --llm-review-report /tmp/skeinrank-41a-llm-report.json \
  --print-proposal-submission-plan

python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --llm-review-report /tmp/skeinrank-41a-llm-report.json \
  --validate-ready-proposals
```

Submission remains opt-in and governed. It creates pending proposals only; it
never writes directly to dictionaries, never pushes Git, and never publishes
runtime snapshots.

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


### Patch 41F — Agent run/document tracking

The OpenRouter alias scout now includes a local JSONL tracking ledger for run/document visits. Use `--print-agent-tracking-plan`, `--write-agent-tracking-report`, or `--append-agent-tracking-ledger` to inspect document fingerprints and skip/revisit decisions before moving the same contract into PostgreSQL.
