# Suggest a dictionary from documents

These examples show the deterministic cold-start flow for teams that do not have a dictionary yet. The command scans local documents, finds significant unmatched terminology candidates, and writes a reviewable draft.

No model provider, API token, Governance API, Elasticsearch, or Docker stack is required.

## CLI

```bash
cd packages/skeinrank-core

poetry run skeinrank suggest-dictionary ../../examples/suggest-dictionary/docs \
  --profile-name platform_candidates \
  --min-frequency 2 \
  --out ../../examples/suggest-dictionary/platform_candidates.dictionary-draft.json \
  --review ../../examples/suggest-dictionary/platform_candidates.review.md
```

Use `--dictionary` to filter terms and aliases that are already governed:

```bash
poetry run skeinrank suggest-dictionary ../../examples/suggest-dictionary/docs \
  --dictionary ../../examples/sdk/platform_ops_demo.dictionary.json \
  --profile-name platform_candidates \
  --out ../../examples/suggest-dictionary/platform_candidates.dictionary-draft.json
```

## Python example

```bash
cd packages/skeinrank-core
poetry run python ../../examples/suggest-dictionary/suggest_from_docs.py
```

The script prints the review markdown and shows the review boundary. If the generated draft contains exportable aliases, it also performs a local in-memory preview. Production workflows should review candidates before rollout.
