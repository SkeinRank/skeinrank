# Terminology drift scan example

This example compares an existing SkeinRank dictionary with local incident notes and writes a reviewable terminology drift report.

The scan is deterministic and local. It does not call an LLM, create proposals, publish snapshots, update bindings, or mutate runtime state.

```bash
cd packages/skeinrank-core

poetry run skeinrank drift scan \
  --dictionary ../../examples/drift-scan/company.dictionary.json \
  --docs ../../examples/drift-scan/docs \
  --binding-metadata ../../examples/drift-scan/binding-metadata.json \
  --out ../../examples/drift-scan/drift-report.json \
  --markdown ../../examples/drift-scan/drift-report.md
```

Useful fields in the JSON report:

- `metrics.unknown_alias_rate`
- `metrics.unknown_candidate_count`
- `metrics.stale_term_count`
- `metrics.binding_lag_count`
- `metrics.binding_snapshot_lag`
- `metrics.ambiguity_signal_count`
- `findings[].finding_type`
- `findings[].evidence`

The current scan emits `alias_drift` findings for significant unmatched local terminology, `stale_term` findings for dictionary terms that have little or no evidence in the scanned corpus, optional `binding_lag` findings when local binding metadata says the pinned snapshot is behind the latest approved snapshot, and conservative `ambiguity_signal` findings when an existing short alias appears near unfamiliar context terms. Later workflows can turn reviewed findings into proposals, but this command only produces a report.
