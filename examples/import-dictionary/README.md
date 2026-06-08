# Import existing dictionaries

These examples show how to convert existing term lists into the SkeinRank dictionary shape without touching production runtime state.

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

The command prints a conversion report with canonical term counts, alias counts, and review findings such as duplicate mappings, aliases that point to more than one canonical value, risky short aliases, and validator findings from the lightweight dictionary validator.

Useful report modes:

```bash
poetry run skeinrank import-dictionary ../../examples/import-dictionary/terms.json \
  --json-report \
  --report ../../examples/import-dictionary/import-report.json

poetry run skeinrank import-dictionary ../../examples/import-dictionary/es_synonyms.txt \
  --format es-synonyms \
  --strict-validate
```

`--no-validate` produces a raw conversion report. `--strict-validate` treats validator errors as fatal findings. The default mode is review-friendly: it reports validator errors as warnings unless the candidate payload itself is unusable.

Use `--draft-out` when the imported list should be reviewed before it becomes a runtime dictionary:

```bash
poetry run skeinrank import-dictionary ../../examples/import-dictionary/es_synonyms.txt \
  --format es-synonyms \
  --name platform_ops_import \
  --draft-out ../../examples/import-dictionary/es_synonyms.dictionary-draft.json
```

The draft artifact keeps every candidate in `proposed` status. Python callers can render a review summary and export a runtime dictionary only after an explicit review step:

```python
from skeinrank import DictionaryDraft

draft = DictionaryDraft.from_file("es_synonyms.dictionary-draft.json")
print(draft.review_markdown())

runtime_dictionary = draft.accept_all().to_dictionary()
```
