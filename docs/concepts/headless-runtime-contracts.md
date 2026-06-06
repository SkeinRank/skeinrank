# Headless runtime contracts

SkeinRank can run as a UI-backed governance console, but the product contract is headless-first. External services, CI/CD jobs, search backends, RAG pipelines, and agents should be able to use SkeinRank through stable contracts without relying on browser workflows.

## Contract map

| Contract | Meaning | Runtime rule |
| --- | --- | --- |
| Profile | Terminology meaning and governance scope. | Owns canonical terms, aliases, slots, stop lists, suggestions, and snapshots. |
| Binding | Production runtime search context. | Preferred runtime selector because it knows profile, index, fields, filters, and pinned snapshot. |
| Snapshot | Immutable terminology version. | Runtime uses a stable version, not live draft edits. |
| Artifact | Portable snapshot export. | Headless workers can load it from a file, Git, or object storage later. |
| Proposal | Draft terminology change. | Agents, CLI, API, and humans submit proposals; validation and review decide what becomes active. |
| Runtime | Read path for canonicalization/search/enrichment. | Uses `binding_id` plus pinned snapshot context whenever possible. |

## Write model vs read model

SkeinRank separates governance writes from runtime reads.

```text
Agents / CLI / UI / CI
        ↓
Write side: PostgreSQL-backed governance state
        ↓
Validators, evidence, approval, audit
        ↓
Snapshot metadata and compiled artifact
        ↓
Read side: canonicalize, query-plan, search, enrich
```

PostgreSQL is the source of truth for changing state: profiles, terms, aliases, stop lists, bindings, suggestions/proposals, reviewer decisions, and snapshot metadata.

The proposal workflow is the write-side safety boundary. Suggestions can carry `binding_id`, `proposal_source_type`, `proposal_source_name`, `idempotency_key`, `source_payload`, and `validation_summary`. The checker registry can add validation details for canonical availability, alias collisions, stop-list guardrails, noisy aliases, confidence, idempotency hints, and agent audit payloads. Agent-shaped tools expose safe proposal surfaces through `/v1/tools/*`, while reviewer gates and apply flows decide what becomes active terminology.

A runtime artifact is the immutable read model. It can be exported as JSON and loaded by services that only need fast canonicalization or query planning.

## Binding-first runtime

A profile tells SkeinRank what terminology means. A binding tells SkeinRank where and how that terminology is applied.

For production runtime, prefer:

```json
{
  "binding_id": 7,
  "query": "k8s pg timeout"
}
```

A binding can carry:

- profile reference;
- Elasticsearch index or alias;
- source text fields;
- target enrichment field;
- optional discriminator field and value;
- timestamp field and time window;
- write strategy;
- active/pending runtime snapshot state.

This keeps shared-index and multi-domain cases safe. The same alias can have different meanings in different bindings, so runtime clients should not rely on one global dictionary.

## Agents and drift control

Agents are useful for discovering terminology drift, failed-query patterns, new aliases, and weak coverage. They must not be allowed to directly mutate production terminology.

The safe contract is:

```text
agent output -> proposal -> validation -> review/policy -> snapshot -> runtime
```

This protects the runtime from:

- alias pollution;
- semantic drift;
- hallucinated terminology;
- cross-domain conflicts;
- over-expansion that increases recall but hurts precision;
- prompt-injection or malicious document content;
- stale or inconsistent runtime versions.

Agents are proposal sources, not sources of truth. A model, CLI, CI job, or MCP client can suggest changes, but approved state plus evidence, policy, audit trail, and snapshot publication defines what the runtime may serve.

## UI scope

The UI should remain thin and audit-oriented:

- Search Playground for query explanation;
- proposals inbox for human-in-the-loop review;
- conflict review;
- snapshot state and diffs;
- schema/terminology inspection.

Operational health belongs in logs, `/metrics`, Prometheus, Grafana, and deployment checks.

## Runtime surfaces

The current project exposes the core pieces of this contract:

| Surface | Current route or tool |
| --- | --- |
| Legacy console dictionary validate/import/export | `/v1/console/dictionary/*` |
| Headless dictionary validate/apply/export | `/v1/headless/dictionaries/*` |
| Text canonicalization | `/v1/text/canonicalize` |
| Query planning | `/v1/query/plan` |
| Read-only multi-binding route planning | `/v1/query/route-plan` |
| Binding-aware search | `/v1/search` |
| Multi-binding search | `/v1/search/multi` |
| Snapshot artifact export | `/v1/headless/snapshots/export?binding_id=...` |
| Snapshot state | `/v1/snapshots/summary` |
| Health/readiness | `/livez`, `/readyz` |
| Metrics | `/metrics` |

Headless facade endpoints should reuse these concepts instead of creating a second terminology model. Runtime request bodies can use `binding_id` or stable `binding_name`, while `profile_name` remains useful for preview and development flows. Runtime responses expose `runtime_context` so callers can audit the binding, fields, filters, target field, snapshot source, and optional `application_scope` metadata that selected the binding.

## Dictionary API facade

Headless integrations should use the automation-first dictionary facade:

```text
POST /v1/headless/dictionaries/validate
POST /v1/headless/dictionaries/apply
GET  /v1/headless/dictionaries/export?profile_name=...
```

This facade intentionally reuses the same dictionary spec v1 contract as the console migration endpoints. The route names describe the product contract rather than the current UI implementation: dictionaries can be validated, applied, and exported without opening the governance console.

## Snapshot artifact export

