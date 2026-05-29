# Binding-aware runtime canonicalization API

Patch 63A makes the runtime API explicitly binding-aware. The goal is to let an
application route a query to the correct SkeinRank runtime context without asking
SkeinRank to guess the user's intent from text alone.

## Runtime rule

Use `binding_id` or `binding_name` for production paths. Use `profile_name` only
for preview/dev flows.

```text
Profile  = terminology space
Binding  = runtime search context: profile + index/alias + fields + filters + snapshot
Snapshot = immutable terminology version used by the binding
```

A product backend usually already knows the application scope from the current
screen, workspace, collection, or route. It should pass that scope to SkeinRank
and resolve the matching binding before canonicalization/search.

## Canonicalize with a binding id

```http
POST /v1/text/canonicalize
```

```json
{
  "binding_id": 7,
  "text": "k8s pg timeout",
  "mode": "replace",
  "application_scope": {
    "workspace": "infra",
    "selected_scope": "incidents",
    "route": "/incidents/search"
  }
}
```

The response includes both the legacy top-level fields and the resolved runtime
context:

```json
{
  "profile_name": "infra_incidents",
  "binding_id": 7,
  "binding_name": "infra incidents prod",
  "snapshot_source": "binding_runtime_snapshot",
  "runtime_context": {
    "mode": "binding_runtime",
    "profile_name": "infra_incidents",
    "binding_id": 7,
    "binding_name": "infra incidents prod",
    "index_name": "incidents-prod",
    "text_fields": ["title", "body"],
    "target_field": "skeinrank",
    "snapshot_source": "binding_runtime_snapshot",
    "application_scope": {
      "workspace": "infra",
      "selected_scope": "incidents",
      "route": "/incidents/search"
    }
  },
  "canonical_text": "kubernetes postgresql timeout"
}
```

## Canonicalize with a stable binding name

`binding_name` is useful when an application has a stable search-context name but
should not hard-code database ids in config files.

```json
{
  "binding_name": "infra incidents prod",
  "text": "pg timeout",
  "mode": "replace"
}
```

If both `binding_id` and `binding_name` are provided, they must refer to the same
binding. A mismatch returns `409` before canonicalization starts.

## Query plan with runtime context

```http
POST /v1/query/plan
```

```json
{
  "binding_name": "infra incidents prod",
  "query": "k8s pg timeout",
  "size": 10,
  "application_scope": {
    "workspace": "infra",
    "selected_scope": "incidents"
  }
}
```

The query plan response includes `runtime_context` so developers can debug which
binding, fields, target field, filter discriminator, and snapshot produced the
Elasticsearch DSL.

## Search with runtime context

```http
POST /v1/search
```

```json
{
  "binding_id": 7,
  "query": "pg timeout",
  "size": 10
}
```

When a binding is provided, SkeinRank derives `index_name`, `text_fields`, and
`target_field` from the binding unless the caller overrides them for debugging.

## Preview mode remains available

Preview/dev calls can still use a profile directly:

```json
{
  "profile_name": "infra_incidents",
  "text": "pg timeout",
  "mode": "replace"
}
```

This returns `runtime_context.mode = "profile_preview"` and uses the latest
profile state instead of a binding-pinned snapshot. A binding without a pinned
runtime snapshot returns `runtime_context.mode = "binding_latest_profile"` plus
a warning. Do not rely on either preview shape for production search paths.

## What this patch does not do

Patch 63A made the binding-aware contract explicit. Patch 63B adds deterministic
`context_triggers` for aliases so noisy surfaces can be gated by nearby query
terms without introducing an LLM router. Multi-binding route planning remains a
later runtime-routing patch.

See also: [`context-trigger-disambiguation.md`](context-trigger-disambiguation.md).

