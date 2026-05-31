# SkeinRank documentation

This directory keeps repository-level documentation for developers, operators, and contributors. The public product site is available at <https://skeinrank.github.io>.

## Start here

- [`product-positioning.md`](product-positioning.md) — public README/GitHub positioning for SkeinRank as a Terminology Control Plane, including personas, 3-tab UI scope, demo tour, safety posture, and public-beta readiness checklist.
- [`benchmarks/headless-agent-workflow.md`](benchmarks/headless-agent-workflow.md) — deterministic 48A/49A/49B/49C benchmark for the headless agent proposal workflow, expanded quality report, proposal quality metrics, and agent decision diagnostics.
- [`benchmarks/openrouter-live-pilot.md`](benchmarks/openrouter-live-pilot.md) — guarded 48B live OpenRouter pilot with cost limits and no runtime mutation.
- [`benchmarks/containerized-benchmark-integration.md`](benchmarks/containerized-benchmark-integration.md) — 48C Docker Compose + PostgreSQL + Governance API + Elasticsearch integration benchmark.
- [`benchmarks/retrieval-eval-baseline.md`](benchmarks/retrieval-eval-baseline.md) — 50A/50B/50B.1/50C/53A retrieval quality baseline, 500-document corpus, and retrieval comparison report with qrels, hard negatives, query-hygiene metrics, NDCG@10, MRR@10, Recall@10, baseline-vs-SkeinRank deltas, and benchmark-retrieval-compare diagnostics.
- [`benchmarks/synthetic-smoke-generator.md`](benchmarks/synthetic-smoke-generator.md) — 53B deterministic 5k synthetic smoke generator for batch/scale checks without OpenRouter, Elasticsearch, database calls, or runtime mutation.
- [`benchmarks/cost-latency-throughput-report.md`](benchmarks/cost-latency-throughput-report.md) — 53C offline cost, latency, throughput, savings, and projection report for 5k smoke manifests plus optional live-pilot usage JSON.
- [`pilots/elasticsearch-pilot-integration.md`](pilots/elasticsearch-pilot-integration.md) — 49E first-company pilot path for connecting an existing Elasticsearch index, seeding a dictionary/binding, and producing a read-only integration report.
- [`pilots/first-company-pilot-runbook.md`](pilots/first-company-pilot-runbook.md) — 54A operator runbook for planning, rehearsing, running, reviewing, and exiting the first company pilot safely.
- [`pilots/troubleshooting-bundle-export.md`](pilots/troubleshooting-bundle-export.md) — 54B sanitized support bundle export for pilot troubleshooting.
- [`pilots/support-bundle-production.md`](pilots/support-bundle-production.md) — 56B production-style support bundle with logs, config inventory, health snapshots, alert/degraded-state snapshots, and last agent runs.
- [`deployment/alerting-hooks-degraded-state-reports.md`](deployment/alerting-hooks-degraded-state-reports.md) — 56A read-only alerting hook payload previews and degraded-state reports.
- [`deployment/docker-images.md`](deployment/docker-images.md) — GHCR image publishing for release tags and manual rebuilds.
- [`deployment/release-compose.md`](deployment/release-compose.md) — release Compose runbook using published GHCR images.
- [`deployment/helm-chart.md`](deployment/helm-chart.md) — alpha Helm chart for Kubernetes installs using external PostgreSQL, RabbitMQ, and Elasticsearch/OpenSearch.

