# Platform Ops Benchmark v1

Synthetic headless benchmark for the governed agent proposal workflow.

It intentionally includes:

- seeded aliases that should remain idempotent (`k8s`, `kube`);
- new agent-discovered aliases (`rmq`, `otel`, `pg`);
- a profile stop-list collision (`app`);
- unchanged document skip behavior;
- changed document revisit behavior;
- golden runtime queries after proposals are applied.

Run through the Makefile from the repository root:

```bash
make benchmark-reset
make benchmark-seed
make benchmark-eval
make benchmark-report
make benchmark-clean
```

The benchmark is deterministic and does not call OpenRouter or Elasticsearch.
