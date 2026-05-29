# Headless runtime contracts

SkeinRank can run as a UI-backed governance console, but the product contract is headless-first. External services, CI/CD jobs, search backends, RAG pipelines, and agents should be able to use SkeinRank through stable contracts without relying on browser workflows.

## Contract map

| Contract | Meaning | Runtime rule |
| --- | --- | --- |
| Profile | Terminology meaning and governance scope. | Owns canonical terms, aliases, slots, stop lists, suggestions, and snapshots. |
| Binding | Production runtime search context. | Preferred runtime selector because it knows profile, index, fields, filters, and pinned snapshot. |
| Snapshot | Immutable terminology version. | Runtime uses a stable version, not live draft edits. |
| Artifact | Portable snapshot export. | Headless workers can load it from a file, Git, or object storage later. |
| Proposal | Draft terminology change. | Agents, CLI, API, and humans submit proposals; validation/review decides what becomes active. |
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

Patch 37A keeps the existing `governance_suggestions` workflow backward compatible while extending each suggestion with proposal metadata: optional `binding_id`, `proposal_source_type`, `proposal_source_name`, `idempotency_key`, `source_payload`, and `validation_summary`. Patch 37B adds a proposal checker registry that can generate `validation_summary` automatically when callers do not provide one. Checks cover canonical availability, alias collisions, stop-list guardrails, noisy aliases, confidence, idempotency hints, and agent audit payloads. Patch 37C adds a `/v1/tools/*` REST facade for agent-shaped actions: list runtime bindings, validate an alias proposal, submit an alias proposal, and explain query canonicalization. Patch 37D adds a batch apply endpoint that turns reviewed pending proposals into active terminology and can pin a fresh runtime snapshot on a binding in the same transaction. Patch 37E enforces idempotency keys for safe agent/CI retries. Patch 37F exposes the same safe tools over a thin MCP adapter. Patch 37G adds proposal Prometheus counters and a source-quality endpoint so reviewers can see which agents, jobs, or humans produce useful proposals. This makes the existing review queue ready for agents and CLI/API automation without letting those callers mutate active runtime terminology directly.

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

## UI scope

The UI should remain thin and audit-oriented:

- Search Playground for query explanation;
- proposals inbox for human-in-the-loop review;
- conflict review;
- snapshot state and diffs;
- schema/terminology inspection.

Operational health belongs in logs, `/metrics`, Prometheus, Grafana, and deployment checks.

## Current surfaces

The current project already exposes core pieces of this contract:

| Surface | Current route or tool |
| --- | --- |
| Dictionary validate/apply/export | `/v1/headless/dictionaries/*` |
| Text canonicalization | `/v1/text/canonicalize` |
| Query planning | `/v1/query/plan` |
| Binding-aware search | `/v1/search` |
| Multi-binding search | `/v1/search/multi` |
| Snapshot artifact export | `/v1/headless/snapshots/export?binding_id=...` |
| Snapshot state | `/v1/snapshots/summary` |
| Health/readiness | `/livez`, `/readyz` |
| Metrics | `/metrics` |

Future headless facade endpoints should reuse the same concepts instead of creating a second terminology model.


## Dictionary API facade

Headless integrations should use the automation-first dictionary facade:

```text
POST /v1/headless/dictionaries/validate
POST /v1/headless/dictionaries/apply
GET  /v1/headless/dictionaries/export?profile_name=...
```

This facade intentionally reuses the same dictionary spec v1 contract as the
console migration endpoints. The route names describe the product contract rather
than the current UI implementation: dictionaries can be validated, applied, and
exported without opening the governance console.

## Snapshot artifact export

Headless workers should not depend on browser workflows or live draft edits.
They can export a binding-scoped runtime artifact instead:

```text
GET /v1/headless/snapshots/export?binding_id=7
```

The exported artifact is intentionally binding-first: it contains the profile,
index/field/filter context, and the compiled runtime snapshot. This makes it safe
to store the artifact in Git, object storage, or a deployment bundle and later
load it into a lightweight runtime worker.

Use `source=latest` to build from current profile state. Use `source=runtime` to
export the currently pinned binding runtime snapshot.



## Runtime artifact file loader/cache

Patch 36E adds a local file loader for exported runtime artifacts. Lightweight
workers can now load the JSON artifact without talking to PostgreSQL at request
time:

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

The cache reloads a file when its modification time or size changes. This keeps
headless runtime workers simple: deployment can swap the artifact file, and the
worker can refresh the in-memory read model on the next lookup.

CLI inspection is available through:

```bash
skeinrank-migrate snapshot-inspect snapshots/platform_ops.binding-7.v1.json
```


## Headless Compose golden path

Patch 36F adds `docker-compose.headless.yml` for the API/PostgreSQL-only runtime contract smoke path. The profile intentionally excludes the UI, Elasticsearch, RabbitMQ, and Celery workers so a developer can validate the headless flow quickly:

```text
dictionary spec v1 -> /v1/headless/dictionaries/apply -> binding -> /v1/headless/snapshots/export -> runtime artifact file
```

The walkthrough lives in `docs/deployment/headless-quickstart.md`, and the helper script is `deploy/docker/scripts/headless-golden-path.sh`.

## MCP adapter boundary

Patch 37F adds a minimal MCP stdio server as an adapter over the existing
headless and agent-tool REST contracts. This keeps the architecture simple:

