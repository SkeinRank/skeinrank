# Governance API reference

This page lists the main API surfaces used by the governance console, migration tooling, runtime search path, and Elasticsearch workflows.

The governance API lives in:

```text
packages/skeinrank-governance-api
```

Start locally:

```bash
cd packages/skeinrank-governance-api
poetry install
poetry run python -m skeinrank_governance_api.migrations upgrade head
poetry run skeinrank-governance-api --reload
```

Default local URL:

```text
http://127.0.0.1:8010
```

For the API/PostgreSQL-only smoke path, start `docker-compose.headless.yml` and follow `docs/deployment/headless-quickstart.md`.

## Health and readiness

```text
GET /livez
GET /healthz
GET /readyz
GET /schema/health
GET /metrics
GET /v1/ops/troubleshooting/report
GET /v1/ops/alerts/report
```

`/healthz` reports process/database health and includes a schema-health block. `/readyz` also requires the migrated governance schema to be at the current Alembic head, then checks configured Elasticsearch readiness. `/schema/health` is a read-only schema check for operators and CI. `/metrics` exposes Prometheus-compatible metrics when enabled by configuration and refreshes best-effort operational gauges for database/schema health, Elasticsearch reachability, and DB-backed agent tracking counts. `/v1/ops/troubleshooting/report` returns a sanitized operator report with config, health checks, table counts, and recommendations. `/v1/ops/alerts/report` converts troubleshooting and profile-isolation degraded state into alert events and a sanitized hook payload preview without sending webhooks.

Patch 45A metrics to watch first:

```text
skeinrank_database_up
skeinrank_schema_ok
skeinrank_schema_current_matches_head
skeinrank_schema_missing_tables
skeinrank_elasticsearch_up
skeinrank_agent_runs_current
skeinrank_agent_document_visits_current
skeinrank_agent_candidate_observations_current
skeinrank_agent_llm_reviews_current
skeinrank_agent_proposal_attempts_current
```

CLI equivalent:

```bash
poetry run python -m skeinrank_governance_api.migrations check
```

The schema check reports `current_revision`, `head_revision`, multiple Alembic heads, whether `alembic_version` exists, and any SQLAlchemy metadata tables missing from the database.

## Troubleshooting report

```text
GET /v1/ops/troubleshooting/report
```

The troubleshooting report is read-only and intended for operators. It includes sanitized runtime configuration, database/schema/Elasticsearch/observability checks, selected table counts, and recommended next steps. It never includes database credentials, API tokens, Elasticsearch passwords, request bodies, document text, or query text.

When authentication is enabled, the endpoint requires the `admin` role. Personal and service-account API tokens must also include:

```text
ops:reports:read
```

CLI equivalent:

```bash
poetry run python -m skeinrank_governance_api.troubleshooting report
poetry run python -m skeinrank_governance_api.troubleshooting report --strict
poetry run python -m skeinrank_governance_api.backup_restore export --out backups/governance.json
poetry run python -m skeinrank_governance_api.backup_restore inspect --file backups/governance.json
poetry run python -m skeinrank_governance_api.backup_restore restore --file backups/governance.json --dry-run
```

`--strict` returns a non-zero exit code when the generated report status is degraded.

## Alerting degraded-state report

```text
GET /v1/ops/alerts/report
```

The alerting report is read-only and returns schema `skeinrank.alerting_report.v1`. It combines the troubleshooting report with profile/binding isolation checks, emits alert events for degraded database/schema/search/observability/profile-isolation state, and renders a sanitized `webhook_json` payload preview.

The endpoint does **not** deliver webhooks. It also does not call OpenRouter, call Elasticsearch, apply proposals, publish snapshots, or mutate runtime state.

When authentication is enabled, the endpoint requires the `admin` role and the `ops:reports:read` token scope.

CLI equivalent:

```bash
poetry run python -m skeinrank_governance_api.alerting plan
poetry run python -m skeinrank_governance_api.alerting report --out /tmp/skeinrank-alerting-report.json
poetry run python -m skeinrank_governance_api.alerting show --file /tmp/skeinrank-alerting-report.json
```

Repository helpers:

```bash
make alerts-report-plan
make alerts-report-generate
make alerts-report-show
```

## Headless dictionary workflows

