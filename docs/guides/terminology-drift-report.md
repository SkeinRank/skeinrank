# Terminology drift report

SkeinRank can compare a governed dictionary with a local document corpus and produce a reviewable terminology drift report. The report answers a narrow operational question:

> Which parts of this dictionary no longer match the language people are using in these documents?

This is a local, deterministic workflow. It does not call model providers, create governance proposals, publish snapshots, update bindings, or mutate runtime search configuration.

## When to use it

Use a terminology drift report when you want to check a dictionary against fresh docs, incident notes, runbooks, support exports, or search-content samples before a reviewer decides whether the dictionary needs new aliases, stale-term cleanup, or binding rollout work.

Typical signals:

| Signal | Meaning | Action |
| --- | --- | --- |
| `alias_drift` | Significant unmatched terminology appears in the corpus. | Review candidate terms and decide whether to add aliases or canonicals. |
| `stale_term` | A dictionary term has little or no evidence in the scanned corpus. | Review whether the term is deprecated, out of scope, or still needed elsewhere. |
| `binding_lag` | Local binding metadata says the pinned snapshot is behind the latest approved snapshot. | Review whether the binding should roll forward. |
| `ambiguity_signal` | A short existing alias appears near unfamiliar context terms. | Review context rules or split meanings; do not auto-change the alias. |

The scan is not a real-time monitor and is not search observability. It does not require query logs, click data, relevance labels, or production access.

## Run a local scan

From the repository checkout:

```bash
cd packages/skeinrank-core

poetry run skeinrank drift scan \
  --dictionary ../../examples/drift-scan/company.dictionary.json \
  --docs ../../examples/drift-scan/docs \
  --binding-metadata ../../examples/drift-scan/binding-metadata.json \
  --out ../../examples/drift-scan/drift-report.json \
  --markdown ../../examples/drift-scan/drift-report.md
```

The command writes a versioned `TerminologyDriftReport` JSON artifact and an optional markdown review summary.

Useful report fields:

| Field | Meaning |
| --- | --- |
| `metrics.unknown_alias_rate` | Share of matched + unmatched terminology mentions represented by unmatched candidates. |
| `metrics.unknown_candidate_count` | Count of unmatched terminology candidates emitted as `alias_drift`. |
| `metrics.stale_term_count` | Count of dictionary terms with little or no corpus evidence. |
| `metrics.binding_lag_count` | Count of binding lag findings emitted from optional metadata. |
| `metrics.ambiguity_signal_count` | Count of conservative alias ambiguity review hints. |
| `findings[].evidence` | Source snippets that explain why a finding exists. |

## Tune the scan

The scan reuses the deterministic candidate discovery engine. Start strict, then relax if you need more candidates:

```bash
poetry run skeinrank drift scan \
  --dictionary ../../examples/drift-scan/company.dictionary.json \
  --docs ../../examples/drift-scan/docs \
  --min-frequency 2 \
  --min-document-frequency 1 \
  --max-candidates 25
```

Disable optional detectors when you want a narrower report:

```bash
poetry run skeinrank drift scan \
  --dictionary ../../examples/drift-scan/company.dictionary.json \
  --docs ../../examples/drift-scan/docs \
  --no-stale-terms \
  --no-binding-lag \
  --no-ambiguity-signals
```

## Use Python

```python
from skeinrank import DriftScanConfig, merge_binding_metadata, scan_dictionary_drift

config = merge_binding_metadata(
    DriftScanConfig(discovery={"min_frequency": 2}),
    "../../examples/drift-scan/binding-metadata.json",
)

report = scan_dictionary_drift(
    dictionary="../../examples/drift-scan/company.dictionary.json",
    docs=["../../examples/drift-scan/docs"],
    config=config,
)

print(report.summary().unknown_alias_rate)
print(report.to_markdown())
```

## Convert reviewed findings into a draft

After a human reviews the report, turn `alias_drift` findings into a local dictionary draft:

```bash
poetry run skeinrank drift export-draft ../../examples/drift-scan/drift-report.json \
  --out ../../examples/drift-scan/drift.dictionary-draft.json \
  --review ../../examples/drift-scan/drift.dictionary-draft.md
```

Only `alias_drift` findings become draft candidates. `stale_term`, `binding_lag`, and `ambiguity_signal` findings are preserved as review findings so humans can decide whether to create dictionary proposals, context rules, or rollout tasks later.

```python
from skeinrank import drift_report_to_dictionary_draft

result = drift_report_to_dictionary_draft("../../examples/drift-scan/drift-report.json")
print(result.review_markdown())
result.save("../../examples/drift-scan/drift.dictionary-draft.json")
```

## Safety boundary

Terminology drift reports are intentionally review-first:

- no Governance API calls;
- no model-provider calls;
- no automatic production proposal creation;
- no snapshot publishing;
- no binding updates;
- no runtime dictionary mutation;
- no search-log or click-data requirement.

The workflow is:

```text
scan local corpus -> review report -> export draft -> reviewer decides next action
```
