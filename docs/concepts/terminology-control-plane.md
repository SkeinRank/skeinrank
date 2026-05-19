# Terminology control plane

SkeinRank treats terminology as governed runtime infrastructure, not as a static helper list buried inside application code.

A terminology control plane lets teams:

- normalize noisy aliases into canonical values;
- review and approve terminology changes;
- keep domain dictionaries separated by profile;
- bind dictionaries to concrete search contexts;
- publish immutable snapshots for runtime safety;
- check evidence from indexed documents before approving changes;
- serve context to search, RAG, and agent workflows.

## The problem

Enterprise search often depends on raw text. That raw text contains aliases, abbreviations, typos, internal nicknames, and competing terminology.

Example:

```text
k8s rollout failed after pg timeout in sev1 runbook
```

A plain lexical search sees surface forms. SkeinRank can map them to canonical values:

```text
k8s      -> kubernetes
pg       -> postgresql
sev1     -> severity_1
runbook  -> runbook
```

This produces structured runtime context that downstream systems can use for search filters, retrieval features, reranking, highlighting, or audit/debug views.

## Canonical terms and aliases

A canonical term is the normalized value SkeinRank wants runtime systems to use.

Aliases are accepted surface forms that point to the canonical value.

```json
{
  "canonical_value": "kubernetes",
  "slot": "TOOL",
  "aliases": ["k8s", "kube", "kuber"]
}
```

The lightweight core supports dictionary-first extraction and alias canonicalization. The governance platform adds lifecycle, suggestions, roles, evidence checks, snapshots, and runtime bindings.

## Guardrails

Guardrails prevent noisy or unsafe terms from becoming runtime signals.

SkeinRank supports both:

- global stop-list entries inherited by every profile;
- profile-scoped stop-list entries for domain-specific cleanup.

This keeps broad words such as `api`, `service`, or ambiguous internal tokens from polluting extraction unless a team deliberately models them.

## Evidence-assisted review

Reviewer workflows should not approve aliases blindly. SkeinRank can query a configured Elasticsearch binding and return bounded snippets showing whether a value appears in indexed content.

Evidence checks are intentionally bounded:

- small document limits;
- selected fields only;
- no writes;
- short request timeouts;
- highlighted snippets for reviewer context.

Pending suggestions can store evidence snapshots so reviewers can see what justified a change even if the underlying index changes later.

## Snapshots

Runtime systems should not depend on live, mutable terminology edits. SkeinRank uses snapshots as the immutable version of terminology that a runtime binding serves.

A snapshot answers:

```text
Which exact terminology version was used for this query, enrichment job, or document context?
```

This makes runtime behavior more reproducible and easier to debug.
