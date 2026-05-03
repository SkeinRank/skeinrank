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

Or load a JSON snapshot:

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