These endpoints are the automation-first facade for CI jobs, agents, and service
integrations. They use the same stable dictionary spec v1 payload as the console
migration flow, but avoid naming the API after a UI surface.

```text
POST /v1/headless/dictionaries/validate
POST /v1/headless/dictionaries/apply
GET  /v1/headless/dictionaries/export?profile_name=...
```

Recommended use:

```text
validate -> apply -> export -> create/publish runtime snapshot
```

`validate` never writes to the database. `apply` validates first and then writes
profile, term, alias, and stop-list changes in one transaction. `export` returns
the current profile dictionary with `schema_version`.

## Headless snapshot artifact export

After a dictionary is applied and a binding exists, automation can export a
portable binding-scoped runtime artifact:

```text
GET /v1/headless/snapshots/export?binding_id=7
GET /v1/headless/snapshots/export?binding_id=7&source=runtime
```

`source=latest` is the default and builds an artifact from the current profile
state. `source=runtime` exports the binding-pinned runtime snapshot and returns
`409` when the binding has not published one yet.

The artifact contains:

- `schema_version: skeinrank.runtime_snapshot_artifact.v1`;
- binding context: index, fields, filters, target field, write strategy;
- profile identity;
- compiled `runtime_snapshot`;
- manifest checksum, source, snapshot version, and alias count.

CLI example:

```bash
skeinrank-migrate snapshot-export \
  --binding-id 7 \
  --snapshot-version platform_ops@v1 \
  --output snapshots/platform_ops.binding-7.v1.json
```

Validate and summarize a local artifact without contacting the API:

```bash
skeinrank-migrate snapshot-inspect snapshots/platform_ops.binding-7.v1.json
```

Headless workers can also load artifacts directly through
`RuntimeSnapshotArtifactCache`, which validates the manifest checksum and reloads
the file when it changes.

## Terminology-as-Code import/export map

The 60A file workflow uses the existing API and CLI surfaces rather than adding a
new endpoint family:

```text
Git dictionary file
  -> POST /v1/headless/dictionaries/validate
  -> POST /v1/headless/dictionaries/apply
  -> GET  /v1/headless/dictionaries/export?profile_name=...
  -> GET  /v1/headless/snapshots/export?binding_id=...
  -> runtime artifact delivery through GitOps or object storage
```

Use `skeinrank-migrate validate`, `skeinrank-migrate apply`,
`skeinrank-migrate export`, and `skeinrank-migrate snapshot-export` for the same
workflow from CI scripts. YAML input is a CLI convenience; HTTP requests and
responses remain JSON. See `docs/guides/terminology-as-code.md` for the full
runbook and examples.

## Console dictionary workflows

The console endpoints remain available for the existing governance UI and legacy
scripts. New headless integrations should prefer `/v1/headless/dictionaries/*`.

```text
POST /v1/console/dictionary/validate
POST /v1/console/dictionary/import
GET  /v1/console/dictionary/export?profile_name=...
```

Both surfaces share the same implementation and response shapes. The expected
dictionary shape is `skeinrank.dictionary.v1` and is compatible with the
lightweight SDK/CLI examples in `examples/migration/console_dictionary.example.json`.
New payloads should include `schema_version`; legacy payloads without it are
accepted as v1 for backward compatibility. HTTP requests and responses remain JSON;
CLI validate/apply accepts YAML files as a human-editable convenience when PyYAML
is available.

## Profiles, terms, aliases, and guardrails

The governance API exposes CRUD-style endpoints for:

- profiles;
- canonical terms;
- aliases;
- global stop-list entries;
- profile stop-list entries;
- suggestions and approval/rejection workflows;
- runtime-compatible snapshot export.

Snapshots are exported from governed terminology and served to runtime paths as immutable dictionary versions.


## Conflict detection report

Coverage framework Phase C starts with a read-only conflict report. It does not
change active terminology or runtime snapshots; it only surfaces drift risks for
reviewers and future ambiguous-alias policy work.

```text
GET /v1/governance/conflicts
GET /v1/governance/conflicts?profile_name=infra_incidents
GET /v1/governance/conflicts?profile_name=infra_incidents&include_suggestions=false
PATCH /v1/governance/conflicts/{fingerprint}/review
```

Each conflict item includes a deterministic `fingerprint`, default `severity`, and persisted review state (`open`, `ignored`, or `resolved`). Admins and moderators can update review state without changing terms, aliases, proposals, or runtime snapshots.