- [`overview.md`](overview.md) — what SkeinRank is, what it solves, and how the repository is organized.
- [`concepts/terminology-control-plane.md`](concepts/terminology-control-plane.md) — terminology, aliases, guardrails, evidence, and snapshots.
- [`concepts/profiles-bindings-snapshots.md`](concepts/profiles-bindings-snapshots.md) — the production runtime model.
- [`concepts/headless-runtime-contracts.md`](concepts/headless-runtime-contracts.md) — headless-first contract map for runtime, agents, snapshots, and UI scope.
- [`concepts/dictionary-spec-v1.md`](concepts/dictionary-spec-v1.md) — stable dictionary import/export contract with `schema_version`.
- [`guides/terminology-as-code.md`](guides/terminology-as-code.md) — 60A Terminology-as-Code import/export workflow: YAML/JSON in Git, JSON APIs, PostgreSQL control-plane state, and binding-scoped runtime snapshot artifacts.
- [`guides/dictionary-cli-planning.md`](guides/dictionary-cli-planning.md) — 60B CLI `lint`, server-backed `plan`, and `apply --plan-output` workflow for JSON/YAML dictionaries.
- [`deployment/gitops-delivery-runbook.md`](deployment/gitops-delivery-runbook.md) — 60C GitOps delivery runbook for GitLab CI, ArgoCD, Flux, and binding-scoped runtime artifacts.
- [`guides/enrichment-pause-resume-checkpointing.md`](guides/enrichment-pause-resume-checkpointing.md) — 61C pause/resume controls and chunk checkpoint metadata for Celery-backed enrichment jobs.
- [`../examples/gitops-delivery`](../examples/gitops-delivery) — reference GitLab CI, ArgoCD, Flux, and Kustomize examples for runtime artifact delivery.
- [`concepts/coverage-framework.md`](concepts/coverage-framework.md) — slots, tags, ambiguous aliases, binding policies, and evaluation guardrails.
- [`adr/0001-headless-runtime-contracts.md`](adr/0001-headless-runtime-contracts.md) — accepted architecture decision for headless runtime boundaries.
- [`guides/core-sdk-and-cli.md`](guides/core-sdk-and-cli.md) — local dictionary validation, extraction, canonicalization, and document extraction.
- [`guides/governance-console.md`](guides/governance-console.md) — governance API/UI workflow.
- [`guides/proposal-inbox-ui.md`](guides/proposal-inbox-ui.md) — review-first AI Inbox detail panel for evidence, risk, validation findings, and approve/reject actions.
- [`guides/playground-snapshot-compare-ui.md`](guides/playground-snapshot-compare-ui.md) — Search Playground split-screen compare mode for binding-backed runtime snapshots.
- [`guides/schema-snapshots-tree-ui.md`](guides/schema-snapshots-tree-ui.md) — read-heavy Schema & Snapshots tree + detail view for bindings, profiles, canonical terms, aliases, and snapshot drift.
- [`guides/ui-polish-empty-states-degraded-banners.md`](guides/ui-polish-empty-states-degraded-banners.md) — global degraded-state banner and actionable empty states for the 3-tab Control Plane UI.
- [`guides/control-plane-navigation-slim-down.md`](guides/control-plane-navigation-slim-down.md) — 58F primary navigation contract with Playground, AI Inbox, and Schema & Snapshots plus utility/legacy tools.
- [`guides/read-only-legacy-admin-cockpit.md`](guides/read-only-legacy-admin-cockpit.md) — 58G lockdown for legacy/admin write controls with an explicit local-development bypass.
- [`guides/seeded-demo-walkthrough.md`](guides/seeded-demo-walkthrough.md) — 59A seeded product walkthrough for Playground, AI Inbox, Schema & Snapshots, and read-only legacy cockpit.
- [`guides/demo-product-tour.md`](guides/demo-product-tour.md) — 59B one-command demo tour and smoke report (`make demo-tour`, `make demo-tour-smoke`, `platform_ops_demo_tour_report.json`).
- [`guides/coverage-framework.md`](guides/coverage-framework.md) — headless workflow for tags, conflicts, ambiguous candidates, policies, and before/after evaluation.
- [`../examples/agents/openrouter_alias_scout`](../examples/agents/openrouter_alias_scout) — reference OpenRouter alias scout foundation and SkeinRank REST client.
- [`guides/elasticsearch-enrichment.md`](guides/elasticsearch-enrichment.md) — Elasticsearch enrichment, dry-run, evidence, jobs, and cancellation.
- [`guides/enrichment-beta-hardening.md`](guides/enrichment-beta-hardening.md) — preflight, concurrency guard, and beta safety rules for enrichment jobs.
- [`deployment/blue-green-alias-swap-runbook.md`](deployment/blue-green-alias-swap-runbook.md) — blue/green operator runbook for `reindex_alias_swap`, alias publish, cancellation, and rollback.
- [`../examples/blue-green-alias-swap`](../examples/blue-green-alias-swap) — request payloads and checklist for the 61B alias-swap rollout path.
- [`guides/development.md`](guides/development.md) — local development checks and package workflow.
- [`api/governance-api.md`](api/governance-api.md) — important HTTP surfaces and runtime endpoints.

