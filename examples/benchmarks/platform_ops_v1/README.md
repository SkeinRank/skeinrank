# Platform Ops Benchmark v1

Synthetic headless benchmark for the governed agent proposal workflow.

The benchmark is deterministic and does not call OpenRouter or Elasticsearch in the default local flow. It exists to keep the proposal, validation, approval, runtime query, and reporting contracts stable as the project evolves.

## What the benchmark covers

The fixture includes:

- incidents, runbooks, support tickets, and noisy documents;
- known aliases that should remain idempotent (`k8s`, `kube`, `postgres`, `elastic`);
- new agent-discovered aliases such as `rmq`, `otel`, `pg`, `prom`, `svc`, `redis-sentinel`, `redis-cluster`, `slo`, and `es`;
- profile stop-list collisions such as `app`, `error`, `job`, and `api`;
- unchanged-document skip behavior;
- changed-document revisit behavior;
- warning-level proposals such as low-confidence `pg`;
- golden runtime queries after proposals are applied;
- quality thresholds and regression reports;
- proposal-quality metrics for submission, approval, evidence coverage, alias classes, outcomes, and per-alias debugging;
- diagnostic rows explaining scan/skip decisions, candidate outcomes, validator reasons, and missing-alias explanations;
- a 500-document corpus manifest with semantic noise, near duplicates, labeled hard negatives, and weak platform-adjacent rows.

## Run the benchmark

From the repository root:

```bash
make benchmark-reset
make benchmark-seed
make benchmark-eval
make benchmark-report
make benchmark-clean
```

Use the containerized integration layer when you want PostgreSQL, Governance API, and Elasticsearch involved:

```bash
make benchmark-stack-run
```

## Retrieval evaluation baseline

The retrieval fixture files are:

```text
retrieval_queries.jsonl
qrels.jsonl
hard_negatives.jsonl
corpus_manifest.json
```

Run retrieval evaluation from the repository root:

```bash
make benchmark-retrieval-eval
make benchmark-retrieval-report
make benchmark-retrieval-compare
make benchmark-retrieval-compare-report
```

The retrieval report compares a literal baseline against a SkeinRank-expanded run with:

- `NDCG@10`
- `MRR@10`
- `Recall@10`
- `Precision@10`
- `hard_negative_leakage@10`
- `generic_token_noise@10`
- per-query deltas

The comparison report uses schema `skeinrank.retrieval_comparison_report.v1` and summarizes the largest improvements, regressions, high hard-negative leakage, generic-token noise, zero-recall queries, and operator-facing recommendations.

## Larger synthetic smoke data

Use the synthetic generator to exercise batch/report plumbing and larger-corpus handling before cost, latency, and throughput reporting.

```bash
make benchmark-smoke-plan
make benchmark-smoke-generate
make benchmark-smoke-report
make benchmark-smoke-clean
```

Default generated files are ignored local artifacts:

```text
examples/benchmarks/platform_ops_v1/reports/synthetic/platform_ops_v1-5k-corpus.jsonl
examples/benchmarks/platform_ops_v1/reports/synthetic/platform_ops_v1-5k-manifest.json
```

The committed 500-document quality corpus remains the primary regression fixture. The generated 5k corpus is for smoke and scale-shape checks, not complete relevance labeling.

## Cost, latency, and throughput report

The provider-independent performance report reads the synthetic manifest, optional live-pilot usage JSON, and an explicit elapsed-time value.

```bash
make benchmark-performance-plan
make benchmark-performance-report
make benchmark-performance-show
make benchmark-performance-clean
```

The report uses schema `skeinrank.benchmark_performance_report.v1` and summarizes documents/minute, seconds/document, batch latency, tokens, cost, skipped/unchanged documents, cache/idempotency savings, and a simple 100k-document projection.

It is an offline estimate and does not call OpenRouter, Elasticsearch, the database, or runtime mutation APIs.
