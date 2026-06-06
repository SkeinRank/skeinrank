# 5k synthetic smoke generator

The synthetic smoke generator creates a deterministic 5,000-document corpus for
the `platform_ops_v1` benchmark family. This layer is not a hand-labeled
retrieval quality benchmark. It is a scale smoke fixture for checking that local
tooling, batching, skip/unchanged accounting, report plumbing, and worker/job
flows can handle a larger corpus shape without paying for model calls.

The generator creates a JSONL corpus and a compact manifest under
`examples/benchmarks/platform_ops_v1/reports/synthetic/` by default. Generated
files are local artifacts and should not be committed.

## What it generates

Default shape:

```text
5,000 documents
10 batches x 500 documents
5 synthetic roles
10 platform/domain patterns
```

Synthetic roles:

```text
semantic_noise
near_duplicate
hard_negative
weak_platform_adjacent
golden_relevant
```

The generated documents include repeated platform operations surfaces such as
`pg`, `k8s`, `rmq`, `otel`, `es`, `prom`, `lk`, `svc`, `ns`, and `slo`, with both
relevant and intentionally misleading contexts. The point is to create stable
hard-negative and near-duplicate pressure at larger volume.

## Commands

Run from the repository root:

```bash
make benchmark-smoke-plan
make benchmark-smoke-generate
make benchmark-smoke-report
make benchmark-smoke-clean
```

Direct CLI usage:

```bash
cd packages/skeinrank-governance-api
poetry run python -m skeinrank_governance_api.synthetic_smoke plan
poetry run python -m skeinrank_governance_api.synthetic_smoke generate \
  --out ../../examples/benchmarks/platform_ops_v1/reports/synthetic/platform_ops_v1-5k-corpus.jsonl \
  --manifest ../../examples/benchmarks/platform_ops_v1/reports/synthetic/platform_ops_v1-5k-manifest.json
poetry run python -m skeinrank_governance_api.synthetic_smoke report \
  --manifest ../../examples/benchmarks/platform_ops_v1/reports/synthetic/platform_ops_v1-5k-manifest.json
```

Poetry script:

```bash
poetry run skeinrank-governance-synthetic-smoke generate
```

## Manifest

The manifest schema is:

```text
skeinrank.synthetic_smoke_manifest.v1
```

It records:

```text
document_count
batch_size
batches_total
role_counts
source_type_counts
top_aliases
unchanged_skip_candidates
corpus_sha256
batches[]
safety
```

The generated document schema is:

```text
skeinrank.synthetic_smoke_document.v1
```

## Safety

This smoke generator is fully offline:

```text
OpenRouter calls: false
Elasticsearch calls: false
database calls: false
runtime mutation: false
```

It does not submit proposals, approve/apply changes, publish snapshots, call LLM
providers, call Elasticsearch, or touch the governance database. It only writes
local generated JSON files when `generate` is invoked.

## Relationship to the 500-document corpus

The default 500-document corpus is the quality benchmark with qrels and
hard-negative labels. The 5,000-document synthetic corpus intentionally does not
try to label every generated document. It provides a repeatable larger corpus
shape for scale smoke checks before moving into cost, latency, and throughput
reporting.