## Production safety

- [Apply policy and risk levels](policies/apply-policy-risk-levels.md) — proposal risk classification for safe apply workflows.
- [Role boundaries](policies/role-boundaries.md) — explicit agent/reviewer/admin boundaries for production human-in-the-loop workflows.
- [Profile isolation checks](policies/profile-isolation-checks.md) — read-only profile/binding alignment checks for production safety.
- [Alerting hooks and degraded-state reports](deployment/alerting-hooks-degraded-state-reports.md) — read-only operator alerts from troubleshooting and isolation state.

## Deployment

- [`deployment/docker-images.md`](deployment/docker-images.md) — GHCR image publishing, automatic tag builds, and manual rebuilds for existing tags.
- [`deployment/release-compose.md`](deployment/release-compose.md) — public beta Compose stack using published GHCR images.
- [`deployment/docker-compose.md`](deployment/docker-compose.md) — full Docker Compose dev stack and release quickstart.
- [`deployment/headless-quickstart.md`](deployment/headless-quickstart.md) — API/PostgreSQL-only golden path for headless integrations.
- [`deployment/gitops-delivery-runbook.md`](deployment/gitops-delivery-runbook.md) — GitLab CI / ArgoCD / Flux delivery runbook for Terminology-as-Code runtime artifacts.
- [`deployment/blue-green-alias-swap-runbook.md`](deployment/blue-green-alias-swap-runbook.md) — production-oriented blue/green alias-swap runbook for Elasticsearch enrichment.
- [`deployment/security.md`](deployment/security.md) — production-oriented security baseline.
- [`deployment/env-and-secrets.md`](deployment/env-and-secrets.md) — `.env` validation, required settings, and secrets handling.
- [`deployment/production-compose.md`](deployment/production-compose.md) — production-ish Compose profile, ops services, and smoke checks.
- [`deployment/observability.md`](deployment/observability.md) — logs, metrics, tracing, Prometheus, and Grafana.
- [`deployment/backup-restore.md`](deployment/backup-restore.md) — backup/restore and runbooks.
- [`deployment/upgrade-guide.md`](deployment/upgrade-guide.md) — production-ish upgrade flow and rollback notes.
- [`deployment/migration-safety.md`](deployment/migration-safety.md) — Alembic/schema health safety checks.
- [`deployment/release-checklist.md`](deployment/release-checklist.md) — release and deployment checklist.
- [`deployment/dev-stack-troubleshooting.md`](deployment/dev-stack-troubleshooting.md) — common local stack issues.

