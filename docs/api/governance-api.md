# Governance API reference

The Governance API is the HTTP control plane for SkeinRank terminology governance. It manages profiles, terms, aliases, suggestions, Elasticsearch/OpenSearch bindings, immutable runtime snapshots, agent proposal workflows, and operational reports.

The API package lives in `packages/skeinrank-governance-api`.

Start it locally:

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

## Operating model

SkeinRank separates authoring, review, publication, and runtime use:

```text
profile -> terms and aliases -> suggestions -> approved snapshot -> binding -> runtime API
```

Core concepts:

- **Profile**: terminology space for a domain, team, or corpus.
- **Term**: canonical value, primary slot, aliases, optional tags, and status.
- **Suggestion**: governed proposal for creating or changing terminology.
- **Snapshot**: immutable runtime dictionary exported from approved terminology.
- **Binding**: runtime search context that connects a profile snapshot to index, fields, filters, and write strategy.
- **Binding policy**: per-binding rules for preferred slots, allowed tags, denied slots, ambiguous aliases, and context triggers.

HTTP requests and responses are JSON unless noted otherwise. YAML is supported only by CLI helpers such as `skeinrank-migrate validate` and `skeinrank-migrate apply`.

## Health, readiness, and metrics

| Method | Path | Purpose |
|---|---|---|
| GET | `/livez` | Process liveness. |
| GET | `/healthz` | Process, database, and schema-health status. |
| GET | `/readyz` | Readiness for migrated schema and configured Elasticsearch/OpenSearch dependencies. |
| GET | `/schema/health` | Read-only Alembic/schema health report for operators and CI. |
| GET | `/metrics` | Prometheus-compatible metrics when metrics are enabled. |

Operational gauges to watch first:

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

CLI equivalent for schema checks:

```bash
poetry run python -m skeinrank_governance_api.migrations check
```

The schema check reports `current_revision`, `head_revision`, multiple Alembic heads, whether `alembic_version` exists, and SQLAlchemy metadata tables missing from the database.

## Operator reports

| Method | Path | Purpose |
|---|---|---|
| GET | `/v1/ops/troubleshooting/report` | Sanitized troubleshooting report with configuration, health checks, table counts, and recommendations. |
| GET | `/v1/ops/alerts/report` | Degraded-state alert report and sanitized webhook payload preview. |

The troubleshooting report never includes database credentials, API tokens, Elasticsearch passwords, request bodies, document text, or query text. When authentication is enabled, these endpoints require the `admin` role and the `ops:reports:read` token scope.

CLI equivalents:

