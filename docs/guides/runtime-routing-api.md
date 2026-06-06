# Binding-aware runtime canonicalization API

The runtime API is explicitly binding-aware. The goal is to let an
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

## Runtime boundaries

Binding-aware canonicalization does not introduce an LLM router and does not try to infer every search context from text alone. Use deterministic `context_triggers` for noisy aliases that should match only with nearby domain terms, and use route planning for global-search and fan-out scenarios.

See also: [`context-trigger-disambiguation.md`](context-trigger-disambiguation.md).

## Multi-binding route plan API

The route-plan endpoint is read-only. It is for callers that already know a set of
candidate runtime contexts but need SkeinRank to rank which binding should handle
a query.

```text
POST /v1/query/route-plan
```

This endpoint is intentionally not a search router. The route planner does not execute Elasticsearch search, does not call `/v1/search/multi`, and does not mutate
profiles, aliases, bindings, snapshots, or proposals. It builds the same
binding-aware query plan that `/v1/query/plan` would build for each candidate
binding, scores the binding contexts, and returns selected/rejected/failed
planning results.

Request shape:

```json
{
  "candidate_binding_ids": [1, 2, 3],
  "query": "k8s pg timeout",
  "application_scope": {
    "workspace": "infra",
    "selected_scope": "all"
  },
  "max_selected_bindings": 2,
  "min_score": 0.01,
  "include_rejected": true,
  "include_evidence": true
}
```

Response shape:

```json
{
  "query": "k8s pg timeout",
  "mode": "route_plan_only",
  "candidate_binding_ids": [1, 2, 3],
  "selected_binding_ids": [1],
  "total_bindings": 3,
  "selected_count": 1,
  "rejected_count": 1,
  "failed_count": 1,
  "selected_bindings": [
    {
      "binding_id": 1,
      "binding_name": "infra incidents prod",
      "profile_name": "infra_incidents",
      "index_name": "incidents-prod",
      "score": 0.75,
      "score_reasons": ["matched_aliases:2", "application_scope:workspace"],
      "reason": "matched_aliases:2",
      "canonical_query": "kubernetes postgresql timeout",
      "canonical_values": ["kubernetes", "postgresql"],
      "matched_aliases": ["k8s", "pg"],
      "runtime_context": {
        "mode": "binding_latest_profile",
        "binding_id": 1,
        "profile_name": "infra_incidents"
      }
    }
  ],
  "rejected_bindings": [],
  "failed_bindings": [
    {
      "binding_id": 3,
      "error": "Elasticsearch binding not found: 3"
    }
  ],
  "warnings": []
}
```

Scoring is deterministic and explainable. It favors candidate bindings with
matched aliases, matched canonical values, matched `context_triggers`, matching
`application_scope` metadata, and binding-pinned runtime snapshots. The score is
only a route-planning hint; application backends should still decide whether to
run `/v1/search` for one selected binding or `/v1/search/multi` for several
selected bindings.

Use this endpoint when the application has a global search box such as `All docs`
and wants a safe plan before fan-out. For simple production surfaces, prefer
passing a single `binding_id` directly to `/v1/text/canonicalize`,
`/v1/query/plan`, or `/v1/search`.
