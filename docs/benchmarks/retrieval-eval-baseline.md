# Retrieval eval baseline

The retrieval evaluation baseline measures whether SkeinRank canonicalization and
alias expansion improve ranking quality for the `platform_ops_v1` benchmark. It
uses a 500-document corpus with graded relevance labels, hard negatives, and
query-hygiene diagnostics so retrieval changes can be evaluated with ranking
metrics instead of proposal/runtime checks alone.

This layer answers a different question than the agent workflow benchmark:

```text
Does SkeinRank canonicalization/expansion improve retrieval ranking quality?
```

## Fixtures

The retrieval fixtures live next to the benchmark corpus:

```text
examples/benchmarks/platform_ops_v1/
  corpus.jsonl
  retrieval_queries.jsonl
  qrels.jsonl
  hard_negatives.jsonl
  expected_aliases.json
  corpus_manifest.json
```

`retrieval_queries.jsonl` contains query ids, user-facing queries, expected
expansions, and descriptions. `qrels.jsonl` contains graded relevance labels for
benchmark documents. `hard_negatives.jsonl` marks intentionally confusing
documents that share alias-like terms but should not be treated as relevant.
`corpus_manifest.json` records the 500-document corpus shape: total documents,
added documents, labeled hard negatives, semantic-noise rows, near-duplicates,
and weak platform-adjacent rows.

The baseline run uses literal query terms. The SkeinRank run expands known
aliases and canonicals from the benchmark dictionary and expected alias map, for
example:

```text
rmq -> rabbitmq
k8s/kube -> kubernetes
otel -> opentelemetry
pg/postgres -> postgresql
lk -> loki
es/elastic -> elasticsearch
```

## Commands

Run from the repository root:

```bash
make benchmark-retrieval-plan
make benchmark-retrieval-eval
make benchmark-retrieval-report
make benchmark-retrieval-clean
```

Direct CLI usage is also available:

```bash
cd packages/skeinrank-governance-api
poetry run python -m skeinrank_governance_api.retrieval_eval plan
poetry run python -m skeinrank_governance_api.retrieval_eval eval \
  --out ../../examples/benchmarks/platform_ops_v1/reports/platform_ops_v1-retrieval-report.json
poetry run python -m skeinrank_governance_api.retrieval_eval report \
  --file ../../examples/benchmarks/platform_ops_v1/reports/platform_ops_v1-retrieval-report.json
```

The Poetry script name is:

```bash
poetry run skeinrank-governance-retrieval-eval eval
```

## Metrics

The report schema is `skeinrank.retrieval_eval_report.v1`. It contains:

- `baseline` — literal lexical retrieval metrics;
- `skeinrank` — SkeinRank-expanded lexical retrieval metrics;
- `delta` — SkeinRank minus baseline;
- `per_query[]` — query-level rankings, matched terms, relevant documents, and metric deltas;
- `quality_gates[]` — regression gates for the retrieval baseline.

The core ranking metrics are:

```text
NDCG@10
MRR@10
Recall@10
Precision@10
```

The hard-negative diagnostics are:

```text
hard_negative_leakage@10
hard-negative leakage delta
per-result hard_negative flags
```

The query-hygiene diagnostics are:

```text
generic_token_noise@10
alias-to-canonical expansion
weighted domain terms
per-result noise_penalty
```

A successful retrieval baseline should show positive `delta.ndcg@10` and
`delta.recall@10` while keeping `delta.mrr@10` non-negative. It should also
avoid increasing `hard_negative_leakage@10`; the expanded run is allowed to
operate in a noisy corpus, but hard-negative leakage must stay within the
configured ceiling and should not materially regress versus baseline.
SkeinRank expansion should also avoid amplifying generic-token noise and should
expand observed aliases toward canonical values rather than expanding canonical
terms back to ambiguous short aliases such as `service -> svc` or
`namespace -> ns`.

This is a deterministic benchmark harness, not a production-scale search study.
The default corpus is suitable for a small controlled quality benchmark;
provider-backed and large smoke evaluations can build on this layer.

## Safety

This evaluator does not call OpenRouter, Elasticsearch, or the database. It does
not submit proposals, approve/apply changes, publish snapshots, or mutate runtime
state.

## Retrieval comparison report

The retrieval comparison report is an operator-facing summary for benchmark,
pilot, and company-index runs. It consumes any
`skeinrank.retrieval_eval_report.v1` file and writes
`skeinrank.retrieval_comparison_report.v1` without calling OpenRouter,
Elasticsearch, the database, or runtime mutation endpoints.

Run from the repository root after `benchmark-retrieval-eval`:

```bash
make benchmark-retrieval-compare
make benchmark-retrieval-compare-report
```

Or run the full local flow:

```bash
make benchmark-retrieval-run
```

Direct CLI usage:

```bash
cd packages/skeinrank-governance-api
poetry run skeinrank-governance-retrieval-compare compare \
  --input ../../examples/benchmarks/platform_ops_v1/reports/platform_ops_v1-retrieval-report.json \
  --out ../../examples/benchmarks/platform_ops_v1/reports/platform_ops_v1-retrieval-comparison-report.json
poetry run skeinrank-governance-retrieval-compare report \
  --file ../../examples/benchmarks/platform_ops_v1/reports/platform_ops_v1-retrieval-comparison-report.json
```

The comparison report includes:

```text
query_counts
query_groups.largest_ndcg_improvements
query_groups.largest_ndcg_regressions
query_groups.high_hard_negative_leakage
query_groups.high_generic_token_noise
query_groups.zero_recall_after_expansion
query_groups.no_gain_with_expansion
query_diagnostics[].recommended_actions
```

For pilot/company index evaluation, the intended contract is the same: produce or
export a retrieval eval report in `skeinrank.retrieval_eval_report.v1` format,
then run the comparison CLI against that file. This keeps the comparison layer
provider-independent while still giving operators a compact view of regressions,
hard-negative leakage, generic-token noise, and zero-recall queries.
