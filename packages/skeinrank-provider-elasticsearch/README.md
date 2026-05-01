# skeinrank-provider-elasticsearch

A lightweight Elasticsearch integration for SkeinRank.

This package has two small responsibilities:

1. Retrieve BM25 candidates from Elasticsearch and convert them into `skeinrank.Candidate` objects.
2. Enrich an existing Elasticsearch index with compact SkeinRank canonical attributes.

The enrichment command supports a safe `--dry-run` preview and an explicit `--write` mode. It reads documents, extracts attributes locally, and writes a partial update into a user-provided target field only when `--write` is passed.

## BM25 retrieval usage

```python
from elasticsearch import Elasticsearch
from skeinrank import RerankEngine
from skeinrank_provider_elasticsearch import ElasticsearchProvider

es = Elasticsearch("http://localhost:9200")
provider = ElasticsearchProvider(
    client=es,
    index="docs",
    text_fields=("title", "body"),
)

query = "okta password reset"
candidates, hits = provider.retrieve(query, size=100)

engine = RerankEngine(profile="rerank_auto")
out = engine.rerank(query, candidates, top_k=10)
print([r.id for r in out.ranked])
```

## Elasticsearch enrichment CLI

The CLI uses an explicit contract. SkeinRank does not guess how your index is shaped; you tell it where the source text lives and where the enrichment payload should be written.

```bash
python -m skeinrank_provider_elasticsearch.enrich_cli \
  --url http://localhost:9200 \
  --index docs \
  --text-field title \
  --text-field body \
  --target-field skeinrank \
  --profile default_it \
  --limit 10 \
  --batch-size 5 \
  --dry-run
```

Equivalent console script after installation:

```bash
skeinrank-es-enrich \
  --url http://localhost:9200 \
  --index docs \
  --text-field title \
  --text-field body \
  --target-field skeinrank \
  --dry-run
```

Example compact dry-run preview shape:

```json
{
  "summary": {
    "dry_run": true,
    "index": "docs",
    "text_fields": ["title", "body"],
    "target_field": "skeinrank",
    "previewed": 1,
    "include_evidence": false
  },
  "previews": [
    {
      "_id": "doc_1",
      "_index": "docs",
      "target_field": "skeinrank",
      "doc": {
        "skeinrank": {
          "profile_id": "default_it",
          "snapshot_version": "default_it@2026-04-29-v1",
          "alias_matcher_backend": "aho_corasick",
          "canonical_values": ["kubernetes", "timeout"],
          "slots": {
            "TOOL": ["kubernetes"],
            "ERROR": ["timeout"]
          }
        }
      }
    }
  ]
}
```

### Optional full evidence mode

The default Elasticsearch payload is compact and production-oriented. If you need full debug evidence, add `--include-evidence`:

```bash
skeinrank-es-enrich \
  --url http://localhost:9200 \
  --index docs \
  --text-field title \
  --text-field body \
  --target-field skeinrank \
  --include-evidence \
  --dry-run
```

This adds full `attributes`, per-match `evidences`, and the full snapshot object to the target field payload. Use it for debugging, not as the default shape for very large indexes.

### Write mode

Write mode is explicit and uses bulk partial updates. It adds or replaces only the configured target field on each matched document.

```bash
skeinrank-es-enrich \
  --url http://localhost:9200 \
  --index docs \
  --text-field title \
  --text-field body \
  --target-field skeinrank \
  --limit 100 \
  --batch-size 25 \
  --write
```

The target field receives a compact payload like:

```json
{
  "skeinrank": {
    "profile_id": "default_it",
    "snapshot_version": "default_it@2026-04-29-v1",
    "alias_matcher_backend": "aho_corasick",
    "canonical_values": ["kubernetes", "timeout"],
    "slots": {
      "TOOL": ["kubernetes"],
      "ERROR": ["timeout"]
    }
  }
}
```

## Current limits

- Tests use fake Elasticsearch clients; CI does not require a running cluster.
- The CLI updates the existing index in-place; production reindex-and-alias orchestration is intentionally left to the user.
- Dotted source fields such as `metadata.summary` are supported for common objects, but full Elasticsearch nested query semantics are intentionally out of scope for this CLI.

## Run tests from a source checkout

```bash
PYTHONPATH=.:../skeinrank-core pytest -q
```

## Notes

- You own the Elasticsearch index mappings and analyzers.
- Write mode is opt-in with `--write`; dry-run remains the recommended first check before touching an index.
- Compact payload is the default. Use `--include-evidence` only when you need a detailed debugging payload.
