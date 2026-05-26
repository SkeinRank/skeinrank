# Retrieval eval baseline

Patch 50A added the first retrieval-quality baseline for the `platform_ops_v1`
benchmark. Patch 50B expands that same harness to a 200-document corpus with
hard negatives, so SkeinRank changes can be evaluated with ranking metrics and
noise/leakage checks instead of only proposal/runtime checks.

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
```

`retrieval_queries.jsonl` contains query ids, user-facing queries, expected
expansions, and descriptions. `qrels.jsonl` contains graded relevance labels for
benchmark documents. `hard_negatives.jsonl` marks intentionally confusing
documents that share alias-like terms but should not be treated as relevant.

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

50B adds:

```text
hard_negative_leakage@10
hard-negative leakage delta
per-result hard_negative flags
```

50B.1 adds query-hygiene diagnostics and safer expansion semantics:

```text
generic_token_noise@10
alias-to-canonical expansion
weighted domain terms
per-result noise_penalty
```

A successful retrieval baseline should show positive `delta.ndcg@10` and
`delta.recall@10` while keeping `delta.mrr@10` non-negative. With 50B, it should
also avoid increasing `hard_negative_leakage@10`; the expanded run is allowed to
operate in a noisy corpus, but hard-negative leakage must stay within the
configured ceiling and should not materially regress versus baseline. With
50B.1, SkeinRank expansion should also avoid amplifying generic-token noise and
should expand observed aliases toward canonical values rather than expanding
canonical terms back to ambiguous short aliases such as `service -> svc` or
`namespace -> ns`. This is still a deterministic benchmark harness, not a
production-scale search study; 500+ document and provider-backed retrieval
evaluations can build on this layer.

## Safety

50A/50B/50B.1 do not call OpenRouter, Elasticsearch, or the database. It does not submit
proposals, approve/apply changes, publish snapshots, or mutate runtime state.
