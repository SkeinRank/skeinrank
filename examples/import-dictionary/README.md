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

The command prints a conversion report with canonical term counts, alias counts, and review findings such as duplicate mappings or aliases that point to more than one canonical value.
