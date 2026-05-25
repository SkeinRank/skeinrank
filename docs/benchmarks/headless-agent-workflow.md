# Headless agent workflow benchmark

Patch 48A adds a deterministic benchmark for the governed agent proposal workflow.
It is designed to answer a different question than ordinary unit tests:

```text
Did the headless agent workflow become better, worse, or noisier over time?
```

The benchmark is intentionally offline. It does not call OpenRouter and it does
not require Elasticsearch. It uses a dry-run binding as the runtime context and
exercises the database-backed governance workflow end to end.

## What it covers

The default fixture lives in `examples/benchmarks/platform_ops_v1` and includes:

- a seed dictionary for `platform_ops_benchmark`;
- synthetic platform operations documents;
- previously seen unchanged documents;
- changed documents that must be revisited;
- new aliases such as `rmq`, `otel`, and `pg`;
- an idempotent existing alias case for `kube`;
- a stop-list blocked noisy alias case for `app`;
- golden runtime queries after proposals are applied.

The workflow is:

```text
seed dictionary
→ create dry-run binding
→ create prior run visits
→ create current benchmark run
→ record document visits
→ record candidate observations and evidence windows
→ record deterministic LLM reviews
→ record proposal attempts
→ create governed suggestions
→ approve/apply safe proposals
→ publish binding runtime snapshot
→ evaluate golden runtime queries
→ write JSON report
```

## Commands

Run from the repository root:

```bash
make benchmark-reset
make benchmark-seed
make benchmark-eval
make benchmark-report
make benchmark-clean
```

The default benchmark DB is the package-local SQLite database used by the
governance API CLI. Override it when you want an isolated run:

```bash
make benchmark-seed BENCHMARK_DATABASE_URL=sqlite:////tmp/skeinrank-benchmark.db
make benchmark-eval BENCHMARK_DATABASE_URL=sqlite:////tmp/skeinrank-benchmark.db
```

Direct CLI usage is also available:

```bash
cd packages/skeinrank-governance-api
poetry run python -m skeinrank_governance_api.benchmark seed --reset
poetry run python -m skeinrank_governance_api.benchmark eval \
  --out ../../examples/benchmarks/platform_ops_v1/reports/platform_ops_v1-report.json
poetry run python -m skeinrank_governance_api.benchmark report \
  --file ../../examples/benchmarks/platform_ops_v1/reports/platform_ops_v1-report.json
```

The Poetry script name is:

```bash
poetry run skeinrank-governance-benchmark seed --reset
```

## Report signals

The report schema is `skeinrank.benchmark_report.v1`. Important fields:

- `status` — `passed` or `failed`;
- `scores.expected_alias_recall` — whether expected aliases reached runtime;
- `scores.runtime_canonicalization_accuracy` — golden query match accuracy;
- `scores.unexpected_proposals` — number of unexpected proposal aliases;
- `counts.visit_statuses` — document visit decisions such as `unchanged_seen`;
- `counts.idempotent_noops` — existing aliases correctly treated as no-ops;
- `checks[]` — named pass/fail checks with details.

A successful report should show:

```text
expected_alias_recall = 1.0
runtime_canonicalization_accuracy = 1.0
unexpected_proposals = 0
```

## Why OpenRouter is not used here

48A is the stable CI/local layer. It proves the backend contract and lifecycle
without external latency, cost, or nondeterministic model output.

Live OpenRouter execution belongs in the next layer:

```text
48B — OpenRouter live agent pilot mode
```

That mode should stay opt-in, cost-bounded, and dry-run by default.
