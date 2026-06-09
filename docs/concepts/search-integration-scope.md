# Search integration scope

SkeinRank is a terminology control plane, not a search-engine management platform.

The project owns governed terminology artifacts: profiles, aliases, evidence, proposals, snapshots, bindings, dictionary drafts, and drift reports. Search engines execute retrieval. Integrations should make those artifacts useful in existing search, RAG, and agent stacks without turning SkeinRank into the owner of engine mappings, analyzers, templates, cluster settings, or production query logic.

## Default integration patterns

Prefer these patterns for new search engines and RAG stacks.

### Query-time lexical adapter

Canonicalize the user query before it reaches a lexical search backend.

```text
raw query -> skeinrank canonicalization -> Elasticsearch/OpenSearch/Solr/Postgres FTS/Vespa query
```

This pattern is appropriate for Elasticsearch, OpenSearch, Solr, Lucene, PostgreSQL full-text search, Vespa, Typesense, and similar engines. The engine remains the retrieval backend; SkeinRank only prepares governed text and explain metadata.

### Vector pre-embedding adapter

Canonicalize text before embedding during indexing or query-time retrieval.

```text
raw text/query -> skeinrank canonicalization -> embedder -> vector store
```

This pattern is appropriate for Qdrant, Weaviate, Milvus, pgvector, and other vector retrieval systems. SkeinRank should not own the vector collection schema. It should provide a deterministic text preparation step and optional explain metadata.

### Export artifacts

Generating artifacts is allowed when the operator or downstream deployment system applies them.

Examples:

- dictionary JSON or YAML;
- runtime snapshot artifacts;
- synonym-list exports;
- reviewable dictionary drafts;
- drift reports;
- operator runbook request payloads.

Artifact export follows the same safety model as dictionary import and drift export: SkeinRank produces a reviewable artifact; the operator decides how and when to apply it.

### Examples before engine-specific modules

Do not create one package per search engine by default. Most engines need a short example using the same core canonicalization or export API. New code is justified only when a reusable adapter can stay thin and dependency-light.

## Operator-controlled delivery

Direct writes to a search backend are exceptional. They are allowed only for an explicit operator-controlled delivery workflow with narrow scope and clear safety gates.

The Elasticsearch/OpenSearch delivery path is the current advanced delivery workflow. It publishes terminology-derived enrichment fields into an existing search index. It does not make Elasticsearch/OpenSearch the source of truth for terminology. SkeinRank remains the source of truth for governed terminology artifacts.

An operator-controlled delivery workflow must keep these properties:

- the core SDK has no backend client dependency;
- backend-specific code lives outside `skeinrank-core`;
- the UI remains an inspection and review surface, not the operational apply surface;
- an admin or operator explicitly starts the delivery operation;
- the binding is enabled for write delivery;
- preflight is ready and returns the exact plan;
- the job start request confirms that exact plan with a per-run confirmation token;
- blue/green or rollback-oriented strategies are preferred for production-like runs;
- direct in-place writes are documented as not reversible by alias rollback;
- workers write only derived fields or derived indexes, not engine-owned taxonomy state.

## Boundaries for future engines

New search integrations should follow this order:

1. query-time adapter;
2. vector pre-embedding adapter;
3. export artifact writer;
4. operator-controlled delivery workflow only when a concrete deployment need justifies direct backend writes.

Avoid these scopes unless they are explicitly accepted through an architecture discussion:

- owning search-engine mappings, analyzers, templates, or cluster settings;
- treating engine synonym configuration as the source of truth;
- writing production search configuration from UI actions;
- allowing agents to mutate search backends directly;
- adding heavyweight backend clients to `skeinrank-core`;
- turning SkeinRank into a generic search-engine management platform.

## Contribution checklist

Before adding a search integration, answer these questions in the issue or discussion:

1. Is this a query-time adapter, vector pre-embedding adapter, export artifact, or operator-controlled delivery workflow?
2. What owns the source of truth for terminology?
3. Does the change add any dependency to `skeinrank-core`?
4. Can any write happen without an explicit operator decision?
5. If a backend write exists, what preflight, confirmation, and rollback boundary protects it?
6. Can the same value be shown with a docs example instead of new package code?

This policy keeps SkeinRank focused: govern the language layer, expose auditable runtime context, and integrate with search engines without becoming the search engine.