```text
MCP client / agent
  -> skeinrank-mcp stdio adapter
  -> /v1/tools/* and proposal review APIs
  -> PostgreSQL proposal/audit state
  -> reviewed snapshot publish
```

The MCP server is deliberately thin. It does not maintain a separate proposal
model and does not bypass validation, idempotency, role checks, or batch publish
logic. Agents can call tools such as `skeinrank_validate_alias` and
`skeinrank_submit_alias_proposal`, while SkeinRank remains the policy boundary
that validates, stores, reviews, and snapshots terminology changes.


## Coverage framework: term tags

Patch 38A introduces term tags as normalized facets on canonical terms. A term
still has one primary `slot`, while `tags` provide additional classification
for later conflict analysis, policies, and retrieval evaluation. Tags are stored
in governance state and exported through dictionary APIs.

Patch 38B carries those tags into runtime snapshot alias entries. Headless
artifacts, binding-pinned snapshots, `/v1/text/canonicalize`, and
`/v1/query/plan` can now expose matched term tags as runtime debug metadata.
This keeps existing alias tuple compatibility for enrichment while making tags
available to future conflict detection, policy resolution, and evaluation.


## Conflict detection report

Patch 38C adds a read-only conflict report as the first coverage-framework layer.
It scans governed terminology for alias drift, stop-list collisions, canonical slot
drift, and pending proposal conflicts. The report does not publish snapshots or
change active terms; it gives reviewers and agents a safe diagnostic surface
before later ambiguous-alias and binding-policy layers.

### Ambiguous aliases

An ambiguous alias is a governance record for a surface form that can safely mean different canonical terms in different runtime contexts. It stores candidates and review state, but it does not change production canonicalization unless a binding policy resolver selects one of its candidates for a binding-specific runtime context.

Patch 38F connects ambiguous aliases to proposals. A conflicting alias proposal is still stored as a pending proposal, but SkeinRank now also records candidate interpretations on the matching ambiguous alias surface. Active aliases become `active_alias` candidates, while proposal interpretations become `suggestion` candidates. This turns agent ambiguity into an auditable review object instead of silently rejecting or applying the proposal.

### Binding policy (Phase C)

A binding policy is optional metadata attached to a runtime binding. It does not mutate active terminology or publish a snapshot by itself. It records the constraints that later runtime resolution can use when an alias has multiple candidate interpretations:

- `preferred_slots` lists slots that should be preferred in this binding context.
- `allowed_tags` lists term tags that are safe for this binding context.
- `deny_slots` lists slots that should not be selected in this binding context.
- `context_rules` can pin a surface form to a preferred canonical value, for example `pg -> postgresql` for an infra binding.

This keeps the governance model explicit: ambiguous candidates are reviewed separately, while the binding policy describes how a specific runtime context is allowed to resolve them.


### Runtime policy resolver

Patch 38H applies active binding policies during binding-scoped runtime canonicalization and query planning. The resolver keeps active aliases as the default source, adds reviewed ambiguous candidates for the same surface, applies hard constraints (`deny_slots`, `allowed_tags`), and then selects a candidate through `context_rules`, preferred candidate status, or `preferred_slots`. Responses expose `policy_decisions` so reviewers can see why a surface such as `pg` resolved to `postgresql` in one binding and can remain unresolved or different in another.

## Snapshot evaluation contract

Patch 38I introduces an offline before/after evaluation report for runtime
snapshot artifacts. It compares two immutable artifacts and optionally applies a
sample query set to both alias maps.

```text
snapshot artifact v1 -> evaluator -> snapshot evaluation v1
```

The evaluator is intentionally read-only. It is suitable for CI/CD and GitOps
release gates where a team wants to inspect terminology drift before promoting a
new artifact. It highlights:

- added, removed, and changed aliases;
- added or removed runtime tags;
- sample queries whose canonicalized form changed;
- risk notes for removed aliases, changed mappings, and query-plan changes.

Agents and humans can use this report to decide whether a proposal batch should
be published, rolled back, or sent for additional review.


## Coverage framework examples

Patch 38J adds dedicated coverage docs and examples:

- `docs/concepts/coverage-framework.md` for the conceptual model;
- `docs/guides/coverage-framework.md` for API walkthroughs;
- `examples/coverage-framework/` for tagged dictionary, ambiguous alias, binding policy, and evaluation query payloads.

These files document the existing Phase C APIs. They do not add new runtime behavior; the resolver, policy model, ambiguous alias model, and evaluator are implemented by the preceding 38A-38I patches.

### MCP integration kit

Patch 62A adds an MCP integration kit around this boundary without changing the
runtime contract. The `skeinrank-mcp` adapter can print a local tool manifest
with `--print-tool-manifest` and an env template with `--print-env-template`.
These helpers make agent packaging easier while keeping all business logic in
the existing Governance API and proposal review flow.


## MCP adapter packaging smoke test

The `skeinrank-mcp` adapter exposes an offline smoke helper for client packaging
and CI checks:

```bash
skeinrank-mcp --smoke-test
```

Client-specific MCP docs for Claude Desktop, Cursor/IDE agents, and
LangGraph-style agents use the same stdio adapter and tool boundary. See
`docs/deployment/mcp-claude-desktop.md`, `docs/deployment/mcp-cursor-agents.md`,
`docs/deployment/mcp-langgraph-agents.md`, and `examples/mcp-agent-docs/`.

The output schema is `skeinrank.mcp_smoke_report.v1`. The helper does not call
the Governance API, create proposals, approve suggestions, publish snapshots, or
reload runtime state.
