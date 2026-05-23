# Coverage framework guide

This guide shows the Phase C coverage workflow using the current governance API surfaces. It is intentionally headless-friendly and keeps active runtime terminology protected behind review, policy, and snapshots.

## 1. Apply a tagged dictionary

Start with a dictionary that uses one primary slot per canonical term and optional tags for facets.

```bash
curl -s -X POST "http://127.0.0.1:8010/v1/headless/dictionaries/apply" \
  -H "Content-Type: application/json" \
  -H "X-SkeinRank-Role: admin" \
  --data-binary @examples/coverage-framework/coverage_dictionary.example.json | python -m json.tool
```

Tags are normalized and exported with the dictionary and runtime snapshot artifacts.

## 2. Inspect conflicts

Run the read-only conflict report before adding policy rules:

```bash
curl -s "http://127.0.0.1:8010/v1/governance/conflicts?profile_name=coverage_ops" \
  -H "X-SkeinRank-Role: admin" | python -m json.tool
```

A conflict report does not change terms, aliases, proposals, ambiguous aliases, or snapshots.

## 3. Record ambiguous candidates

When one surface can have multiple interpretations, record it explicitly:

```bash
curl -s -X POST "http://127.0.0.1:8010/v1/governance/profiles/coverage_ops/ambiguous-aliases" \
  -H "Content-Type: application/json" \
  -H "X-SkeinRank-Role: admin" \
  --data-binary @examples/coverage-framework/ambiguous_alias_pg.example.json | python -m json.tool
```

This records review metadata only. It does not make `pg` expand to every candidate at runtime.

## 4. Attach binding policy

Create or reuse an Elasticsearch binding for the profile, then attach a binding policy:

```bash
curl -s -X PUT "http://127.0.0.1:8010/v1/governance/elasticsearch/bindings/1/policy" \
  -H "Content-Type: application/json" \
  -H "X-SkeinRank-Role: admin" \
  --data-binary @examples/coverage-framework/binding_policy_infra.example.json | python -m json.tool
```

A policy is binding-scoped. Another binding can use a different policy for the same alias surface.

## 5. Explain runtime behavior

Runtime calls with `binding_id` can include policy decisions:

```bash
curl -s -X POST "http://127.0.0.1:8010/v1/query/plan" \
  -H "Content-Type: application/json" \
  -H "X-SkeinRank-Role: admin" \
  -d '{"binding_id": 1, "query": "pg timeout after k8s rollout"}' | python -m json.tool
```

Look for `policy_decisions` to see why a surface resolved to a selected canonical value.

## 6. Evaluate before/after snapshots

Export before and after artifacts, then run offline evaluation:

```bash
skeinrank-migrate snapshot-eval \
  --before snapshots/coverage_ops.before.json \
  --after snapshots/coverage_ops.after.json \
  --queries examples/coverage-framework/evaluation_queries.jsonl \
  --output coverage-evaluation.json
```

Use the report as a release gate: inspect changed aliases, tag drift, query-plan changes, and risk notes before promoting a new runtime artifact.

## What belongs in UI vs headless flow

Use headless APIs, CLI, CI/CD, or MCP tools for submissions and automation. Use UI only where visual review helps:

- Search Playground for query explanation;
- proposal inbox for human-in-the-loop decisions;
- conflict review;
- ambiguous alias candidate review;
- snapshot diff/evaluation review.
