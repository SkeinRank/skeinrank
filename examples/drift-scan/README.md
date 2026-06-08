# Terminology drift scan example

This example compares an existing SkeinRank dictionary with local incident notes and writes a reviewable terminology drift report.

The scan is deterministic and local. It does not call an LLM, create proposals, publish snapshots, update bindings, or mutate runtime state.

```bash
cd packages/skeinrank-core

poetry run skeinrank drift scan \
  --dictionary ../../examples/drift-scan/company.dictionary.json \
  --docs ../../examples/drift-scan/docs \
  --out ../../examples/drift-scan/drift-report.json \
  --markdown ../../examples/drift-scan/drift-report.md
```

Useful fields in the JSON report:

- `metrics.unknown_alias_rate`
- `metrics.unknown_candidate_count`
- `metrics.stale_term_count`
- `findings[].finding_type`
- `findings[].evidence`

The current scan emits `alias_drift` findings for significant unmatched local terminology and `stale_term` findings for dictionary terms that have little or no evidence in the scanned corpus. Later workflows can turn reviewed findings into proposals, but this command only produces a report.
