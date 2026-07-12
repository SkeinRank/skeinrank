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
| `stale_term` | A dictionary term has little or no evidence in an eligible corpus. | Review whether the term is deprecated, out of scope, or still needed elsewhere. |
| `binding_lag` | Local binding metadata says the pinned snapshot is behind the latest approved snapshot. | Review whether the binding should roll forward. |
| `ambiguity_signal` | A short existing alias appears near unfamiliar context terms. | Review context rules or split meanings; do not auto-change the alias. |

The scan is not a real-time monitor and is not search observability. It does not require query logs, click data, relevance labels, or production access. Staleness is treated as a corpus-level signal: by default it runs only when at least 20 documents are present. Smaller corpora still produce alias, binding, and ambiguity findings, while the report records that stale analysis was skipped.

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
| `metrics.stale_term_count` | Count of dictionary terms with little or no corpus evidence when stale analysis completed. |
| `metrics.stale_analysis_status` | `completed`, `skipped`, or `disabled`. |
| `metrics.stale_analysis_reason` | Why stale analysis ran or did not run. |
| `metrics.stale_min_document_count` | Corpus-size threshold used by the scan. |
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
  --max-candidates 25 \
  --stale-min-documents 20
```


Candidate discovery removes common documentation noise before scoring. Repeated lines that occur across a configured share of at least three documents are treated as boilerplate, and reStructuredText directives such as `.. code-block::` plus option lines such as `:header-rows:` are skipped. The discovery report records `input_line_count`, `scanned_line_count`, `skipped_line_count`, `skipped_lines_by_reason`, and `boilerplate_line_pattern_count` so filtering remains reviewable.

Evidence entries carry a `context` value from the deterministic `context-v2` classifier. Markdown fenced blocks, four-space and tab-indented blocks, inline backticks, reStructuredText code directives, literal blocks introduced by `::`, `literalinclude` directives, and inline double-backtick literals are distinguished from surrounding prose. Candidates found in both prose and code receive a positive context adjustment. Code-only candidates remain in the report with a negative adjustment rather than being removed, so review workflows retain API names while lowering example-specific idioms. The score breakdown exposes signed `context_score`, signed `context_adjustment`, and `context_counts` for downstream policies such as prose-required benchmark evaluation.

To intentionally run stale analysis on a small controlled fixture or narrow corpus, lower the threshold explicitly:

```bash
poetry run skeinrank drift scan \
  --dictionary ../../examples/drift-scan/company.dictionary.json \
  --docs ../../examples/drift-scan/docs \
  --stale-min-documents 1
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
    DriftScanConfig(
        stale_min_document_count=20,
        discovery={"min_frequency": 2},
    ),
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
  --review ../../examples/drift-scan/drift.dictionary-draft.md \
  --summary ../../examples/drift-scan/drift.conversion-summary.json
```

Only `alias_drift` findings become draft candidates. `stale_term`, `binding_lag`, and `ambiguity_signal` findings are preserved as review findings so humans can decide whether to create dictionary proposals, context rules, or rollout tasks later.

The conversion summary separates three counts that were previously easy to confuse:

- all findings in the source report;
- `alias_drift` findings eligible to become candidates;
- findings retained for review but not converted into candidates.

A report can therefore contain valid findings and still produce an empty candidate list. In that case `summary.status` is `no_convertible_findings`, `skipped_findings_by_type` explains the finding types, and the CLI prints a precise reason instead of implying that a threshold silently removed candidates.

```python
from skeinrank import drift_report_to_dictionary_draft

result = drift_report_to_dictionary_draft("../../examples/drift-scan/drift-report.json")
print(result.summary.status)
print(result.summary.source_finding_count)
print(result.summary.alias_drift_finding_count)
print(result.summary.skipped_findings_by_type)
print(result.review_markdown())
result.save("../../examples/drift-scan/drift.dictionary-draft.json")
result.save_summary("../../examples/drift-scan/drift.conversion-summary.json")
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
