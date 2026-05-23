# Coverage framework

The coverage framework is the SkeinRank layer that keeps terminology expansion useful without letting it drift into noisy runtime behavior.

It is built on one rule:

```text
more aliases are not automatically better coverage
```

Naively expanding every surface form into every possible meaning can increase recall while hurting precision. SkeinRank keeps the model explicit by separating primary extraction roles, facets, ambiguous interpretations, binding-specific policy, and immutable runtime artifacts.

## Mental model

| Concept | What it means | What it does not mean |
| --- | --- | --- |
| `slot` | Primary extraction/search role for a canonical term. | A general-purpose category list. |
| `tag` | Additional normalized facet such as `infra`, `backend`, or `storage`. | A replacement for the primary slot. |
| `candidate` | Possible interpretation of one ambiguous surface form. | A tag or an automatic runtime synonym. |
| `BindingPolicy` | Runtime-context rule attached to one binding. | A global dictionary rewrite. |
| `snapshot` | Immutable runtime read model. | Live draft governance state. |
| evaluation | Before/after artifact diff and query-plan check. | A guarantee that every expansion improves search quality. |

## Why this exists

Enterprise terminology often looks like this:

```text
pg -> postgresql        in infra incidents
pg -> page              in documentation tooling
pg -> product_group     in analytics or org reporting
```

SkeinRank should not flatten that into:

```text
pg -> postgresql OR page OR product_group
```

Instead, it records the ambiguity, reviews candidate meanings, and lets binding-specific policy decide what is safe in a concrete runtime context.

## Lifecycle

```text
discover -> validate -> review -> snapshot -> bind -> serve -> evaluate
```

1. A human, CLI, job, or agent submits a proposal.
2. The proposal checker registry adds structured validation results.
3. Conflicts surface in reports and ambiguous-alias candidates.
4. Reviewers resolve or annotate risky surfaces.
5. A binding policy can define allowed runtime choices for one binding.
6. A snapshot artifact captures the runtime read model.
7. Before/after evaluation checks whether the new artifact changes query behavior.

## Slots vs tags

Use one primary slot for the term's role in extraction/search schema:

```json
{
  "canonical_value": "postgresql",
  "slot": "DATABASE",
  "tags": ["infra", "backend", "storage"]
}
```

Use tags for facets that help policies, review, filtering, and evaluation. A term can have many tags, but it should still have one primary slot.

## Ambiguous aliases

An ambiguous alias stores one surface form and multiple possible interpretations.

```json
{
  "surface_value": "pg",
  "candidates": [
    {"canonical_value": "postgresql", "slot": "DATABASE", "status": "preferred"},
    {"canonical_value": "page", "slot": "DOCUMENT_COMPONENT", "status": "candidate"}
  ]
}
```

Ambiguous aliases are governance records. Creating one does not mutate active aliases and does not publish a runtime snapshot.

## Binding policies

A binding policy is attached to one runtime binding. It can restrict which candidate is safe in that binding context.

```json
{
  "preferred_slots": ["DATABASE", "SERVICE", "TECHNOLOGY"],
  "allowed_tags": ["infra", "backend", "storage"],
  "deny_slots": ["DOCUMENT_COMPONENT"],
  "context_rules": [
    {
      "surface": "pg",
      "prefer": "postgresql",
      "slot": "DATABASE",
      "reason": "Infra incidents use pg as PostgreSQL."
    }
  ]
}
```

The policy does not rewrite the dictionary. Runtime endpoints can use it to select safe candidates and emit `policy_decisions` for audit/debug.

## Evaluation before publishing

Use snapshot evaluation when a proposed dictionary/policy release could change runtime behavior.

```bash
skeinrank-migrate snapshot-eval \
  --before snapshots/infra.before.json \
  --after snapshots/infra.after.json \
  --queries examples/coverage-framework/evaluation_queries.jsonl \
  --output coverage-evaluation.json
```

Review the report before promoting a new artifact.

## Anti-patterns

Avoid these patterns:

- using multiple slots to represent facets;
- treating tags as runtime disambiguation by themselves;
- allowing agents to mutate active aliases directly;
- resolving an ambiguous alias globally when the meaning is binding-specific;
- publishing a snapshot without checking conflict reports or before/after evaluation;
- hiding policy decisions from runtime debug output.

## Safe default

When SkeinRank cannot safely resolve an ambiguous surface for a binding, the safer behavior is to keep the original surface form and return policy/debug information for review.