The report currently detects:

- active alias surfaces reused across profiles;
- active aliases that map to multiple canonical terms;
- canonical surfaces used with different primary slots;
- active aliases/canonical terms that now collide with profile or global stop lists;
- pending alias proposals that conflict with active aliases or other pending proposals.

This is intentionally a report-only API. Severity, review state, and explicit
ambiguous-alias candidates are added in later coverage-framework patches.

## Suggestions and evidence

Reviewer workflows can refresh evidence for pending suggestions:

```text
POST /v1/governance/profiles/{profile_name}/suggestions/{suggestion_id}/evidence/refresh
```

The request references an Elasticsearch binding for the same profile. If `query` is omitted, alias suggestions use their alias value and canonical-term suggestions use their canonical value.

Suggestions also support proposal metadata for headless/agent workflows. Existing manual requests remain valid, and automation can optionally provide `binding_id`, `proposal_source_type`, `proposal_source_name`, `idempotency_key`, `source_payload`, and `validation_summary`. The binding must belong to the same profile as the suggestion. If `validation_summary` is omitted, the API runs the proposal checker registry and stores structured results covering canonical availability, alias collisions, stop-list guardrails, noisy aliases, confidence, idempotency hints, and agent audit payloads.

### Agent-friendly proposal tools

Patch 37C adds task-shaped routes for agents, CLI jobs, and service
integrations. They are a facade over existing governance/runtime logic, not a
second proposal model:

```text
GET  /v1/tools/bindings
POST /v1/tools/validate-alias
POST /v1/tools/suggest-alias
POST /v1/tools/explain-query
```

`validate-alias` runs the proposal checker registry without creating a
suggestion. `suggest-alias` creates a pending suggestion with
`proposal_source_type=agent` by default. `explain-query` reuses the runtime query
planner so agents can inspect canonicalization before proposing changes.

### Proposal source quality

Patch 37G adds a reviewer-oriented source quality endpoint:

```text
GET /v1/governance/proposals/source-quality
```

Optional filters: `profile_name`, `proposal_source_type`, and `proposal_source_name`.
The response aggregates persisted proposal state by source and includes totals,
pending/approved/rejected counts, validation status counts, approval rate,
rejection rate, blocked rate, and average confidence. This is intentionally
computed from PostgreSQL state rather than from Prometheus counters so it
remains useful after restarts.

Prometheus also exposes proposal flow counters for submission outcomes, review
decisions, and batch apply operations.

### Proposal batch apply

Patch 37D adds an atomic release endpoint for reviewed proposal batches:

```text
POST /v1/governance/profiles/{profile_name}/suggestions/apply-batch
```

The request can provide explicit `suggestion_ids`, or omit them to apply all
pending suggestions for the profile. Setting `publish_snapshot=true` requires a
matching `binding_id` and pins a fresh runtime snapshot on that binding in the
same transaction. Suggestions with `validation_summary.status = blocked` are not
applied by the batch endpoint.

Saved evidence includes binding metadata, query metadata, warnings, and highlighted snippets.

## Elasticsearch discovery and bindings

Connection and mapping discovery:

```text
GET /v1/governance/elasticsearch/connection/status
GET /v1/governance/elasticsearch/indices
GET /v1/governance/elasticsearch/indices/{index_name}/mapping
```

Binding dry-run:

```text
POST /v1/governance/elasticsearch/bindings/{binding_id}/dry-run
```

Evidence lookup:

```text
POST /v1/governance/elasticsearch/bindings/{binding_id}/evidence
```

Enrichment jobs:

```text
POST /v1/governance/elasticsearch/bindings/{binding_id}/jobs/preflight
```

Read-only preflight for write-mode enrichment. It returns `ready`,
`blocking_issues`, `warnings`, `recommended_request`, and safety metadata. It
does not create jobs, write documents, reindex, or swap aliases.


```text
POST /v1/governance/elasticsearch/bindings/{binding_id}/jobs
GET  /v1/governance/elasticsearch/jobs?binding_id=...
GET  /v1/governance/elasticsearch/jobs/{job_id}
POST /v1/governance/elasticsearch/jobs/{job_id}/pause
POST /v1/governance/elasticsearch/jobs/{job_id}/resume
POST /v1/governance/elasticsearch/jobs/{job_id}/cancel
POST /v1/governance/elasticsearch/jobs/{job_id}/rollback
```

