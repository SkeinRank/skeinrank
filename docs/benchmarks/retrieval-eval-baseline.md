# Retrieval eval baseline

Patch 50A adds the first retrieval-quality baseline for the `platform_ops_v1`
benchmark. It is intentionally small and deterministic: the fixture still uses
50 documents, but now includes retrieval queries and qrels so SkeinRank changes
can be evaluated with ranking metrics instead of only proposal/runtime checks.

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
  expected_aliases.json
```

`retrieval_queries.jsonl` contains query ids, user-facing queries, expected
expansions, and descriptions. `qrels.jsonl` contains graded relevance labels for
benchmark documents.

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
- `quality_gates[]` — regression gates for the first retrieval baseline.

50A reports:

```text
NDCG@10
MRR@10
Recall@10
Precision@10
```

A successful first baseline should show positive `delta.ndcg@10` and
`delta.recall@10` while keeping `delta.mrr@10` non-negative. The initial fixture
is not intended to prove production-scale quality; it proves the evaluator,
qrels format, report shape, and regression gates. Larger 200-500 document
retrieval corpora with hard negatives should come after this harness is stable.

## Safety

50A does not call OpenRouter, Elasticsearch, or the database. It does not submit
proposals, approve/apply changes, publish snapshots, or mutate runtime state.
