# Core SDK and CLI

The core package is the fastest way to test SkeinRank locally. It does not require the governance API, UI, PostgreSQL, RabbitMQ, or Elasticsearch.

Use it for:

- dictionary validation;
- term extraction from text;
- text canonicalization;
- document text extraction;
- small local scripts and notebooks;
- smoke testing before importing a dictionary into the platform.

## Install locally from the monorepo

```bash
cd packages/skeinrank-core
poetry install
```

## Validate a dictionary

```bash
poetry run skeinrank validate-dictionary ../../examples/migration/console_dictionary.example.json
```

The validator checks dictionary shape and helps catch alias/canonicalization issues before a profile is imported into the governance platform.

## Extract canonical terms from text

```bash
poetry run skeinrank extract "k8s rollout uses pg database" \
  --text \
  --dictionary ../../examples/migration/console_dictionary.example.json
```

## Canonicalize text

```bash
poetry run skeinrank canonicalize "k8s rollout uses pg database" \
  --text \
  --dictionary ../../examples/migration/console_dictionary.example.json
```

## Extract document text

```bash
poetry run skeinrank document-text incident-runbook.md
```

The document helpers can load text from TXT, Markdown, logs, CSV, JSON, YAML-like files, HTML, DOCX, and PDF when optional PDF dependencies are installed by the caller.

## Python SDK

```python
from skeinrank import load_dictionary, extract_terms

dictionary = load_dictionary("examples/migration/console_dictionary.example.json")
result = extract_terms("k8s rollout uses pg database", dictionary=dictionary)

print(result.canonical_values)  # ["kubernetes", "postgresql"]
```

Document extraction:

```python
from skeinrank import load_dictionary, extract_terms_from_document

dictionary = load_dictionary("examples/migration/console_dictionary.example.json")
result = extract_terms_from_document("docs/incident-runbook.md", dictionary=dictionary)

print(result.document.file_name)
print(result.extraction.canonical_values)
```

## Profile-file extraction path

The lower-level profile-file tools are still available for custom extraction profiles:

```bash
skeinrank-init-profile company_terms.json
skeinrank-validate-profile company_terms.json

skeinrank-extract --text "kuber timeout on pg" --profile-file ./company_terms.json
skeinrank-enrich-jsonl docs.jsonl enriched.jsonl --profile-file ./company_terms.json
```

## Optional fuzzy alias fallback

Exact alias matching remains the default. Conservative fuzzy matching is opt-in:

```bash
skeinrank-extract \
  --text "kubernets timeout on postgress" \
  --profile-file ./company_terms.json \
  --enable-fuzzy \
  --fuzzy-threshold 0.88
```

Fuzzy matching is disabled by default, ignores short aliases such as `pg`, and reports accepted matches as `fuzzy_alias` in extraction output.

## Demo corpus

The repository includes a tiny demo corpus under `examples/demo/`:

- `demo_documents.jsonl`;
- `demo_queries.jsonl`;
- `demo_enriched_documents.jsonl`;
- `demo_eval_results.json`.

Batch-enrich demo documents:

```bash
cd packages/skeinrank-core
poetry run skeinrank-enrich-jsonl \
  ../../examples/demo/demo_documents.jsonl \
  ../../examples/demo/demo_enriched_documents.jsonl
```

Run the demo evaluation:

```bash
poetry run skeinrank-eval-demo \
  ../../examples/demo/demo_queries.jsonl \
  ../../examples/demo/demo_enriched_documents.jsonl \
  --out ../../examples/demo/demo_eval_results.json
```

The demo is intentionally small. It exists to make alias-heavy queries visibly testable, not to represent a benchmark claim.

## Packaging and PyPI

The lightweight package is published as `skeinrank`.

Release checklist lives in:

```text
packages/skeinrank-core/docs/PUBLISHING.md
```

Local smoke test:

```bash
cd packages/skeinrank-core
poetry install
poetry run pytest -q
poetry build
poetry run python -m pip install --upgrade twine
poetry run twine check dist/*
```
