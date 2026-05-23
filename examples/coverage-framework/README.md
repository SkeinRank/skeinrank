# Coverage framework examples

This directory contains small Phase C examples for tags, ambiguous aliases, binding policies, and before/after evaluation.

Files:

- `coverage_dictionary.example.json` — dictionary spec v1 with tags and one intentionally ambiguous surface form.
- `ambiguous_alias_pg.example.json` — ambiguous alias candidates for `pg`.
- `binding_policy_infra.example.json` — policy resolving `pg` as `postgresql` for infra/runtime contexts.
- `binding_policy_docs.example.json` — policy resolving `pg` as `page` for documentation contexts.
- `evaluation_queries.jsonl` — query set for snapshot before/after evaluation.

Suggested flow:

```bash
curl -s -X POST "http://127.0.0.1:8010/v1/headless/dictionaries/apply" \
  -H "Content-Type: application/json" \
  -H "X-SkeinRank-Role: admin" \
  --data-binary @examples/coverage-framework/coverage_dictionary.example.json | python -m json.tool

curl -s -X POST "http://127.0.0.1:8010/v1/governance/profiles/coverage_ops/ambiguous-aliases" \
  -H "Content-Type: application/json" \
  -H "X-SkeinRank-Role: admin" \
  --data-binary @examples/coverage-framework/ambiguous_alias_pg.example.json | python -m json.tool
```

Create bindings through the governance API or UI, then attach one of the policy examples to the binding that should own that runtime interpretation.