Headless workers should not depend on browser workflows or live draft edits. They can export a binding-scoped runtime artifact instead:

```text
GET /v1/headless/snapshots/export?binding_id=7
```

The exported artifact is binding-first: it contains the profile, index/field/filter context, and the compiled runtime snapshot. This makes it safe to store the artifact in Git, object storage, or a deployment bundle and later load it into a lightweight runtime worker.

Use `source=latest` to build from current profile state. Use `source=runtime` to export the currently pinned binding runtime snapshot.

## Runtime artifact file loader/cache

Lightweight workers can load an exported JSON artifact without talking to PostgreSQL at request time:

```python
from skeinrank_governance_api.runtime_snapshots import RuntimeSnapshotArtifactCache

cache = RuntimeSnapshotArtifactCache()
loaded = cache.get("snapshots/platform_ops.binding-7.v1.json")

print(loaded.snapshot_version)
print(len(loaded.alias_entries))
```

The loader validates:

- `schema_version: skeinrank.runtime_snapshot_artifact.v1`;
- `artifact_type: runtime_snapshot`;
- binding/profile/runtime snapshot sections;
- manifest checksum.

The cache reloads a file when its modification time or size changes. This keeps headless runtime workers simple: deployment can swap the artifact file, and the worker can refresh the in-memory read model on the next lookup.

CLI inspection is available through:

```bash
skeinrank-migrate snapshot-inspect snapshots/platform_ops.binding-7.v1.json
```

## Headless Compose golden path

`docker-compose.headless.yml` provides an API/PostgreSQL-only runtime contract smoke path. The profile intentionally excludes the UI, Elasticsearch, RabbitMQ, and Celery workers so a developer can validate the headless flow quickly:

```text
dictionary spec v1 -> /v1/headless/dictionaries/apply -> binding -> /v1/headless/snapshots/export -> runtime artifact file
```

The walkthrough lives in `docs/deployment/headless-quickstart.md`, and the helper script is `deploy/docker/scripts/headless-golden-path.sh`.

## MCP adapter boundary

The `skeinrank-mcp` stdio adapter sits over the existing headless and agent-tool REST contracts:

```text
MCP client / agent
  -> skeinrank-mcp stdio adapter
  -> /v1/tools/* and proposal review APIs
  -> PostgreSQL proposal/audit state
  -> reviewed snapshot publish
```

The MCP server is deliberately thin. It does not maintain a separate proposal model and does not bypass validation, idempotency, role checks, or batch publish logic. Agents can call tools such as `skeinrank_validate_alias` and `skeinrank_submit_alias_proposal`, while SkeinRank remains the policy boundary that validates, stores, reviews, and snapshots terminology changes.

The adapter can print a local tool manifest with:

```bash
skeinrank-mcp --print-tool-manifest
```

It can print an environment template with:

```bash
skeinrank-mcp --print-env-template
```

It also exposes an offline smoke helper for client packaging and CI checks:

```bash
skeinrank-mcp --smoke-test
```

The output schema is `skeinrank.mcp_smoke_report.v1`. The helper does not call the Governance API, create proposals, approve suggestions, publish snapshots, or reload runtime state.

Client-specific MCP docs for Claude Desktop, Cursor/IDE agents, and LangGraph-style agents use the same stdio adapter and tool boundary. See `docs/deployment/mcp-claude-desktop.md`, `docs/deployment/mcp-cursor-agents.md`, `docs/deployment/mcp-langgraph-agents.md`, and `examples/mcp-agent-docs/`.

## Coverage framework

The coverage framework extends the runtime contract without changing the binding-first model:

- `tags` are normalized facets on canonical terms. A term still has one primary `slot`, while `tags` provide additional classification for conflict analysis, policies, and retrieval evaluation.
- Runtime snapshot alias entries can expose matched term tags as debug metadata for `/v1/text/canonicalize` and `/v1/query/plan`.
- Read-only conflict reports scan governed terminology for alias drift, stop-list collisions, canonical slot drift, and pending proposal conflicts.
- Ambiguous aliases store possible interpretations for one surface form, including `active_alias` and `suggestion` candidates.
- Binding policies define `preferred_slots`, `allowed_tags`, `deny_slots`, and `context_rules` for one runtime binding.
- Runtime canonicalization and query planning expose `policy_decisions` when a binding policy selects or rejects ambiguous candidates.

These concepts are documented in `docs/concepts/coverage-framework.md`, `docs/guides/coverage-framework.md`, and `examples/coverage-framework/`.

## Snapshot evaluation contract

The snapshot evaluation contract compares immutable runtime artifacts before a new artifact is promoted:

```text
snapshot artifact v1 -> evaluator -> snapshot evaluation v1
```

The evaluator is read-only and suitable for CI/CD and GitOps release gates. It highlights:

- added, removed, and changed aliases;
- added or removed runtime tags;
- sample queries whose canonicalized form changed;
- risk notes for removed aliases, changed mappings, and query-plan changes.

Agents and humans can use this report to decide whether a proposal batch should be published, rolled back, or sent for additional review.

## Read-only route planning

Global search surfaces can call `POST /v1/query/route-plan` with `candidate_binding_ids` before deciding whether to execute `/v1/search` for one binding or `/v1/search/multi` for several bindings. The route planner returns `mode = "route_plan_only"` and never executes Elasticsearch search or mutates runtime state.

Route-plan responses can include `selected_bindings`, `rejected_bindings`, and `failed_bindings` so applications can explain why a binding was selected or skipped before running a fan-out search.
