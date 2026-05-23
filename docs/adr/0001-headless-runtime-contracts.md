# ADR 0001: Headless runtime contracts

Status: Accepted

Date: 2026-05-23

## Context

SkeinRank started as a terminology governance platform with a console, Elasticsearch evidence workflows, enrichment jobs, and runtime endpoints. The next product direction is headless-first: teams should be able to connect SkeinRank from CI/CD, internal services, RAG pipelines, and agents without depending on the UI as the primary write path.

This ADR consolidates the runtime contract names that future patches should use. It does not introduce new API behavior by itself. It documents the current and intended boundaries so that future headless, proposal, MCP, and UI work can evolve without renaming the core model every few patches.

## Decision

SkeinRank uses these product contracts:

```text
Profile   = terminology meaning and governance scope
Binding   = production runtime search context
Snapshot  = immutable terminology version safe for runtime
Artifact  = portable snapshot export for headless readers
Proposal  = draft terminology change submitted by humans, agents, CLI, or API
Runtime   = read path that canonicalizes, plans, searches, or enriches using a binding and snapshot
```

The production read path is binding-first. Runtime clients should prefer `binding_id` because a binding knows the profile, index or collection, selected fields, optional discriminator filters, and pinned snapshot state.

Agents are proposal sources, not sources of truth. An LLM, OpenRouter-backed agent, internal model, CLI, or CI job may submit a proposal, but it must not mutate production terminology directly. Approved state plus evidence, policy, audit trail, and snapshot publication defines what the runtime may serve.

PostgreSQL remains the write-side state store for profiles, terms, aliases, stop lists, bindings, suggestions/proposals, audit metadata, and snapshot metadata. Runtime artifacts are read-side exports: JSON files today, with possible Git/S3 delivery later. This keeps writes transactional while allowing lightweight runtime workers to load immutable snapshots without owning governance state.

## Contract boundaries

### Write side

The write side accepts and validates changes:

- dictionary validation and import/export;
- governance CRUD for profiles, terms, aliases, stop lists, bindings, and suggestions;
- proposal intake and validation in future patches;
- evidence snapshots and reviewer decisions;
- snapshot metadata and publication state.

Write-side state can be rich, relational, audited, and slower than the read path.

### Read side

The read side serves stable runtime context:

- text canonicalization;
- query planning;
- binding-aware search;
- multi-binding search fan-out;
- enrichment jobs that use a pinned snapshot;
- future artifact-loaded workers.

Read-side clients should not depend on live mutable edits. They should use a binding and the binding's pinned snapshot or a compiled artifact produced from it.

### UI role

The UI is an audit and debug surface, not the only control path.

The console remains useful for:

- Search Playground and query explanation;
- proposal inbox and human-in-the-loop review;
- conflict inspection;
- snapshot state and diffs;
- evidence review.

Operational metrics should remain observable through `/metrics`, Prometheus, Grafana, and logs rather than being reimplemented as the main SkeinRank UI dashboard.

## Current API alignment

The current platform already contains several pieces aligned with this ADR:

- dictionary validation/import/export under `/v1/console/dictionary/*`;
- runtime canonicalization under `/v1/text/canonicalize`;
- query planning under `/v1/query/plan`;
- binding-aware search under `/v1/search` and `/v1/search/multi`;
- snapshot state under `/v1/snapshots/summary`;
- service health and observability under `/livez`, `/readyz`, and `/metrics`.

Future headless facade endpoints may wrap existing console routes, but should preserve these contract names and the binding-first runtime rule.

## Consequences

Future patches should avoid introducing parallel names for the same concepts. In particular:

- do not use `profile_name` as the primary production runtime context when `binding_id` is available;
- do not let agents apply aliases directly to the active profile without proposal validation;
- do not make runtime workers depend on mutable draft state;
- do not make the UI the only supported path for dictionary application, snapshot publication, or query debugging.

This ADR makes the next phases explicit:

```text
Headless API / CLI -> proposals and validators -> snapshot artifacts -> runtime readers -> thin audit UI
```