```bash
poetry run python -m skeinrank_governance_api.troubleshooting report
poetry run python -m skeinrank_governance_api.troubleshooting report --strict
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

See `docs/deployment/alerting-hooks-degraded-state-reports.md` for alerting hooks and degraded-state examples.

## Headless dictionary workflows

Headless dictionary endpoints are the automation-first surface for CI, GitOps jobs, service integrations, and agents. They use the stable `skeinrank.dictionary.v1` payload.

| Method | Path | Purpose |
|---|---|---|
| POST | `/v1/headless/dictionaries/validate` | Validate a dictionary payload without writing to the database. |
| POST | `/v1/headless/dictionaries/apply` | Validate and apply profile, term, alias, and stop-list changes in one transaction. |
| GET | `/v1/headless/dictionaries/export?profile_name=...` | Export a profile dictionary with `schema_version`. |

Recommended CI flow:

```text
validate -> apply -> export -> create or publish runtime snapshot
```

Console-compatible endpoints remain available for the governance UI and legacy scripts:

| Method | Path | Purpose |
|---|---|---|
| POST | `/v1/console/dictionary/validate` | Validate the same dictionary shape through the console namespace. |
| POST | `/v1/console/dictionary/import` | Import a dictionary through the console namespace. |
| GET | `/v1/console/dictionary/export?profile_name=...` | Export a console-compatible dictionary. |

Both endpoint families share the same implementation and response shapes. New headless integrations should prefer `/v1/headless/dictionaries/*`.

## Headless snapshot artifacts

After a dictionary is applied and a binding exists, automation can export a portable binding-scoped runtime artifact.

| Method | Path | Purpose |
|---|---|---|
| GET | `/v1/headless/snapshots/export?binding_id=7` | Export a runtime snapshot artifact built from the current profile state. |
| GET | `/v1/headless/snapshots/export?binding_id=7&source=runtime` | Export the binding-pinned runtime snapshot; returns `409` when the binding has not published one yet. |

The artifact schema is `skeinrank.runtime_snapshot_artifact.v1` and includes binding context, profile identity, compiled runtime snapshot, manifest checksum, source, snapshot version, and alias count.

CLI equivalents:

```bash
skeinrank-migrate snapshot-export \
  --binding-id 7 \
  --snapshot-version platform_ops@v1 \
  --output snapshots/platform_ops.binding-7.v1.json

skeinrank-migrate snapshot-inspect snapshots/platform_ops.binding-7.v1.json
```

Headless workers can load artifacts with `RuntimeSnapshotArtifactCache`, which validates the manifest checksum and reloads the file when it changes.

## Terminology-as-Code import/export map

Terminology-as-Code uses existing HTTP and CLI surfaces rather than a separate endpoint family:

```text
Git dictionary file
  -> POST /v1/headless/dictionaries/validate
  -> POST /v1/headless/dictionaries/apply
  -> GET  /v1/headless/dictionaries/export?profile_name=...
  -> GET  /v1/headless/snapshots/export?binding_id=...
  -> runtime artifact delivery through GitOps or object storage
```

Use `skeinrank-migrate validate`, `skeinrank-migrate apply`, `skeinrank-migrate export`, and `skeinrank-migrate snapshot-export` for the same workflow from CI scripts. See `docs/guides/terminology-as-code.md`, `docs/guides/dictionary-cli-planning.md`, and `docs/deployment/gitops-delivery-runbook.md` for the full runbook and examples.

## Profiles, stop lists, terms, aliases, and snapshots

| Method | Path | Purpose |
|---|---|---|
| GET | `/v1/governance/profiles` | List profiles. |
| POST | `/v1/governance/profiles` | Create a profile. |
| PATCH | `/v1/governance/profiles/{profile_name}` | Update profile metadata. |
| DELETE | `/v1/governance/profiles/{profile_name}` | Delete a profile. |
| GET | `/v1/governance/profiles/{profile_name}/stop-list` | List profile stop-list entries. |
| POST | `/v1/governance/profiles/{profile_name}/stop-list` | Create a profile stop-list entry. |
| PATCH | `/v1/governance/profiles/{profile_name}/stop-list/{entry_id}` | Update a profile stop-list entry. |
| DELETE | `/v1/governance/profiles/{profile_name}/stop-list/{entry_id}` | Delete a profile stop-list entry. |
| GET | `/v1/governance/global-stop-list` | List global stop-list entries. |
| POST | `/v1/governance/global-stop-list` | Create a global stop-list entry. |
| PATCH | `/v1/governance/global-stop-list/{entry_id}` | Update a global stop-list entry. |
| DELETE | `/v1/governance/global-stop-list/{entry_id}` | Delete a global stop-list entry. |
| GET | `/v1/governance/profiles/{profile_name}/terms` | List terms for a profile. |
| POST | `/v1/governance/profiles/{profile_name}/terms` | Add a canonical term. |
| GET | `/v1/governance/profiles/{profile_name}/terms/{canonical_value}` | Read one term. |
| PATCH | `/v1/governance/profiles/{profile_name}/terms/{canonical_value}` | Update a term. |
| DELETE | `/v1/governance/profiles/{profile_name}/terms/{canonical_value}` | Delete a term. |
| POST | `/v1/governance/profiles/{profile_name}/terms/{canonical_value}/aliases` | Add an alias to a term. |
| PATCH | `/v1/governance/profiles/{profile_name}/terms/{canonical_value}/aliases/{alias_id}` | Update an alias. |
| DELETE | `/v1/governance/profiles/{profile_name}/terms/{canonical_value}/aliases/{alias_id}` | Delete an alias. |
| POST | `/v1/governance/profiles/{profile_name}/snapshot/export` | Export a runtime-compatible profile snapshot. |
| GET | `/v1/snapshots/summary` | Read snapshot summary metadata for the dashboard. |

Terms support `primary_slot`, aliases, optional `tags`, status, and evidence-backed review metadata.

## Suggestions, evidence, and apply gates

Suggestions are the human-in-the-loop workflow for terminology changes. Agents and CI jobs can submit proposal-shaped data, but production mutation remains gated by validation, policy, and reviewer decisions.

| Method | Path | Purpose |
|---|---|---|
| GET | `/v1/governance/profiles/{profile_name}/suggestions` | List suggestions for a profile. |
| POST | `/v1/governance/profiles/{profile_name}/suggestions` | Create a suggestion. |
| POST | `/v1/governance/profiles/{profile_name}/suggestions/{suggestion_id}/evidence/refresh` | Refresh evidence for a suggestion. |
| POST | `/v1/governance/profiles/{profile_name}/suggestions/{suggestion_id}/approve` | Approve a suggestion. |
| POST | `/v1/governance/profiles/{profile_name}/suggestions/{suggestion_id}/reject` | Reject a suggestion. |
| POST | `/v1/governance/profiles/{profile_name}/suggestions/apply-batch/preview` | Dry-run batch apply and return warnings/blocks. |
| POST | `/v1/governance/profiles/{profile_name}/suggestions/apply-batch` | Apply an approved batch with validation-warning gates. |
| GET | `/v1/governance/proposals/source-quality` | Read source-quality metadata for proposal review. |

Batch apply is idempotent by proposal identity and blocks validation-warning proposals by default. Use explicit warning allowance only after reviewer approval.

Apply-policy risk levels:

```text
low
medium
high
blocked
```

High-risk or blocked changes include destructive runtime mutations, secret exfiltration attempts, and prompt-like instructions embedded in evidence or imported terminology. Prompt-like content is surfaced as review metadata; it is not treated as an instruction to the system.

## Conflict detection and coverage framework

The conflict report is read-only. It surfaces terminology drift risks without changing active terminology or runtime snapshots.

| Method | Path | Purpose |
|---|---|---|
| GET | `/v1/governance/conflicts` | List cross-profile and in-profile terminology conflicts. |
| GET | `/v1/governance/conflicts?profile_name=infra_incidents` | Filter conflicts by profile. |
| GET | `/v1/governance/conflicts?profile_name=infra_incidents&include_suggestions=false` | Exclude pending suggestions from the report. |
| PATCH | `/v1/governance/conflicts/{fingerprint}/review` | Mark a conflict as `open`, `ignored`, or `resolved`. |

The report detects active alias surfaces reused across profiles, active aliases mapped to multiple canonical terms, canonical surfaces used with different primary slots, stop-list collisions, and pending proposals that conflict with active or pending terminology.

Coverage framework routes and examples:

- `docs/concepts/coverage-framework.md`
- `docs/guides/coverage-framework.md`
- `examples/coverage-framework`
- `/v1/headless/dictionaries/apply`
- `/v1/governance/profiles/coverage_ops/ambiguous-aliases`
- `/v1/governance/elasticsearch/bindings/1/policy`
- `/v1/query/plan`

## Ambiguous aliases and binding policy

Ambiguous aliases represent surface forms that can map to multiple canonical meanings. Binding policy decides which interpretation is safe for a runtime context.

| Method | Path | Purpose |
|---|---|---|
| GET | `/v1/governance/profiles/{profile_name}/ambiguous-aliases` | List ambiguous aliases for a profile. |
| POST | `/v1/governance/profiles/{profile_name}/ambiguous-aliases` | Create or replace an ambiguous alias record. |
| GET | `/v1/governance/profiles/{profile_name}/ambiguous-aliases/{surface_value}` | Read one ambiguous alias record. |
| PATCH | `/v1/governance/profiles/{profile_name}/ambiguous-aliases/{surface_value}` | Update review state or candidate metadata. |
| GET | `/v1/governance/elasticsearch/bindings/{binding_id}/policy` | Read binding policy. |
| PUT | `/v1/governance/elasticsearch/bindings/{binding_id}/policy` | Create or replace binding policy. |
| DELETE | `/v1/governance/elasticsearch/bindings/{binding_id}/policy` | Remove binding policy. |

Binding policy can define preferred slots, allowed tags, denied slots, context triggers, and explicit ambiguous-alias decisions. Runtime decisions are returned as `policy_decisions` where supported by query planning.

## Elasticsearch/OpenSearch discovery and bindings

Elasticsearch/OpenSearch endpoints are used to inspect index readiness, create bindings, preview enrichment, refresh evidence, and run controlled enrichment jobs.

| Method | Path | Purpose |
|---|---|---|
| GET | `/v1/governance/elasticsearch/connection/status` | Check configured Elasticsearch/OpenSearch connectivity. |
| GET | `/v1/governance/elasticsearch/indices` | List available indices. |
| GET | `/v1/governance/elasticsearch/indices/{index_name}/mapping` | Read one index mapping. |
| GET | `/v1/governance/elasticsearch/bindings` | List bindings. |
| POST | `/v1/governance/elasticsearch/bindings` | Create a binding. |
| PATCH | `/v1/governance/elasticsearch/bindings/{binding_id}` | Update a binding. |
| DELETE | `/v1/governance/elasticsearch/bindings/{binding_id}` | Delete a binding. |
| POST | `/v1/governance/elasticsearch/bindings/{binding_id}/dry-run` | Preview canonicalization/enrichment matches without writing. |
| POST | `/v1/governance/elasticsearch/bindings/{binding_id}/evidence` | Fetch read-only evidence for candidate terms or aliases. |
| POST | `/v1/governance/elasticsearch/bindings/{binding_id}/jobs/preflight` | Validate an enrichment job request and return the per-run confirmation token. |
| POST | `/v1/governance/elasticsearch/bindings/{binding_id}/jobs` | Start an enrichment job with the current confirmation token. |
| GET | `/v1/governance/elasticsearch/jobs?binding_id=...` | List enrichment jobs, optionally filtered by binding. |
| GET | `/v1/governance/elasticsearch/jobs/{job_id}` | Read job status, progress, checkpoint, and rollout metadata. |
| POST | `/v1/governance/elasticsearch/jobs/{job_id}/cancel` | Request cancellation. |
| POST | `/v1/governance/elasticsearch/jobs/{job_id}/pause` | Request pause for a resumable job. |
| POST | `/v1/governance/elasticsearch/jobs/{job_id}/resume` | Resume a paused job. |
| POST | `/v1/governance/elasticsearch/jobs/{job_id}/rollback` | Roll back a completed alias-swap rollout when rollback metadata is available. |

Supported write strategies are `in_place` and `reindex_alias_swap`. Use preflight before long-running jobs to inspect `blocking_issues`, copy the `confirmation_token`, and start only the exact plan that was reviewed.

Blue/green alias-swap runbook: `../deployment/blue-green-alias-swap-runbook.md`.

Additional guides:

- `docs/guides/elasticsearch-enrichment.md`
- `docs/guides/enrichment-beta-hardening.md`
- `docs/guides/enrichment-pause-resume-checkpointing.md`

## Runtime search and canonicalization

Runtime routes serve binding-aware canonicalization and search. Production callers should pass `binding_id` whenever possible because a binding defines the search context, pinned snapshot, fields, filters, and policy.

| Method | Path | Purpose |
|---|---|---|
| POST | `/v1/text/canonicalize` | Canonicalize text by profile preview mode or binding-pinned runtime mode. |
| POST | `/v1/query/plan` | Build a query expansion plan and expose canonicalization decisions. |
| POST | `/v1/query/route-plan` | Build a multi-binding route plan for one query. |
| POST | `/v1/search` | Execute search for one binding. |
| POST | `/v1/search/multi` | Fan out search across several bindings and merge results. |

`POST /v1/query/route-plan` is read-only. Requests provide `candidate_binding_ids`; responses return `mode = "route_plan_only"` with `selected_bindings`, `rejected_bindings`, and `failed_bindings` so applications can explain routing before deciding whether to call `/v1/search` or `/v1/search/multi`.

Production guidance:

```json
{
  "binding_id": 7,
  "query": "k8s pg timeout",
  "size": 10
}
```

Preview/dev flows may use `profile_name`, but binding-scoped runtime mode is the safer production default.

Alias context triggers allow a binding policy to prefer one candidate when specific query tokens or runtime fields are present. No separate runtime endpoint is required for this behavior.

## Agent-friendly proposal tools

`/v1/tools/*` is the REST surface used by the MCP server, reference agents, and service integrations. Tools are proposal-first: agents can list context, explain queries, validate aliases, submit proposals, and check proposal status through the suggestions API. They cannot directly publish snapshots or mutate production runtime state.

| Method | Path | Purpose |
|---|---|---|
| GET | `/v1/tools/bindings` | List enabled binding contexts for agent use. |
| POST | `/v1/tools/explain-query` | Return a binding/profile-aware query plan for an agent. |
| POST | `/v1/tools/validate-alias` | Validate an alias proposal without applying it. |
| POST | `/v1/tools/suggest-alias` | Submit a pending alias suggestion. |
| GET | `/v1/governance/profiles/{profile_name}/suggestions` | Check proposal status through the governed suggestions list. |

Allowed MCP tool names:

```text
skeinrank_list_bindings
skeinrank_explain_query
skeinrank_validate_alias
skeinrank_submit_alias_proposal
skeinrank_get_proposal_status
```

See `docs/deployment/mcp-integration-kit.md` and `examples/mcp-integration-kit`.

MCP client guides:

- `docs/deployment/mcp-claude-desktop.md`
- `docs/deployment/mcp-cursor-agents.md`
- `docs/deployment/mcp-langgraph-agents.md`
- `examples/agents/openrouter_alias_scout`
- `examples/mcp-agent-docs`

Scoped MCP credentials and smoke tests:

- `docs/deployment/mcp-scoped-credentials-smoke-tests.md`
- `examples/mcp-scoped-credentials`

## Agent run registry and progress

The agent registry tracks local or service-run discovery workflows without granting direct runtime mutation. It records run metadata, document visits, candidate observations, evidence windows, LLM reviews, proposal attempts, progress, resume plans, and sanitized reports.

| Method | Path | Purpose |
|---|---|---|
| POST | `/v1/agents/runs` | Create or upsert an agent run. |
| GET | `/v1/agents/runs` | List runs; supports filters such as `profile_name`. |
| GET | `/v1/agents/runs/{run_id}` | Read one run. |
| PATCH | `/v1/agents/runs/{run_id}` | Update run status or metadata. |
| POST | `/v1/agents/runs/{run_id}/document-visits` | Record a document visit. |
| GET | `/v1/agents/runs/{run_id}/document-visits` | List document visits. |
| POST | `/v1/agents/runs/{run_id}/candidate-observations` | Record a candidate alias/term observation. |
| GET | `/v1/agents/runs/{run_id}/candidate-observations` | List candidate observations. |
| GET | `/v1/agents/runs/{run_id}/evidence-windows` | List compact evidence windows for review. |
| POST | `/v1/agents/runs/{run_id}/llm-reviews` | Record an LLM review. |
| GET | `/v1/agents/runs/{run_id}/llm-reviews` | List LLM reviews. |
| POST | `/v1/agents/runs/{run_id}/proposal-attempts` | Record a proposal validation/submission attempt. |
| GET | `/v1/agents/runs/{run_id}/proposal-attempts` | List proposal attempts. |
| GET | `/v1/agents/runs/{run_id}/progress` | Read progress counters and run status. |
| POST | `/v1/agents/runs/{run_id}/resume-plan` | Build a read-only resume/retry plan. |
| GET | `/v1/agents/runs/{run_id}/report` | Read a sanitized diagnostics report for one run. |

The resume plan is read-only. It reports skipped/revisited documents, retry candidates, and configured batch limits without queueing work.

## Auth, users, service accounts, and scoped tokens

Authentication is optional for local development and recommended for shared environments. When enabled, role checks and token scopes protect mutation, admin, agent, and ops surfaces.

| Method | Path | Purpose |
|---|---|---|
| POST | `/v1/auth/login` | Create a session/token from credentials. |
| POST | `/v1/auth/logout` | End the current session. |
| GET | `/v1/auth/me` | Read current principal metadata. |
| GET | `/v1/auth/users` | List users. |
| POST | `/v1/auth/users` | Create a user. |
| PATCH | `/v1/auth/users/{username}` | Update user metadata. |
| PATCH | `/v1/auth/users/{username}/status` | Activate/deactivate a user. |
| POST | `/v1/auth/users/{username}/revoke-api-tokens` | Revoke all API tokens for a user. |
| DELETE | `/v1/auth/users/{username}` | Delete a user. |
| GET | `/v1/auth/api-tokens` | List personal API tokens. |
| POST | `/v1/auth/api-tokens` | Create a personal API token. |
| DELETE | `/v1/auth/api-tokens/{token_id}` | Revoke a personal API token. |
| GET | `/v1/auth/service-accounts` | List service accounts. |
| POST | `/v1/auth/service-accounts` | Create a service account. |
| PATCH | `/v1/auth/service-accounts/{account_name}` | Update a service account. |
| DELETE | `/v1/auth/service-accounts/{account_name}` | Delete a service account. |
| GET | `/v1/auth/service-accounts/{account_name}/tokens` | List service-account tokens. |
| POST | `/v1/auth/service-accounts/{account_name}/tokens` | Create a scoped service-account token. |
| POST | `/v1/auth/service-accounts/{account_name}/tokens/{token_id}/rotate` | Rotate a service-account token. |
| DELETE | `/v1/auth/service-accounts/{account_name}/tokens/{token_id}` | Revoke a service-account token. |
| GET | `/v1/auth/scoped-agent-credentials` | Read the recommended scoped credentials policy for agents and MCP. |

Recommended MCP service-account scopes:

```text
agent:tools:read
agent:tools:validate
agent:tools:suggest
agent:tools:explain
```

See `docs/deployment/mcp-scoped-credentials-smoke-tests.md` for least-privilege examples.

## Dashboard and status summaries

| Method | Path | Purpose |
|---|---|---|
| GET | `/v1/dashboard/summary` | Governance console dashboard summary. |
| GET | `/v1/governance/isolation-checks` | Profile/binding isolation report. |
| GET | `/v1/governance/role-boundaries` | Human/agent/admin role boundary report. |

Isolation checks help detect bindings that could leak terminology across profiles or runtime contexts.

## Copyable endpoint quick list

The tables above are the canonical grouping. This copyable list keeps runbooks and docs tests anchored to exact route strings:

```text
GET /v1/ops/troubleshooting/report
GET /v1/ops/alerts/report
GET /v1/auth/scoped-agent-credentials
POST /v1/auth/service-accounts
POST /v1/auth/service-accounts/{account_name}/tokens/{token_id}/rotate
POST /v1/headless/dictionaries/validate
POST /v1/headless/dictionaries/apply
GET /v1/headless/dictionaries/export?profile_name=...
GET /v1/headless/snapshots/export?binding_id=...
POST /v1/governance/elasticsearch/bindings/{binding_id}/jobs/preflight
POST /v1/governance/elasticsearch/bindings/{binding_id}/jobs
GET /v1/governance/elasticsearch/jobs?binding_id=...
POST /v1/governance/elasticsearch/jobs/{job_id}/cancel
POST /v1/governance/elasticsearch/jobs/{job_id}/pause
POST /v1/governance/elasticsearch/jobs/{job_id}/resume
POST /v1/governance/elasticsearch/jobs/{job_id}/rollback
GET /v1/tools/bindings
POST /v1/tools/explain-query
POST /v1/tools/validate-alias
POST /v1/tools/suggest-alias
GET /v1/governance/profiles/{profile_name}/suggestions
POST /v1/text/canonicalize
POST /v1/query/plan
POST /v1/query/route-plan
POST /v1/search
POST /v1/search/multi
```

## Safety boundaries

The Governance API treats documents, evidence snippets, dictionary imports, user queries, and model outputs as untrusted data. Prompt-like instructions are surfaced as risk metadata for review instead of being executed.

Runtime mutation remains proposal-first:

- agents may validate and suggest;
- reviewers approve or reject;
- snapshots are immutable;
- bindings pin runtime state;
- production rollout uses explicit publish/enrichment workflows;
- MCP tools are allow-listed and schema-constrained.

Security docs:

- `docs/security/prompt-injection.md`
- `docs/security/prompt-like-detector.md`
- `docs/security/prompt-injection-regression-corpus.md`
- `docs/security/mcp-tool-guardrails.md`
- `docs/security/agent-tool-safety.md`
- `docs/security/rag-context-boundaries.md`

## Related docs and examples

- `docs/README.md`
- `packages/skeinrank-governance-api/README.md`
- `docs/concepts/headless-runtime-contracts.md`
- `docs/deployment/headless-quickstart.md`
- `docs/deployment/gitops-delivery-runbook.md`
- `docs/deployment/mcp-integration-kit.md`
- `docs/deployment/blue-green-alias-swap-runbook.md`
- `docs/guides/terminology-as-code.md`
- `docs/guides/coverage-framework.md`
- `docs/guides/elasticsearch-enrichment.md`
- `examples/terminology-as-code`
- `examples/coverage-framework`
- `examples/mcp-integration-kit`
- `examples/mcp-agent-docs`
