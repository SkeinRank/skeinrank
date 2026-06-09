# Runtime routing API examples

These examples show how an application backend can call SkeinRank with an explicit binding context.

The files are request payloads only. They do not contain secrets and do not introduce new endpoints.

## Endpoints demonstrated

```text
POST /v1/text/canonicalize
POST /v1/query/plan
POST /v1/query/route-plan
POST /v1/search
```

Use `binding_id` when your application stores the binding id. Use `binding_name` when your application stores a stable runtime context name.

## Binding-aware canonicalization

`context-trigger-dictionary.yaml` demonstrates a dictionary spec v1 alias with `context_triggers`.

`context-trigger-canonicalize.request.json` demonstrates binding-aware canonicalization where `pg` expands only because the request includes incident/database trigger words.

Aliases without `context_triggers` keep the existing always-active behavior.

## Multi-binding route planning

`route-plan.request.json` demonstrates the read-only route planner:

```text
POST /v1/query/route-plan
```

Use it when an application has a global search box and already knows a bounded set of candidate bindings. The endpoint ranks candidates and returns:

- `selected_bindings`
- `rejected_bindings`
- `failed_bindings`
- `mode = "route_plan_only"`

The route planner does not execute Elasticsearch search. It returns a routing decision that the application can inspect before choosing where to send the query.
