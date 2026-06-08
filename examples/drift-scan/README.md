# Terminology drift scan example

This example compares an existing SkeinRank dictionary with local incident notes and writes a reviewable terminology drift report.

The scan is deterministic and local. It does not call an LLM, create governance proposals, publish snapshots, update bindings, or mutate runtime state.

## Run the scan

```bash
cd packages/skeinrank-core

poetry run skeinrank drift scan \
  --dictionary ../../examples/drift-scan/company.dictionary.json \
  --docs ../../examples/drift-scan/docs \
  --binding-metadata ../../examples/drift-scan/binding-metadata.json \
  --out ../../examples/drift-scan/drift-report.json \
  --markdown ../../examples/drift-scan/drift-report.md
```

The example corpus is shaped to produce four review signals:

| Finding type | What the example demonstrates |
| --- | --- |
| `alias_drift` | New unmatched local terms such as incident/runtime shorthand. |
| `stale_term` | A deprecated dictionary term that no longer appears in the scanned corpus. |
| `binding_lag` | A local metadata file where the pinned snapshot is behind the latest approved snapshot. |
| `ambiguity_signal` | Existing short alias `pg` appearing near unfamiliar layout/dashboard context. |

Useful fields in the JSON report:

- `metrics.unknown_alias_rate`
- `metrics.unknown_candidate_count`
- `metrics.stale_term_count`
- `metrics.binding_lag_count`
- `metrics.binding_snapshot_lag`
- `metrics.ambiguity_signal_count`
- `findings[].finding_type`
- `findings[].evidence`

## Python example

Run the offline Python example from the repository root or from `packages/skeinrank-core`:

```bash
python ../../examples/drift-scan/run_drift_scan.py
```

The script loads `company.dictionary.json`, scans the `docs/` directory, applies `binding-metadata.json`, and prints the markdown report. It does not write production state.

## Convert reviewed findings into a dictionary draft

After reviewing the report, export alias-drift findings into a local dictionary draft:

```bash
poetry run skeinrank drift export-draft ../../examples/drift-scan/drift-report.json \
  --out ../../examples/drift-scan/drift.dictionary-draft.json \
  --review ../../examples/drift-scan/drift.dictionary-draft.md
```

Or run the offline Python example:

```bash
python ../../examples/drift-scan/export_drift_draft.py
```

The export is still review-only. It creates a `DictionaryDraft` artifact with proposed candidates and copies the drift findings into the review table. It does not create governance proposals directly, publish snapshots, update bindings, or mutate runtime state.

## More detail

Read [`docs/guides/terminology-drift-report.md`](../../docs/guides/terminology-drift-report.md) for the schema, CLI options, Python API, and safety boundary.