Schema health is available through `GET /schema/health` and `python -m skeinrank_governance_api.migrations check`. It verifies the Alembic head, database revision, `alembic_version`, and missing SQLAlchemy metadata tables. Patch 45A mirrors this state into Prometheus gauges and adds DB-backed agent tracking gauges under `GET /metrics`. Patch 45B adds structured log event fields and a sanitized troubleshooting report at `GET /v1/ops/troubleshooting/report` / `python -m skeinrank_governance_api.troubleshooting report`. Patch 45C adds `python -m skeinrank_governance_api.backup_restore export|inspect|restore` and operational runbooks. Patch 46A adds `.env.production.example`, production Compose ops services, optional Prometheus/Grafana profile, and `deploy/docker/scripts/prod-smoke-test.sh`. Patch 46B adds `python -m skeinrank_governance_api.env_validation validate --file .env` plus `make prod-env-check` / `make prod-env-check-strict` for preflight `.env` validation. Patch 46C adds `make prod-upgrade-check`, `make prod-preflight`, `make prod-upgrade`, and deployment runbooks for upgrades, migration safety, and release checks. Patch 48C adds `make benchmark-stack-*` and `python -m skeinrank_governance_api.benchmark_stack` for a containerized benchmark that verifies the same platform-ops fixture against PostgreSQL, the Governance API, and Elasticsearch evidence checks. Patch 49A expands `platform_ops_v1` to 50 documents and adds proposal/runtime quality metrics for regression tracking. Patch 49B adds proposal-level rates, coverage, per-alias outcomes, and quality-gate breakdowns for tuning agents and validators. Patch 49C adds agent decision diagnostics that explain scanned/skipped/revisited documents, proposal decisions, validator reasons, and missing alias diagnostics. Patch 49E adds `python -m skeinrank_governance_api.pilot_integration` and `make pilot-*` for a repeatable first-company Elasticsearch pilot integration path. Patch 53A expands `platform_ops_v1` to a 500-document corpus and adds `corpus_manifest.json` for stable small-pilot scale validation. Patch 53B adds `python -m skeinrank_governance_api.synthetic_smoke` and `make benchmark-smoke-*` for deterministic 5k smoke corpus generation under ignored reports/synthetic artifacts. Patch 53C adds `python -m skeinrank_governance_api.benchmark_performance` and `make benchmark-performance-*` for offline cost, latency, throughput, savings, and projection reports from synthetic manifests plus optional live-pilot usage JSON. Patch 54B adds `python -m skeinrank_governance_api.support_bundle` and `make support-bundle-*` for sanitized pilot troubleshooting bundle export. Patch 56B extends the bundle with `health/health_summary.json`, `runs/last_agent_runs.json`, `logs/log_inventory.json`, and `config/config_inventory.json` for production-style support handoff.
Patch 54A adds `docs/pilots/first-company-pilot-runbook.md` and `examples/pilots/first_company_pilot_checklist.md` as the operator-facing path for the first company pilot: intake, local rehearsal, config preparation, preflight/seed/eval/report, optional validated-agent smoke, and exit criteria.


## Community and repository operations

- [`community/discussions.md`](community/discussions.md) — GitHub Discussions categories, welcome post, public beta feedback thread, and roadmap discussion draft.
- [`community/github-labels.md`](community/github-labels.md) — GitHub label taxonomy and GitHub CLI commands for syncing labels.


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

### Agent proposal inbox

Patch 41G adds an offline proposal inbox/review workflow for the OpenRouter alias scout. See `docs/guides/openrouter-agent.md` for `--print-proposal-inbox-plan`, `--build-proposal-inbox`, and `--write-proposal-inbox` examples.


### Agent approved apply and snapshot evaluation

Patch 41H adds the offline apply/evaluation bridge after proposal inbox review. It builds an approved-proposal apply plan and can compare before/after snapshot artifacts without calling SkeinRank APIs or publishing runtime snapshots.

### Agent scheduled runner

Patch 41I adds a scheduled/worker-mode entrypoint for the OpenRouter alias scout:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py --print-scheduled-runner-plan
python examples/agents/openrouter_alias_scout/run_alias_scout.py --run-agent-cycle
```

This is designed for external schedulers such as Airflow, cron, Prefect, GitHub Actions,
or Kubernetes CronJob. The default mode is report-only and does not mutate runtime state.

Patch 42A adds a full, network-free OpenRouter alias scout integration smoke test:
`--print-integration-smoke-plan` and `--write-integration-smoke-report`. The smoke
creates the complete report chain without external API calls or runtime mutation.

### OpenRouter agent real Elasticsearch validation

Patch 42B adds a reproducible real Elasticsearch validation scenario for the OpenRouter alias scout. See `docs/guides/openrouter-agent.md` and `examples/agents/openrouter_alias_scout/real_es_validation/`.

### Patch 42C — Reports/artifacts standard

The OpenRouter alias scout now writes normalized run artifacts under
`reports/<run_id>/` with `manifest.json`, `run_summary.json`, and per-stage JSON
reports in `reports/<run_id>/reports/`. See `docs/guides/openrouter-agent.md`.

### Patch 42E — Dictionary quickstart

Patch 42E documents a reproducible dictionary import → binding → source=latest snapshot quickstart for headless onboarding. Use `--print-dictionary-quickstart-plan` to inspect the safe plan, `--write-dictionary-quickstart-payloads` to write JSON payloads, and `--run-dictionary-quickstart` for validate-first API checks. Import, binding creation, and snapshot export require explicit flags.

- Agent/product hardening: proposal batches can now be previewed before apply, and validation warnings require explicit `allow_warnings=true` before backend apply.

### Runtime API smoke

Patch 42G adds a runtime API final smoke for the headless agent journey. After the dictionary quickstart creates a profile/binding, run the smoke to verify that canonicalization and query planning serve the expected terminology.

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py --run-runtime-api-smoke
```

