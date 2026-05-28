# Profile isolation checks

Patch 55D adds a read-only isolation report for the current production safety model.

SkeinRank does not claim full tenant isolation yet. The current safe boundary is the terminology profile plus optional runtime binding. The report verifies that binding-scoped rows do not cross profile boundaries and that existing request guards reject mismatched `profile_name` / `binding_id` pairs.

## Endpoint

```http
GET /v1/governance/isolation-checks
```

Response schema:

```text
skeinrank.profile_isolation.v1
```

The endpoint is read-only. It does not call OpenRouter, Elasticsearch, workers, or runtime mutation APIs.

## What is checked

The report verifies alignment for:

- Elasticsearch bindings and their profiles;
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

A request with a `binding_id` from one profile and a different `profile_name` must be rejected before runtime work starts:

```json
{
  "profile_name": "infra",
  "binding_id": 42,
  "query": "k8s rollout"
}
```

The same rule applies to agent tools and proposal creation.

## Safety notes

- No migrations are introduced.
- No tenant column is added.
- No runtime writes are performed.
- No provider calls are made.
- Existing profile and binding guards remain the source of truth.

This patch is a production safety check for the current profile/binding model. Full multi-tenant isolation can be added later as a separate feature.
