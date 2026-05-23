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

Patch 37A keeps the existing `governance_suggestions` workflow backward compatible while extending each suggestion with proposal metadata: optional `binding_id`, `proposal_source_type`, `proposal_source_name`, `idempotency_key`, `source_payload`, and `validation_summary`. Patch 37B adds a proposal checker registry that can generate `validation_summary` automatically when callers do not provide one. Checks cover canonical availability, alias collisions, stop-list guardrails, noisy aliases, confidence, idempotency hints, and agent audit payloads. This makes the existing review queue ready for agents and CLI/API automation without letting those callers mutate active runtime terminology directly.

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