Use `--runtime-smoke-binding-id <id> --runtime-smoke-export-snapshot` to include a binding-scoped headless snapshot export check.

### Patch 42D — Docker Compose full demo scenario

The OpenRouter agent documentation includes a Docker Compose full-demo guide (`openrouter-agent-full-demo`) and a safe plan command:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py --print-docker-demo-plan
```

The default demo mode is report-only and does not submit proposals or publish snapshots.


### Agent run registry

Patch 44A adds the first DB-backed agent tracking table: `agent_runs`. It lets scheduled/worker-style agent executions register a durable run record with status, trigger type, profile/binding context, model/prompt metadata, report/artifact URIs, and summary JSON.

The run registry is intentionally separate from runtime snapshots and proposal application: recording a run does not mutate terminology, submit proposals, or publish snapshots.


### Agent tracking: document visits

The governance API now supports DB-backed document visit tracking under `/v1/agents/runs/{run_id}/document-visits`. Agents can persist content hashes and processing-context hashes to decide whether a source document is new, unchanged, content-changed, or context-changed.


### Agent LLM reviews and proposal attempts

Patch 44D adds the final DB-backed tracking tables for the initial agent audit trail: `agent_llm_reviews` and `agent_proposal_attempts`. These tables let operators trace each candidate from observation and evidence through LLM judgment, validation, submission/no-op, and idempotency handling.


### Proposal lifecycle hardening

Suggestion responses include lifecycle fields that help headless clients and UI review flows distinguish reviewable, warning, blocked, approved/applied, and rejected proposals without guessing from raw validation summaries.

The UI now includes a dedicated AI Proposals Inbox page for human-in-the-loop moderation. It is separate from the legacy Suggestions/dev workflow and focuses on pending proposal cards plus a detail panel for risk level, apply-policy decision, validation findings, saved evidence snippets, source payload metadata, and approve/reject actions.

The primary sidebar now follows a slim 3-tab Control Plane contract: Playground, AI Inbox, and Schema & Snapshots. Low-level setup, manual CRUD, and developer pages remain reachable under Settings / Developer Cockpit rather than being deleted.

The Snapshots section now includes a Schema & Snapshots tree workspace. It keeps schema inspection read-heavy by showing binding/profile/category/canonical/alias hierarchy and snapshot drift without adding broad manual edit forms or dangerous rollout buttons.

### Proposal apply idempotency

Batch apply now supports safe retries. If a caller retries the same suggestion ids after a successful apply, the API returns an idempotent result without creating duplicate terms or aliases.

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
ops:reports:read
```

This keeps scheduled agents and CI jobs least-privileged: read-only jobs can list
runs and tracking records, validation-only jobs can call `validate-alias`, and
proposal-writing jobs must explicitly carry `agent:tools:suggest`.



### Patch 49D — Live OpenRouter validated pilot

Adds an explicit validate-only live pilot flow for OpenRouter proposals against the SkeinRank Governance API. Use `make benchmark-agent-live-validated-pilot-plan` to preview and `make benchmark-agent-live-validated-pilot-report` or `make benchmark-agent-live-validated-pilot-stack` for guarded live validation. Reports include `validated_pilot` diagnostics and keep runtime mutation disabled.

### Agent run progress API

