# Platform Ops Benchmark v1

Synthetic headless benchmark for the governed agent proposal workflow. Patch 49A expands it into a 50-document quality fixture; Patch 49B adds proposal-level quality metrics and per-alias outcome breakdowns.

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
- `agent_decision_diagnostics` rows explaining document scan/skip choices, candidate outcomes, validator reasons, and missing-alias explanations.

Run through the Makefile from the repository root:

```bash
make benchmark-reset
make benchmark-seed
make benchmark-eval
make benchmark-report
make benchmark-clean
```

The benchmark is deterministic and does not call OpenRouter or Elasticsearch. Use `make benchmark-stack-run` for the containerized PostgreSQL + Governance API + Elasticsearch integration layer.
