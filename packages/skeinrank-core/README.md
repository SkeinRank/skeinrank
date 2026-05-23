# skeinrank-core

`skeinrank-core` is the stable Python core for SkeinRank.

It provides two practical capabilities:

- profile-based reranking with passports and strict contracts
- rule-based attribute extraction and normalization for technical text

## Install

```bash
python -m pip install -e .
```

Optional extras are available, but they are not required for the current MVP.


## Public Python SDK API

Patch 41 adds a lightweight dictionary-first SDK API that can be used without running the governance API, Elasticsearch, Celery, or the UI. It accepts the same dictionary JSON/YAML shape exported by the User Console API and used by `skeinrank-migrate`. New files should declare `schema_version: skeinrank.dictionary.v1`; legacy files without a schema version are treated as v1 for now.

```python
from skeinrank import load_dictionary, extract_terms, canonicalize_text

dictionary = load_dictionary("../../examples/migration/console_dictionary.example.json")

result = extract_terms(
    "This instruction helps deploy 500 k8s servers backed by Postgres.",
    dictionary=dictionary,
)

print(result.canonical_values)  # ["kubernetes", "postgresql"]
print(result.matches[0].highlighted_fragment)

canonicalized = canonicalize_text(
    "k8s rollout uses pg database",
    dictionary=dictionary,
)
print(canonicalized.text)  # "kubernetes rollout uses postgresql database"
```

The stable SDK exports:

- `Dictionary`, `DictionaryTerm`, `DictionaryAlias`, `DictionaryStopListEntry`
- `load_dictionary(...)`
- `validate_dictionary(...)`
- `extract_terms(...)`
- `canonicalize_text(...)`
- `ExtractionResult`, `TermMatch`, `CanonicalizedText`

The SDK matcher is deterministic and local. It honors active/deprecated term and alias statuses, profile/global stop lists, returns offsets, and includes evidence snippets with `<mark>...</mark>` highlights.

## Document text extraction utilities

Patch 42 adds lightweight local helpers for extracting text from common document files before running the public SDK matcher. These helpers do not require the governance API, Elasticsearch, Celery, or a database.

```python
from skeinrank import load_dictionary, load_document_text, extract_terms_from_document

dictionary = load_dictionary("../../examples/migration/console_dictionary.example.json")
text = load_document_text("incident-runbook.md")

result = extract_terms_from_document(
    "incident-runbook.md",
    dictionary=dictionary,
)

print(result.document.file_name)
print(result.extraction.canonical_values)
```

Supported formats without extra dependencies:

- text-like files: `.txt`, `.md`, `.rst`, `.log`, `.csv`, `.tsv`, `.json`, `.jsonl`, `.yaml`, `.yml`
- `.html` / `.htm` with scripts/styles ignored
- `.docx` via a small stdlib ZIP/XML reader

PDF extraction is supported when the caller installs `pypdf` in the environment. The core package does not require it by default so the SDK stays lightweight.

Stable public exports include:

- `DocumentText`, `DocumentExtractionResult`, `DocumentExtractionError`
- `load_document_text(...)`
- `extract_document_text(...)`
- `extract_terms_from_document(...)`


## Local dictionary extraction CLI

Patch 43 adds a lightweight `skeinrank` CLI for local dictionary validation, text/document extraction, and canonicalization. It uses only the public SDK/document helpers and does not require the governance API, Elasticsearch, Celery, RabbitMQ, or a database.

Validate a dictionary exported from the Console API or used by `skeinrank-migrate`:

```bash
poetry run skeinrank validate-dictionary ../../examples/migration/console_dictionary.example.json
poetry run skeinrank validate-dictionary ../../examples/migration/console_dictionary.example.yaml
poetry run skeinrank validate-dictionary ../../examples/migration/console_dictionary.example.json --json
```

Extract canonical terms from raw text:

```bash
poetry run skeinrank extract "k8s rollout uses pg database" \
  --text \
  --dictionary ../../examples/migration/console_dictionary.example.json
```

Extract canonical terms from a supported local document:

```bash
poetry run skeinrank extract incident-runbook.md \
  --dictionary ../../examples/migration/console_dictionary.example.json
```

Canonicalize raw text or document text:

```bash
poetry run skeinrank canonicalize "k8s rollout uses pg database" \
  --text \
  --dictionary ../../examples/migration/console_dictionary.example.json

poetry run skeinrank canonicalize incident-runbook.md \
  --dictionary ../../examples/migration/console_dictionary.example.json \
  --output incident-runbook.canonicalized.txt
```

Extract plain text from a document before matching:

```bash
poetry run skeinrank document-text incident-runbook.docx --output incident-runbook.txt
```

The CLI returns JSON for `extract`, raw text by default for `canonicalize`/`document-text`, and supports `--output`, `--compact`, `--max-matches`, and `--context-chars` where relevant.

## PyPI/TestPyPI publishing

Patch 44 adds publishing polish for the lightweight `skeinrank` package. The recommended flow is:

1. Build and test locally.
2. Publish to TestPyPI.
3. Install from TestPyPI in a clean environment.
4. Publish to PyPI only after the TestPyPI smoke test passes.

Local packaging checks:

```bash
poetry install
poetry run pytest -q
poetry build
poetry run python -m pip install --upgrade twine
poetry run twine check dist/*
```

The manual GitHub Actions workflow is `publish-skeinrank-core`. It defaults to `dry_run=true`, supports `testpypi` and `pypi` targets, and uses PyPI Trusted Publishing for the actual upload step.

PDF extraction support stays optional. Install `pypdf` separately when needed:

