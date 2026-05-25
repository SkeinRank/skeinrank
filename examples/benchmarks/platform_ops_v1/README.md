# Platform Ops Benchmark v1

Synthetic headless benchmark for the governed agent proposal workflow. Patch 49A expands it into a 50-document quality fixture.

It intentionally includes:

- incidents, runbooks, support tickets, and noisy docs;
- seeded aliases that should remain idempotent (`k8s`, `kube`, `postgres`, `elastic`);
- new agent-discovered aliases (`rmq`, `otel`, `pg`, `prom`, `lk`, `ns`, `svc`, `redis-sentinel`, `redis-cluster`, `slo`, `es`);
- profile stop-list collisions (`app`, `error`, `job`, `api`);
- unchanged document skip behavior;
- changed document revisit behavior;
- warning-level proposals such as low-confidence `pg`;
- golden runtime queries after proposals are applied;
- quality thresholds and a quality report for regression tracking.

Run through the Makefile from the repository root:

```bash
make benchmark-reset
make benchmark-seed
make benchmark-eval
make benchmark-report
make benchmark-clean
```

The benchmark is deterministic and does not call OpenRouter or Elasticsearch. Use `make benchmark-stack-run` for the containerized PostgreSQL + Governance API + Elasticsearch integration layer.
