# Runtime routing API examples

These examples show how an application backend can call SkeinRank with an
explicit binding context.

The examples are request payloads only. They do not contain secrets and do not
introduce new endpoints.

Current endpoints used:

```text
POST /v1/text/canonicalize
POST /v1/query/plan
POST /v1/search
```

Use `binding_id` when your application stores the binding id. Use `binding_name`
when your application stores a stable runtime context name.

Patch 63B adds trigger-gated alias examples:

- `context-trigger-dictionary.yaml` — dictionary spec v1 alias with `context_triggers`.
- `context-trigger-canonicalize.request.json` — binding-aware canonicalization request where `pg` expands only because the query also contains incident/database trigger words.

Aliases without `context_triggers` keep the existing always-active behavior.