```bash
pip install pypdf
```

See `docs/PUBLISHING.md` for the full release checklist.

## Minimal attribute extraction example

```python
from skeinrank import extract_attributes

pack = extract_attributes(
    "K8s api-server crashloop on version 1.28",
    profile="default_it",
    debug=True,
)

for item in pack.attributes:
    print(item.slot, item.value)

print(pack.passport)
```

## Custom terminology profile

You can build a profile directly in Python:

```python
from skeinrank import build_attribute_profile, extract_attributes

profile = build_attribute_profile(
    profile_id="company_terms",
    aliases={
        "kubernetes": ["k8s", "kube", "kuber"],
        "postgresql": ["pg", "postgres"],
    },
    slots={
        "kubernetes": "TOOL",
        "postgresql": "DB",
    },
    snapshot_version="company_terms@v1",
)

pack = extract_attributes("kuber timeout on pg", profile=profile)
```

Or create a starter profile and load it as a JSON snapshot:

```bash
poetry run skeinrank-init-profile company_terms.json
poetry run skeinrank-validate-profile company_terms.json
```

```python
from skeinrank import extract_attributes, load_attribute_profile

profile = load_attribute_profile("company_terms.json")
pack = extract_attributes("kuber timeout on pg", profile=profile)
```

A profile file can use the compact grouped alias format:

```json
{
  "profile_id": "company_terms",
  "snapshot": {
    "version": "company_terms@v1",
    "source": "file"
  },
  "aliases": [
    {
      "slot": "TOOL",
      "canonical": "kubernetes",
      "aliases": ["k8s", "kube", "kuber"]
    },
    {
      "slot": "DB",
      "canonical": "postgresql",
      "aliases": ["pg", "postgres", "psql"]
    }
  ],
  "rules": []
}
```

The CLI accepts the same file with `--profile-file`.

Validate a profile before using it for extraction or enrichment:

```bash
poetry run skeinrank-validate-profile company_terms.json
poetry run skeinrank-validate-profile company_terms.json --json
poetry run skeinrank-validate-profile company_terms.json --strict
# Optional: customize short-alias warning threshold
poetry run skeinrank-validate-profile company_terms.json --min-short-alias-length 4
```

The validation report catches fatal alias collisions and warns about aliases that are likely to hurt retrieval quality, such as overly generic terms (`api`, `service`, `app`) or very short aliases (`pg`, `go`, `js`). It also validates governance statuses (`active`, `deprecated`, `pending`, `ambiguous`, `disabled`, `rejected`) and can elevate warnings to errors in `--strict` mode before publishing a snapshot.

## Optional fuzzy alias fallback

Exact alias matching is the default. Enable fuzzy fallback only when you want to catch typo-like terms:

```python
from skeinrank import extract_attributes, load_attribute_profile

profile = load_attribute_profile("company_terms.json")
pack = extract_attributes(
    "kubernets timeout on postgress",
    profile=profile,
    enable_fuzzy=True,
    fuzzy_threshold=0.88,
)
```

The same option is available in CLI commands:

```bash
poetry run skeinrank-extract \
  --text "kubernets timeout on postgress" \
  --profile-file company_terms.json \
  --enable-fuzzy \
  --fuzzy-threshold 0.88
```

Fuzzy matching is intentionally conservative: it is disabled by default, ignores short aliases by default, and marks matches as `fuzzy_alias` in attributes/passport output.

## High-level Python enrichment

Use `enrich_texts(...)` when you want to process a small in-memory corpus without writing the extraction loop yourself.

```python
from skeinrank import build_attribute_profile, enrich_texts

profile = build_attribute_profile(
    profile_id="company_terms",
    aliases={
        "kubernetes": ["k8s", "kube", "kuber"],
        "postgresql": ["pg", "postgres", "psql"],
    },
    slots={
        "kubernetes": "TOOL",
        "postgresql": "DB",
    },
    snapshot_version="company_terms@v1",
)

rows = enrich_texts(
    [
        {"id": "doc-1", "text": "k8s timeout after upgrade"},
        {"id": "doc-2", "text": "pg latency spike"},
    ],
    profile=profile,
)

print(rows[0]["canonical_values"])  # ["kubernetes"]
```

By default, the result is compact and search-friendly: `canonical_values`, `slots`, `snapshot_version`, and `alias_matcher_backend`. Use `include_attributes=True` or `include_passport=True` when you need explainability/debug output.

## Batch enrichment and demo eval

The core package also ships helper functions and product-friendly CLI entrypoints for demo workflows.

From a source checkout:

```bash
poetry run skeinrank-extract --text "kube api timeout" --debug

poetry run skeinrank-enrich-jsonl \
  ../../examples/demo/demo_documents.jsonl \
  ../../examples/demo/demo_enriched_documents.jsonl

poetry run skeinrank-eval-demo \
  ../../examples/demo/demo_queries.jsonl \
  ../../examples/demo/demo_enriched_documents.jsonl \
  --out ../../examples/demo/demo_eval_results.json
```

## What the default attribute profile does

The default file-based profile lives under `skeinrank/attributes/config/default_it.json` and currently implements:

- canonical alias mapping (for example `k8s -> kubernetes`)
- versioned snapshot metadata for repeatable enrichment runs
- Aho-Corasick alias matching for fast in-memory runtime lookup
- regex/rule extraction for selected slots
- slot limits and total limits
- explainable passport/debug traces

## Run tests from a source checkout

```bash
poetry run pytest -q
```

## Public API

Only symbols re-exported from `skeinrank.__init__` should be treated as stable public API.