Pause/resume is intended for Celery-backed chunked jobs. It records checkpoint metadata under `result_json.chunked_enrichment.checkpoint` and requeues only remaining chunks when a paused job resumes. See [`../guides/enrichment-pause-resume-checkpointing.md`](../guides/enrichment-pause-resume-checkpointing.md).

Rollback is conservative and only applies to succeeded `reindex_alias_swap` jobs
with completed alias swaps and valid rollout metadata. See
[`../deployment/blue-green-alias-swap-runbook.md`](../deployment/blue-green-alias-swap-runbook.md).

## Runtime search and canonicalization

Production runtime should prefer binding-aware requests because a binding knows the index, fields, filters, and pinned snapshot.

Recommended production shape:

```json
{
  "binding_id": 7,
  "query": "k8s pg timeout",
  "size": 10
}
```

Useful runtime design rule:

```text
profile_name mode = preview/dev dictionary mode
binding_id mode   = pinned production runtime mode
```

## Auth and API access

The governance API supports local auth, users, roles, personal API tokens, service accounts, and token revocation.

Important environment variables include:

```text
SKEINRANK_GOVERNANCE_API_AUTH_ENABLED
SKEINRANK_GOVERNANCE_API_BOOTSTRAP_ADMIN
SKEINRANK_GOVERNANCE_API_ADMIN_USERNAME
SKEINRANK_GOVERNANCE_API_ADMIN_PASSWORD
SKEINRANK_GOVERNANCE_API_DATABASE_URL
SKEINRANK_GOVERNANCE_API_ELASTICSEARCH_URL
SKEINRANK_GOVERNANCE_API_ENRICHMENT_JOBS_BACKEND
```

Do not use default credentials or permissive CORS settings in production. See `docs/deployment/security.md`.

## MCP server MVP

Patch 37F exposes the same agent-safe proposal tools through a small stdio MCP
adapter. The MCP server delegates to the REST API instead of duplicating business
logic.

```bash
cd packages/skeinrank-governance-api
poetry run skeinrank-mcp --api-url http://127.0.0.1:8010
```

Environment variables:

```text
SKEINRANK_MCP_GOVERNANCE_API_URL=http://127.0.0.1:8010
SKEINRANK_MCP_ROLE=admin
SKEINRANK_MCP_API_TOKEN=optional-bearer-token
```

MCP tools:

```text
skeinrank_list_bindings
skeinrank_explain_query
skeinrank_validate_alias
skeinrank_submit_alias_proposal
skeinrank_get_proposal_status
```

The MCP adapter keeps the same production rule as the REST tools: an agent can
submit a proposal, validate a candidate alias, or explain a query, but it does
not mutate active runtime terminology directly.


### Patch 38A/38B: term tags in governance and runtime

Dictionary terms and governance term APIs now accept optional `tags` on canonical
terms. Tags are normalized, deduplicated facets (`infra`, `backend`, `storage`)
that complement the primary `slot`. Runtime snapshot alias entries now carry
those tags too, so exported artifacts and query/canonicalization debug output
can explain both the primary slot and richer term facets.

### Ambiguous alias candidates

Phase C adds reviewer-facing ambiguous alias endpoints:

- `GET /v1/governance/profiles/{profile_name}/ambiguous-aliases`
- `POST /v1/governance/profiles/{profile_name}/ambiguous-aliases`
- `GET /v1/governance/profiles/{profile_name}/ambiguous-aliases/{surface_value}`
- `PATCH /v1/governance/profiles/{profile_name}/ambiguous-aliases/{surface_value}`

Ambiguous aliases record possible canonical interpretations for one surface form without changing active runtime behavior. Patch 38H adds runtime BindingPolicy resolution for binding-scoped canonicalization and query planning.

Patch 38F connects this coverage layer to the proposal pipeline: when an alias proposal conflicts with an active alias or with another pending proposal for the same surface, SkeinRank creates or updates the corresponding ambiguous alias candidates. This keeps the proposal accepted for review, records the competing interpretations, and still avoids direct runtime mutation.

### Binding policy API

Patch 38G adds binding-scoped policy metadata and Patch 38H uses it during runtime resolution.

