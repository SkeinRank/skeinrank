# Import existing dictionaries

Many teams already have terminology stored in small, local formats: Elasticsearch synonym files, CSV exports, wiki tables, or ad-hoc JSON dictionaries. `skeinrank import-dictionary` converts those files into a SkeinRank dictionary candidate and a review report.

The command is local and proposal-first. It does not connect to the Governance API, publish snapshots, update bindings, or touch production runtime state.

## When to use this flow

Use this flow when you already have a term list and want to bring it into a governed dictionary lifecycle:

- an Elasticsearch/OpenSearch synonym list;
- a CSV file from a spreadsheet;
- a simple JSON mapping such as `{"kubernetes": ["k8s", "kube"]}`;
- a small manually maintained alias file that should become reviewable and versioned.

For a cold start with no dictionary, use [Agent dictionary assistant](agent-dictionary-assistant.md) instead.

## Supported inputs

| Format | Example | Notes |
| --- | --- | --- |
| JSON mapping | `{"kubernetes": ["k8s", "kube"]}` | Good for simple programmatic dictionaries. |
| CSV | `canonical,alias,slot` | Good for spreadsheet exports. |
| ES synonyms | `k8s, kube => kubernetes` | Good for moving from synonym configuration to governed terminology. |

## Convert to a dictionary candidate

From the repository root:

```bash
cd packages/skeinrank-core

poetry run skeinrank import-dictionary ../../examples/import-dictionary/company_terms.csv \
  --name platform_ops_import \
  --out ../../examples/import-dictionary/company_terms.dictionary.json
```

For Elasticsearch/OpenSearch synonym-list input:

```bash
poetry run skeinrank import-dictionary ../../examples/import-dictionary/es_synonyms.txt \
  --format es-synonyms \
  --name platform_ops_import \
  --out ../../examples/import-dictionary/es_synonyms.dictionary.json
```

The generated dictionary is a local artifact. Review it before applying it through any governance workflow.

## Write a reviewable draft

Use `--draft-out` when the imported file should be reviewed before it becomes a runtime dictionary:

```bash
poetry run skeinrank import-dictionary ../../examples/import-dictionary/es_synonyms.txt \
  --format es-synonyms \
  --name platform_ops_import \
  --draft-out ../../examples/import-dictionary/es_synonyms.dictionary-draft.json \
  --report ../../examples/import-dictionary/es_synonyms.import-report.md
```

Drafts keep candidates in `proposed` status. They are safe review artifacts, not runtime dictionaries.

## Review report

The import report combines three sources of findings:

| Source | Meaning |
| --- | --- |
| `parse` | Input rows or lines that were skipped or interpreted with assumptions. |
| `build` | Conversion findings such as duplicate mappings or alias conflicts. |
| `validate` | Findings from the same lightweight dictionary validator used by `validate-dictionary`. |

Useful modes:

```bash
poetry run skeinrank import-dictionary ../../examples/import-dictionary/terms.json \
  --json-report \
  --compact

poetry run skeinrank import-dictionary ../../examples/import-dictionary/es_synonyms.txt \
  --format es-synonyms \
  --strict-validate
```

`--no-validate` produces a raw conversion report. `--strict-validate` treats validator errors as fatal findings. The default mode is review-friendly: validator findings are surfaced for review without mutating anything.

## Python API

```python
from skeinrank import import_dictionary

result = import_dictionary(
    "../../examples/import-dictionary/es_synonyms.txt",
    fmt="es-synonyms",
    name="platform_ops_import",
)

print(result.report.to_markdown())
result.save("platform_ops_import.dictionary.json")

draft = result.to_draft()
print(draft.review_markdown())
```

To export a runtime dictionary from a draft, accept candidates explicitly:

```python
runtime_dictionary = draft.accept_all().to_dictionary()
```

That explicit transition is intentional: imports propose terminology, humans approve it, and runtime serving remains deterministic.

## Reference examples

- [`examples/import-dictionary/company_terms.csv`](../../examples/import-dictionary/company_terms.csv)
- [`examples/import-dictionary/es_synonyms.txt`](../../examples/import-dictionary/es_synonyms.txt)
- [`examples/import-dictionary/terms.json`](../../examples/import-dictionary/terms.json)
- [`examples/import-dictionary/import_existing_dictionary.py`](../../examples/import-dictionary/import_existing_dictionary.py)

## Safety boundary

`import-dictionary` is an offline conversion tool. It does not:

- call OpenRouter or any model provider;
- connect to Elasticsearch/OpenSearch;
- create proposals in the Governance API;
- publish snapshots;
- change bindings;
- mutate production search behavior.

The output is a candidate file plus a report. Production rollout should still use the normal review, validation, snapshot, and binding workflow.
