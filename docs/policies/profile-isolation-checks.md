# Profile isolation checks

SkeinRank uses profiles and runtime bindings as the current production safety boundary. A profile owns terminology. A binding applies a profile to a specific search context such as an index, text fields, target field, filters, and pinned snapshot.

The isolation report verifies that binding-scoped data remains aligned with the profile it belongs to and that request guards reject mismatched `profile_name` / `binding_id` pairs before runtime work starts.

SkeinRank does not claim full tenant isolation in this model. The report is a production health check for the current profile/binding boundary.

## Endpoint

```http
GET /v1/governance/isolation-checks
```

Response schema:

```text
skeinrank.profile_isolation.v1
```

The endpoint is read-only. It does not call OpenRouter, Elasticsearch/OpenSearch, workers, model providers, or runtime mutation APIs.

## What is checked

The report verifies alignment for:

- Elasticsearch/OpenSearch bindings and their profiles;
- proposal suggestions with `binding_id`;
- binding policies;
- enrichment jobs;
- agent runs;
- agent document visits;
- agent candidate observations;
- agent evidence windows;
- agent LLM reviews;
- agent proposal attempts;
- runtime request guards that reject profile/binding mismatches.

## Expected clean state

A clean state returns:

```json
{
  "schema_version": "skeinrank.profile_isolation.v1",
  "status": "ok",
  "summary": {
    "failed_checks": 0,
    "issues_total": 0
  }
}
```

If mismatched rows are detected, `status` becomes `degraded` and each failed check includes sampled issues. This is meant for operators and support bundles, not for automated repair.

## Guarded request examples

A request with a `binding_id` from one profile and a different `profile_name` must be rejected:

```json
{
  "profile_name": "infra",
  "binding_id": 42,
  "query": "k8s rollout"
}
```

The same rule applies to agent tools and proposal creation. Runtime APIs should use the binding as the production context and should not infer profile ownership from free-form query text.

## Operator guidance

Use this report when:

- preparing a support bundle;
- validating a production-like environment after imports or migrations;
- checking a failed runtime request that references both a profile and a binding;
- reviewing unexpected agent proposals that were tied to a binding.

A degraded report should be investigated before publishing a new runtime snapshot for affected profiles or bindings.

## Safety guarantees

- No migrations are introduced by the report.
- No tenant columns are created.
- No runtime writes are performed.
- No provider calls are made.
- Existing profile and binding guards remain the source of truth.

## Related docs

- [`role-boundaries.md`](role-boundaries.md)
- [`../api/governance-api.md`](../api/governance-api.md)
- [`../security/rag-context-boundaries.md`](../security/rag-context-boundaries.md)