Patch 52A adds `GET /v1/agents/runs/{run_id}/progress`, a read-only progress snapshot for long-running agent workflows. It summarizes visited/scanned/skipped documents, candidate observations, evidence windows, LLM reviews, proposal attempts, and errors from the existing tracking tables. Optional `summary.expected_documents_total` and `summary.phase` values on the run help the endpoint calculate percent complete and display the current phase.

This is the backend foundation for future worker progress UI, resume/retry controls, and long-run operational reports.

### Agent run resume plan API

Patch 52B adds `POST /v1/agents/runs/{run_id}/resume-plan`, a read-only planner for continuing long-running agent workflows after partial completion or failures. The endpoint returns schema `skeinrank.agent_run_resume_plan.v1` with a bounded `work_items` list, `summary.by_kind` counters, and limit metadata.

Supported request controls are `batch_limit`, `retry_errors`, `retry_skipped`, `force_rescan`, and optional `source_ids`. The planner only reads `agent_document_visits`, `agent_candidate_observations`, `agent_llm_reviews`, and `agent_proposal_attempts`; it does not execute a worker, call LLM/search providers, submit proposals, or mutate run state.

### Agent run diagnostics/report API

Patch 52C adds `GET /v1/agents/runs/{run_id}/report`, a read-only diagnostics report for operators. The endpoint returns schema `skeinrank.agent_run_report.v1` and combines the progress snapshot with sampled skipped/unchanged documents, sampled errors, manual-review items, proposal validation outcomes, recommendations, and token/cost hints from persisted LLM usage metadata.

The report helps answer: why documents were skipped, where errors happened, which candidates/proposals require human review, which validation categories blocked proposals, and whether a cost budget hint was exceeded. It does not execute workers, call providers, submit proposals, apply dictionaries, or mutate run state.

### Validated pilot preflight hotfix

Patch 53A.1 makes the OpenRouter validated pilot fail fast before LLM calls when the Governance API validation context is not ready. The preflight now checks `/livez`, `/v1/tools/bindings`, and the read-only `POST /v1/tools/validate-alias` endpoint with a synthetic validation payload. Missing profiles or bindings are reported before OpenRouter budget is spent.

### Backup/restore verified scenario

- [Backup/restore verified scenario](deployment/backup-restore-verified-scenario.md) — disposable local drill for `make backup-restore-drill-plan`, `make backup-restore-drill-run`, and `make backup-restore-drill-inspect`.

## Patch 55C — Token rotation and scoped agent credentials

Patch 55C documents and verifies service-account token rotation for agent
workflows. It adds the read-only scoped credential policy endpoint and the
service-account token rotation endpoint:

```http
GET /v1/auth/scoped-agent-credentials
POST /v1/auth/service-accounts/{account_name}/tokens/{token_id}/rotate
```

See [`policies/token-rotation-scoped-agent-credentials.md`](policies/token-rotation-scoped-agent-credentials.md).

## Patch 55D — Tenant/profile isolation checks

Patch 55D adds `GET /v1/governance/isolation-checks`, a read-only operator report with schema `skeinrank.profile_isolation.v1`. It verifies that binding-scoped proposals, policies, enrichment jobs, agent runs, and agent tracking rows stay inside their profile/binding context. It also documents request guards for profile/binding mismatches in runtime planning, agent tools, proposal creation, and agent run registration.

This is not full multi-tenancy yet: no tenant column or data model migration is introduced. The current safety boundary remains profile plus optional binding. See [`policies/profile-isolation-checks.md`](policies/profile-isolation-checks.md).

## Patch 56A — Alerting hooks and degraded-state reports

Patch 56A adds `GET /v1/ops/alerts/report`, `python -m skeinrank_governance_api.alerting`, the `skeinrank-governance-alerting` Poetry script, and `make alerts-report-*` helpers. The report converts troubleshooting and profile-isolation state into `skeinrank.alerting_report.v1` plus a sanitized `skeinrank.alerting_hook_payload.v1` preview. It does not send webhooks, call OpenRouter/Elasticsearch, mutate runtime state, apply proposals, or publish snapshots. See [`deployment/alerting-hooks-degraded-state-reports.md`](deployment/alerting-hooks-degraded-state-reports.md).

