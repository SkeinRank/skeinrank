# Platform Ops Benchmark v1

Synthetic headless benchmark for the governed agent proposal workflow. Patch 49A expands it into a 50-document quality fixture; Patch 49B adds proposal-level quality metrics and per-alias outcome breakdowns; Patch 53A expands the default fixture to a 500-document small-pilot corpus; Patch 53B adds a deterministic 5k synthetic smoke generator that writes local artifacts under `reports/synthetic/`.

It intentionally includes:

- incidents, runbooks, support tickets, and noisy docs;
- seeded aliases that should remain idempotent (`k8s`, `kube`, `postgres`, `elastic`);
- new agent-discovered aliases (`rmq`, `otel`, `pg`, `prom`, `lk`, `ns`, `svc`, `redis-sentinel`, `redis-cluster`, `slo`, `es`);
- profile stop-list collisions (`app`, `error`, `job`, `api`);
- unchanged document skip behavior;
- changed document revisit behavior;
- warning-level proposals such as low-confidence `pg`;
- golden runtime queries after proposals are applied;
- quality thresholds and a quality report for regression tracking;
- `proposal_quality` metrics for submission/approval rates, evidence coverage, alias classes, outcomes, and per-alias debugging rows.
- `agent_decision_diagnostics` rows explaining document scan/skip choices, candidate outcomes, validator reasons, and missing-alias explanations;
- a 53A 500-document corpus manifest with semantic noise, near duplicates, labeled hard negatives, and weak platform-adjacent rows.

Run through the Makefile from the repository root:

```bash
make benchmark-reset
make benchmark-seed
make benchmark-eval
make benchmark-report
make benchmark-clean
```

The benchmark is deterministic and does not call OpenRouter or Elasticsearch. Use `make benchmark-stack-run` for the containerized PostgreSQL + Governance API + Elasticsearch integration layer.


## Retrieval eval baseline

Patch 50A adds retrieval fixtures, Patch 50B expands them to a 200-document corpus with hard negatives, Patch 50B.1 adds query-hygiene scoring for hard-negative tuning, Patch 50C adds a retrieval comparison report for pilot/company index diagnostics, and Patch 53A expands the corpus to 500 documents:

```text
retrieval_queries.jsonl
qrels.jsonl
hard_negatives.jsonl
corpus_manifest.json
```

Run from the repository root:

```bash
make benchmark-retrieval-eval
make benchmark-retrieval-report
make benchmark-retrieval-compare
make benchmark-retrieval-compare-report
```

The retrieval report compares a literal baseline against a SkeinRank-expanded run with `NDCG@10`, `MRR@10`, `Recall@10`, `Precision@10`, `hard_negative_leakage@10`, `generic_token_noise@10`, and per-query deltas.


The comparison report uses schema `skeinrank.retrieval_comparison_report.v1` and summarizes largest improvements, regressions, high hard-negative leakage, generic-token noise, zero-recall queries, and operator-facing recommendations.


## 5k synthetic smoke generator

Patch 53B adds an offline generator for larger scale-smoke artifacts. It does not replace the committed 500-document quality corpus and does not label all 5,000 generated rows. Use it to test batch/report plumbing and larger-corpus handling before cost/latency/throughput reporting.

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