```http
GET /v1/governance/elasticsearch/bindings/{binding_id}/policy
PUT /v1/governance/elasticsearch/bindings/{binding_id}/policy
DELETE /v1/governance/elasticsearch/bindings/{binding_id}/policy
```

A policy can define `preferred_slots`, `allowed_tags`, `deny_slots`, and `context_rules`. These fields are normalized on write. The API stores policy metadata separately. Runtime endpoints can use the active policy to select safe candidates, but the policy still does not mutate terms, aliases, ambiguous candidates, or snapshots.


### Runtime policy decision output

When `/v1/text/canonicalize`, `/v1/query/plan`, `/v1/search`, or `/v1/search/multi` runs with a `binding_id`, SkeinRank applies the active binding policy if one exists. The response may include `policy_decisions`, each containing the matched surface, selected canonical, selected slot, reason, and candidate summaries.

## Snapshot before/after evaluation

Patch 38I adds an offline CLI evaluator for runtime snapshot artifacts. It does
not mutate PostgreSQL, active terminology, bindings, or runtime snapshots.

```bash
skeinrank-migrate snapshot-eval \
  --before snapshots/platform_ops.binding-7.v1.json \
  --after snapshots/platform_ops.binding-7.v2.json \
  --queries queries.jsonl \
  --output eval-report.json
```

Supported query files are JSON arrays of strings/objects or JSONL with one
string/object per line. Object items may include `query` and optional `id` or
`query_id`.

The report uses `schema_version: skeinrank.snapshot_evaluation.v1` and includes
alias diff totals, tag diff totals, optional query-plan changes, and a compact
risk summary.


## Coverage framework docs and examples

Patch 38J collects the Phase C coverage model in documentation and example payloads:

- `docs/concepts/coverage-framework.md` explains slots vs tags, ambiguous candidates, binding policies, runtime policy decisions, and before/after evaluation.
- `docs/guides/coverage-framework.md` provides a headless API walkthrough.
- `examples/coverage-framework/` contains JSON/JSONL payloads for a tagged dictionary, ambiguous `pg` candidates, binding policies, and evaluation queries.

The examples are documentation fixtures only; they do not introduce new API routes or mutate runtime state by themselves.

## Reference agent runner foundation

Patch 40F adds `examples/agents/openrouter_alias_scout` as the first reference
agent integration. Patch 40G adds OpenRouter/OpenAI-compatible tool schemas and
prompts on top of the same existing tools. Patch 40H adds local candidate
discovery and pruning before any LLM/OpenRouter call. Patch 40I adds compact
evidence windows around discovered candidates while staying local-only. Patch 40K
adds a local E2E demo report that prepares a review queue without calling backend
routes:

```text
GET  /v1/tools/bindings
POST /v1/tools/explain-query
POST /v1/tools/validate-alias
POST /v1/tools/suggest-alias
```

