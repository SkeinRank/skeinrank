# Import existing dictionaries

These examples show how to convert existing terminology files into local SkeinRank dictionary candidates. The import flow is offline: it writes a candidate dictionary or draft and a review report, but it does not change production runtime state.

## Convert CSV or ES synonyms

```bash
cd packages/skeinrank-core

poetry run skeinrank import-dictionary ../../examples/import-dictionary/company_terms.csv \
  --name platform_ops_import \
  --out ../../examples/import-dictionary/company_terms.dictionary.json

poetry run skeinrank import-dictionary ../../examples/import-dictionary/es_synonyms.txt \
  --format es-synonyms \
  --name platform_ops_import \
  --out ../../examples/import-dictionary/es_synonyms.dictionary.json
```

The command prints a conversion report with canonical term counts, alias counts, parse findings, build findings, and validator findings.

## Write a report

```bash
poetry run skeinrank import-dictionary ../../examples/import-dictionary/terms.json \
  --report ../../examples/import-dictionary/import-report.md

poetry run skeinrank import-dictionary ../../examples/import-dictionary/terms.json \
  --json-report \
  --compact
```

`--report` writes markdown. `--json-report` prints a machine-readable report to stdout.

## Create a reviewable draft

```bash
poetry run skeinrank import-dictionary ../../examples/import-dictionary/es_synonyms.txt \
  --format es-synonyms \
  --name platform_ops_import \
  --draft-out ../../examples/import-dictionary/es_synonyms.dictionary-draft.json \
  --report ../../examples/import-dictionary/es_synonyms.import-report.md
```

The draft artifact keeps every candidate in `proposed` status. Reviewers can inspect it before accepting any runtime dictionary changes.

## Python example

```bash
cd packages/skeinrank-core
poetry run python ../../examples/import-dictionary/import_existing_dictionary.py
```

The script converts `es_synonyms.txt`, prints the report, creates a draft, accepts the draft for local preview, and canonicalizes a sample query. It is a local preview only; it does not write to governance state or runtime bindings.
