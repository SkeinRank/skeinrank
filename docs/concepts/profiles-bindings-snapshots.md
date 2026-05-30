# Profiles, bindings, and snapshots

SkeinRank separates terminology meaning from runtime search context.

```text
Profile  = what the terminology means
Binding  = where and how that terminology is applied
Snapshot = which immutable version is safe for runtime
```

## Profile

A profile is a terminology space.

Examples:

```text
infra_incidents
product_docs
support_tickets
security_terms
legal_terms
```

A profile owns canonical terms, aliases, slots, profile-local guardrails, suggestions, and exported snapshots.

## Binding

A binding applies a profile to a concrete search context.

A binding can include:

- profile name;
- Elasticsearch index or alias;
- source text fields;
- target enrichment field;
- document discriminator field/value;
- timestamp field and time window;
- write strategy;
- pinned runtime snapshot.

A simple case looks like this:

```text
profile = infra_incidents
index   = incidents-2026
fields  = title, body, summary
snapshot = infra_incidents / S42
```

A shared-index case needs a discriminator:

```text
binding 1:
  profile = infra_incidents
  index = company_docs
  filter = team:infra

binding 2:
  profile = product_terms
  index = company_docs
  filter = team:product
```

This is why production runtime should use `binding_id`, not just `profile_name`.

For the headless-first contract, the binding is also the safest boundary between proposal-time changes and runtime behavior. Agents, CI jobs, and CLI tools can suggest or apply changes through governance surfaces, but production readers should use a binding plus an immutable snapshot. See [`headless-runtime-contracts.md`](headless-runtime-contracts.md) for the contract map.

## Snapshot

A snapshot is an immutable runtime export of a profile.

Different bindings can safely run different snapshot versions at the same time:

```text
binding 1 -> profile infra_incidents -> snapshot S42
binding 2 -> profile infra_incidents -> snapshot S41
binding 3 -> profile product_terms   -> snapshot S12
```

This lets teams roll out terminology changes gradually and inspect which version produced a query plan, enrichment job, or search result context.

## Runtime rule

For production search paths, prefer:

```json
{
  "binding_id": 7,
  "query": "k8s pg timeout",
  "size": 10
}
```

A development or preview flow can still use `profile_name`, but a real runtime search path needs binding information because the binding knows the index, fields, filters, and pinned snapshot.

Patch 63A allows production callers to use either numeric `binding_id` or stable
`binding_name`. Runtime responses include `runtime_context`, which records the
resolved binding, snapshot source, Elasticsearch fields, optional discriminator
filter, and any caller-provided `application_scope` metadata.

## Multi-binding search

For an `All docs` search experience, the backend can fan out across multiple bindings:

```text
query -> binding 1 canonicalization -> search index A
query -> binding 2 canonicalization -> search index B
query -> binding 3 canonicalization -> search index C
```

The results can then be merged. This is safer than assuming one global dictionary, because the same alias can have different meaning across domains.

## Patch 63C — route before fan-out

For `All docs` search, applications can ask SkeinRank for a read-only
multi-binding route plan via `POST /v1/query/route-plan`. The request supplies
candidate bindings, and the response ranks them using alias matches,
context-trigger matches, application-scope hints, and snapshot context. The
application still owns the final decision to call `/v1/search` or
`/v1/search/multi`.