## Patch 57A — Model provider abstraction

Patch 57A introduces `examples/agents/openrouter_alias_scout/model_provider.py`, a minimal provider interface for chat-completion backends. The existing OpenRouter path is preserved through `OpenRouterChatProvider`, and tests use `MockChatProvider` with no external calls. See [`deployment/model-provider-abstraction.md`](deployment/model-provider-abstraction.md).

## Patch 57B — OpenRouter and local endpoint adapters

Patch 57B adds concrete provider adapters for the alias scout: `openrouter` and `local_endpoint`. The local endpoint adapter is intended for private/self-hosted chat-completion servers and can be previewed with `--print-model-provider-plan` without network calls. See [`deployment/model-provider-adapters.md`](deployment/model-provider-adapters.md).

### Company model integration

Patch 57C adds a safe company-model integration plan for private/local chat-completion endpoints. Use `--print-company-model-integration-plan` to inspect the workflow without network calls or secrets. See [`deployment/company-model-integration.md`](deployment/company-model-integration.md).

## Patch 61A — Enrichment Beta hardening

`POST /v1/governance/elasticsearch/bindings/{binding_id}/jobs/preflight` is a
read-only operator check for enrichment jobs. It returns `ready`,
`blocking_issues`, `warnings`, `recommended_request`, and safety metadata. The
start-job endpoint uses the same guard and blocks concurrent active jobs for the
same binding plus unsafe `reindex_alias_swap` target-index choices. See
[`guides/enrichment-beta-hardening.md`](guides/enrichment-beta-hardening.md) and [`deployment/blue-green-alias-swap-runbook.md`](deployment/blue-green-alias-swap-runbook.md).

## MCP integration kit

- `deployment/mcp-integration-kit.md` documents the packaged `skeinrank-mcp`
  stdio adapter, its safe tool boundary, and the generic agent integration flow.
- `../examples/mcp-integration-kit` contains client-neutral config, env, prompt,
  and tool-contract fixtures.
- `deployment/mcp-scoped-credentials-smoke-tests.md` documents scoped service-account
  tokens for MCP agents and the offline `skeinrank-mcp --smoke-test` helper.
- `../examples/mcp-scoped-credentials` contains service-account token request
  examples and scoped-token MCP client config.
- `deployment/mcp-claude-desktop.md` documents Claude Desktop stdio setup for
  `skeinrank-mcp`.
- `deployment/mcp-cursor-agents.md` documents Cursor/IDE agent usage for search
  integration and terminology proposal workflows.
- `deployment/mcp-langgraph-agents.md` documents a LangGraph-style agent pattern
  without adding a runnable agent package.
- `../examples/mcp-agent-docs` contains Claude/Cursor config examples, agent
  prompts, LangGraph-style flow policy, and a smoke checklist.
## Patch 63A — Binding-aware runtime canonicalization API

Runtime canonicalization and query planning now expose a clearer binding-aware
contract. Production callers should prefer `binding_id` or `binding_name`;
responses include `runtime_context` for audit/debug, and optional
`application_scope` metadata can record the app route/workspace that selected
the binding. See [`guides/runtime-routing-api.md`](guides/runtime-routing-api.md)
and [`../examples/runtime-routing-api`](../examples/runtime-routing-api).
Patch 63B adds deterministic alias `context_triggers`; see [`guides/context-trigger-disambiguation.md`](guides/context-trigger-disambiguation.md).



## Patch 63C — Multi-binding route plan API

`POST /v1/query/route-plan` is a read-only multi-binding planner for application
backends that need to rank candidate bindings before executing search. It returns
`route_plan_only` responses with `selected_bindings`, `rejected_bindings`, and
`failed_bindings`; it does not call Elasticsearch. See
[`guides/runtime-routing-api.md`](guides/runtime-routing-api.md) and
[`../examples/runtime-routing-api/route-plan.request.json`](../examples/runtime-routing-api/route-plan.request.json).