Run the local previews with:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py --dry-run-plan
python examples/agents/openrouter_alias_scout/run_alias_scout.py --print-tool-schemas
python examples/agents/openrouter_alias_scout/run_alias_scout.py --print-system-prompt
python examples/agents/openrouter_alias_scout/run_alias_scout.py --print-sample-review-prompt
python examples/agents/openrouter_alias_scout/run_alias_scout.py --discover-candidates
python examples/agents/openrouter_alias_scout/run_alias_scout.py --print-sample-candidate-pack
python examples/agents/openrouter_alias_scout/run_alias_scout.py --sample-evidence
python examples/agents/openrouter_alias_scout/run_alias_scout.py --print-sample-evidence-pack
python examples/agents/openrouter_alias_scout/run_alias_scout.py --run-demo-report
python examples/agents/openrouter_alias_scout/run_alias_scout.py --print-demo-review-prompt
```

The example is not a new API surface and it does not call OpenRouter yet. Tool
schemas map only to the existing `/v1/tools/*` facade, and the structured output
parser keeps model judgments limited to `propose`, `reject`, or `needs_evidence`
before any later runner validates and submits proposals. The Patch 40H discovery
report is local-only (`skeinrank.agent_candidate_discovery.v1`) and does not infer
canonical values or submit proposals. The Patch 40I evidence report is also
local-only (`skeinrank.agent_evidence_sampling.v1`) and keeps context windows
short so full documents are not sent to future model review. The Patch 40K demo
report is also local-only (`skeinrank.agent_demo_report.v1`): it reports
`proposals_submitted: 0` and exists to preview the future model-review queue, not
to mutate terminology.

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

Patch 40L documents the security envelope for the OpenRouter alias scout. It does
not add or change Governance API routes. The runner only references the existing
agent-safe facade:

```text
GET  /v1/tools/bindings
POST /v1/tools/explain-query
POST /v1/tools/validate-alias
POST /v1/tools/suggest-alias
```

Use the local security report before live model review:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py --print-security-profile
python examples/agents/openrouter_alias_scout/run_alias_scout.py --check-security-profile
```

The `skeinrank.agent_security_profile.v1` report redacts secrets, checks the
configured contributor role, and keeps proposal submission/runtime mutation
disabled by default.

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


### Agent tracking note

Patch 41F keeps agent run/document tracking outside the Governance API for now. The reference runner writes a local JSONL ledger and does not add backend routes or migrations. This preserves the existing API surface while establishing the future PostgreSQL tracking contract.

### Agent proposal inbox note

Patch 41G does not add new governance API routes. The OpenRouter alias scout builds an offline proposal inbox from saved LLM review and `/v1/tools/validate-alias` / `/v1/tools/suggest-alias` reports. Review decisions remain local JSONL records until a later governed apply workflow consumes them.


### Agent approved apply and snapshot evaluation note

Patch 41H does not add new governance API routes. The OpenRouter alias scout builds an offline approved-proposal apply plan from the proposal inbox and can evaluate before/after snapshot artifacts. Actual profile mutation and snapshot publishing remain in the governed backend workflow.

## Agent scheduled runner notes

Patch 41I does not add Governance API routes. The OpenRouter alias scout scheduled mode
is an external worker entrypoint that can optionally call existing tool endpoints in later
explicit stages. The safe default is offline and does not call SkeinRank APIs.

## Agent integration smoke test

Patch 42A adds an offline integration smoke test for the OpenRouter alias scout.
It does not add or require new Governance API endpoints. The smoke validates the
agent-side report chain before live use of `/v1/tools/validate-alias` or
`/v1/tools/suggest-alias`.

### Agent Elasticsearch validation note

Patch 42B does not add governance API routes. It adds a client-side validation scenario that writes optional sample documents to a configured Elasticsearch/OpenSearch index and then reads evidence through the existing agent connector.

### Patch 42C agent artifact reports

Patch 42C does not change Governance API endpoints. It standardizes local agent
artifacts for scheduled/headless runs using `skeinrank.agent_artifact_manifest.v1`.

## Patch 42E — Dictionary quickstart endpoints

The 42E quickstart uses existing API endpoints only:

- `POST /v1/console/dictionary/validate` for validation-first dictionary checks.
- `POST /v1/console/dictionary/import` for explicit dictionary import.
- `POST /v1/governance/elasticsearch/bindings` for explicit binding creation.
- `GET /v1/headless/snapshots/export?binding_id=<id>&source=latest` for headless source=latest snapshot artifact export.

The quickstart runner exposes `--print-dictionary-quickstart-plan`, `--write-dictionary-quickstart-payloads`, and `--run-dictionary-quickstart`. Import, binding creation, and snapshot export remain opt-in flags.

### Proposal batch preview and warning gates

Patch 42F adds `POST /v1/governance/profiles/{profile_name}/suggestions/apply-batch/preview` for dry-run proposal review. The existing `apply-batch` endpoint now blocks validation-warning proposals by default; pass `allow_warnings: true` only after explicit review.

## Runtime API smoke endpoints

Patch 42G does not add new backend endpoints. The smoke runner exercises existing runtime/headless APIs:

- `POST /v1/text/canonicalize`
- `POST /v1/query/plan`
- `GET /v1/headless/snapshots/export?binding_id=<id>&source=latest` when explicitly requested.

This keeps the runtime smoke safe: no proposal submission, no dictionary mutation, and no snapshot publishing.



## Agent run registry

Patch 44A adds a DB-backed run registry under `/v1/agents`.

### Create an agent run

```http
POST /v1/agents/runs
```

Request fields include `run_id`, `agent_name`, `agent_version`, `status`, `trigger_type`, optional `profile_name`, optional `binding_id`, model/prompt metadata, artifact/report URIs, and `summary`.

### List agent runs

```http
GET /v1/agents/runs?status=running&agent_name=openrouter_alias_scout&profile_name=default_it
```

### Read or update one run

```http
GET /v1/agents/runs/{run_id}
PATCH /v1/agents/runs/{run_id}
```

Supported statuses are `queued`, `running`, `succeeded`, `failed`, `cancelled`, and `needs_review`. Supported trigger types are `manual`, `scheduled`, `api`, `worker`, and `test`.


## Agent document visits

Patch 44B adds document visit endpoints under the agent registry:

- `POST /v1/agents/runs/{run_id}/document-visits` records one visited source document.
- `GET /v1/agents/runs/{run_id}/document-visits` lists visits for a run and supports `status`, `should_scan`, and `limit` filters.

A visit stores `source_id`, optional external document metadata, `content_hash`, `processing_context_hash`, `visit_status`, and `should_scan`. The API classifies visits as `new_document`, `unchanged_seen`, `content_changed`, `context_changed`, `skipped`, or `error`.


## Agent LLM reviews and proposal attempts

Patch 44D extends `/v1/agents` with persisted LLM review and proposal-attempt tracking.

```http
POST /v1/agents/runs/{run_id}/llm-reviews
GET /v1/agents/runs/{run_id}/llm-reviews
POST /v1/agents/runs/{run_id}/proposal-attempts
GET /v1/agents/runs/{run_id}/proposal-attempts
```

LLM review rows store model/prompt metadata, response ids, usage, structured judgment, raw response, and a run-scoped review hash. Proposal-attempt rows store validation/submission status, idempotency keys, source payloads, and optional links to candidate observations, LLM reviews, and governance suggestions.


## Proposal lifecycle metadata

`SuggestionResponse` includes additive lifecycle fields: `validation_status`, `lifecycle_status`, `lifecycle_reason`, `can_approve`, and `can_apply`. Approval of a single suggestion rejects blocked validation summaries and requires `allow_warnings: true` for warning summaries. Batch apply keeps the same explicit `allow_warnings` behavior.

### Idempotent proposal batch apply

`POST /v1/governance/profiles/{profile_name}/suggestions/apply-batch` is retry-safe for explicit `suggestion_ids`. Already approved suggestions are returned as idempotent no-ops. Pending proposals that map to already-existing same-canonical aliases are approved as no-ops when warnings are explicitly allowed.

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

## Agent run progress

Patch 52A adds a read-only progress endpoint for persisted agent runs.

```http
GET /v1/agents/runs/{run_id}/progress
```

The response schema is `skeinrank.agent_run_progress.v1` and includes:

- `documents`: expected, visited, processed, pending, scanned, skipped, unchanged, changed, error, and by-status counters.
- `candidates`: observed, queued-for-review, reviewed, rejected, needs-evidence, error, and by-status counters.
- `evidence`: persisted evidence-window counters.
- `llm_reviews`: review totals by status.
- `proposals`: validation, submitted, created, idempotent, manual-review, error, and by-status counters.
- `errors`, `artifacts`, and `timestamps`: operator-facing run status context.

`summary.expected_documents_total` and `summary.phase` on the agent run are optional hints used for `percent_complete` and `phase`. The endpoint does not execute an agent, call external services, submit proposals, mutate dictionaries, or publish snapshots.

## Agent run resume plan

Patch 52B adds a read-only planner for resuming or retrying long-running runs.

```http
POST /v1/agents/runs/{run_id}/resume-plan
Content-Type: application/json
```

Request body:

```json
{
  "batch_limit": 100,
  "retry_errors": true,
  "retry_skipped": false,
  "force_rescan": false,
  "source_ids": ["doc-001", "doc-002"]
}
```

The response schema is `skeinrank.agent_run_resume_plan.v1` and includes:

- `limits`: effective batch limit, selected item count, available item count, and `has_more`.
- `summary`: work item counters by kind and operator notes.
- `work_items`: read-only units such as `resume_unfinished_document`, `retry_document_error`, `retry_candidate_error`, `retry_llm_review_error`, `retry_proposal_error`, `retry_skipped_document`, and `force_rescan`.

The endpoint requires `agent:runs:read`. It intentionally does not mutate agent run status, retry external calls, submit proposals, apply dictionary changes, or publish snapshots.

## Agent run diagnostics/report

Patch 52C adds a read-only operator report for persisted agent runs.

```http
GET /v1/agents/runs/{run_id}/report?item_limit=25
```

The response schema is `skeinrank.agent_run_report.v1` and includes:

- `progress`: the same read-only progress snapshot returned by `/progress`.
- `usage`: LLM review count, token totals, estimated cost hints, budget limit hints, and per-model usage counters from persisted `usage` metadata.
- `diagnostics`: overall status, findings, and operator recommendations.
- `documents`: sampled skipped/unchanged documents and document errors.
- `candidates`: candidate and LLM-review outcome counters.
- `proposals`: proposal attempt counters, blocked/warning/manual-review counts, and validation-category counters.
- `manual_review_items` and `errors`: bounded samples from existing tracking tables.

The endpoint requires `agent:runs:read`. It intentionally does not execute an agent, retry external calls, call LLM/search providers, submit proposals, apply dictionary changes, or publish snapshots.


### Patch 55A — Apply policy and risk levels

Proposal responses now include additive risk-policy metadata. The canonical
payload is stored in `validation_summary.apply_policy` and exposed on response
objects as `risk_level` and `apply_policy`.

```json
{
  "risk_level": "low",
  "apply_policy": {
    "schema_version": "skeinrank.apply_policy.v1",
    "risk_level": "low",
    "decision": "batch_approve_allowed",
    "can_batch_apply": true,
    "requires_reviewer": true,
    "requires_admin": false,
    "requires_warning_override": false,
    "auto_apply_allowed": false,
    "reasons": ["validation_passed_low_risk_thresholds"],
    "signals": {}
  }
}
```

Batch preview items additionally include `policy_can_batch_apply`,
`policy_requires_admin`, and `policy_reasons`. The policy is side-effect free and
does not change apply behavior in 55A: blocked validation summaries still block
apply, warning summaries still require explicit `allow_warnings: true`, and
automatic apply remains disabled.


## Role boundaries

`GET /v1/governance/role-boundaries` returns the current operator-facing role-boundary policy and current caller boundary.

Schema: `skeinrank.role_boundaries.v1`

Boundary mapping:

- `contributor` -> `agent`: read/validate/propose only.
- `moderator` -> `reviewer`: approve/reject and preview batches, but no apply/publish.
- `admin` -> `admin`: apply batches, publish snapshots, and manage users/tokens.

This endpoint is read-only and does not mutate governance state.

### Patch 55C — Token rotation / scoped agent credentials

Admins can inspect the recommended service-account credentials for agent
workflows:

```http
GET /v1/auth/scoped-agent-credentials
```

Response schema:

```text
skeinrank.scoped_agent_credentials.v1
```

Admins can rotate service-account tokens:

```http
POST /v1/auth/service-accounts/{account_name}/tokens/{token_id}/rotate
```

Request body:

```json
{
  "name": "agent token v2",
  "scopes": ["agent:tools:validate", "agent:tools:suggest"],
  "expires_in_days": 90
}
```

`name` and `scopes` are optional. When `scopes` is omitted, the replacement token
inherits the old token scopes. The response returns the replacement plaintext
`access_token` once and marks the old token as revoked.

The endpoint does not create admin-capable agent credentials by default. Use
`contributor` service accounts and explicit `agent:*` scopes for scheduled
agents.

## Profile isolation checks

Patch 55D adds a read-only isolation report for profile/binding safety:

```http
GET /v1/governance/isolation-checks
```

Response schema: `skeinrank.profile_isolation.v1`.

The endpoint reports whether binding-scoped rows stay inside their profile context across bindings, suggestions, binding policies, enrichment jobs, agent runs, and agent tracking tables. It also reports the request-guard surface that rejects profile/binding mismatches. The endpoint does not mutate state or call external providers.

Optional query parameter:

```text
sample_limit=20
```

Use a lower `sample_limit` when a degraded database may contain many issues.

## MCP integration packaging helpers

Patch 62A adds packaging helpers to the existing `skeinrank-mcp` console script.
They print local metadata and exit without starting the stdio server or calling
the Governance API:

```bash
poetry run skeinrank-mcp --print-tool-manifest
poetry run skeinrank-mcp --print-env-template
```

The tool manifest schema is:

```text
skeinrank.mcp_integration_manifest.v1
```

The full runbook and generic examples live in
`docs/deployment/mcp-integration-kit.md` and `examples/mcp-integration-kit/`.
