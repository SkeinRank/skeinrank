# Context-trigger disambiguation for aliases

`context_triggers` are a lightweight runtime guard for noisy aliases.
They support intent-aware canonicalization without adding an LLM router
or new runtime endpoints.

## Problem

Short aliases such as `pg`, `prod`, `core`, or `phoenix` can be useful in one
application scope and noisy in another. A binding-aware request already tells
SkeinRank where the query is running, but the text itself can still be ambiguous.

`context_triggers` let an alias match only when the surrounding query contains at
least one configured trigger word or phrase.

## Dictionary shape

Dictionary spec v1 still accepts simple string aliases. Object aliases can now
carry optional triggers:

```yaml
schema_version: skeinrank.dictionary.v1
profile_name: infra_incidents
terms:
  - canonical_value: postgresql
    slot: DATABASE
    aliases:
      - value: pg
        confidence: 0.95
        context_triggers:
          - timeout
          - replica
          - migration
```

JSON works the same way:

```json
{
  "value": "pg",
  "confidence": 0.95,
  "context_triggers": ["timeout", "replica", "migration"]
}
```

Aliases without `context_triggers` keep the existing behavior and match whenever
the alias surface appears in the text.

## Runtime behavior

```http
POST /v1/text/canonicalize
```

```json
{
  "binding_name": "infra incidents prod",
  "text": "pg timeout on replica",
  "mode": "replace"
}
```

If the `pg` alias has triggers `timeout`, `replica`, and `migration`, the result
includes the trigger explanation:

```json
{
  "canonical_text": "postgresql timeout on replica",
  "replacements": [
    {
      "alias_value": "pg",
      "canonical_value": "postgresql",
      "source": "alias_context_trigger",
      "context_triggers": ["migration", "replica", "timeout"],
      "matched_context_triggers": ["replica", "timeout"]
    }
  ]
}
```

The same alias will not match a query such as `pg layout issue` unless one of the
configured triggers is also present.

## Where this applies

The same trigger-gated matcher is used by:

```text
POST /v1/text/canonicalize
POST /v1/query/plan
POST /v1/search
POST /v1/search/multi
```

No new endpoint is introduced. The feature extends the existing alias model,
dictionary import/export shape, runtime snapshots, and explanation payloads.

## Safety posture

`context_triggers` are intentionally deterministic. They are not a classifier and
not an agent decision. They are a safe middle layer between:

```text
application-scope routing via binding_id / binding_name
and future multi-binding route planning
```

Use them for aliases that are too short or overloaded to expand globally, but are
safe when paired with domain-specific context words.
