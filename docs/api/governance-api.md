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
GET /metrics
```

`/readyz` reports database and configured Elasticsearch readiness. `/metrics` exposes Prometheus-compatible metrics when enabled by configuration.

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
POST /v1/governance/elasticsearch/bindings/{binding_id}/jobs
GET  /v1/governance/elasticsearch/jobs?binding_id=...
GET  /v1/governance/elasticsearch/jobs/{job_id}
POST /v1/governance/elasticsearch/jobs/{job_id}/cancel
```

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
