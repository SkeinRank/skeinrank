# Cost, latency, and throughput report

Patch 53C adds an offline performance report for the `platform_ops_v1` benchmark
family. It combines the generated 5k synthetic smoke manifest with optional
OpenRouter live-pilot usage JSON and an explicit elapsed-time value to estimate
operator-facing cost, latency, throughput, savings, and simple scale projection
numbers.

This report is intentionally an **offline estimate**. It does not claim to be a
real production worker measurement unless you pass elapsed time and usage from a
real run. Use it as a stable report format before wiring long-running worker
measurements in later patches.

## What it reports

Schema:

```text
skeinrank.benchmark_performance_report.v1
```

The report includes:

```text
workload.documents_total
workload.processed_documents
workload.failed_documents
workload.retried_documents
latency.documents_per_minute
latency.seconds_per_document
latency.average_batch_latency_seconds
usage.llm_calls
usage.total_tokens
usage.estimated_cost_usd
unit_costs.cost_per_1k_documents_usd
unit_costs.tokens_per_document
savings.skipped_unchanged_documents
savings.cache_hits
savings.idempotent_existing_aliases
projection.estimated_elapsed_minutes
projection.estimated_cost_usd
recommendations[]
```

## Commands

Run from the repository root after generating the 5k synthetic smoke manifest:

```bash
make benchmark-smoke-generate
make benchmark-performance-plan
make benchmark-performance-report
make benchmark-performance-show
make benchmark-performance-clean
```

Default report path:

```text
examples/benchmarks/platform_ops_v1/reports/platform_ops_v1-cost-latency-throughput-report.json
```

The report is a generated local artifact under `examples/benchmarks/platform_ops_v1/reports/`
and should not be committed.

## Passing live usage

If you have an ignored OpenRouter live-pilot report, pass it through the Makefile:

```bash
BENCHMARK_PERFORMANCE_LIVE_REPORT=examples/agents/openrouter_alias_scout/reports/live-pilot/openrouter-live-pilot-report-3candidates.json \
BENCHMARK_PERFORMANCE_ELAPSED_SECONDS=250 \
make benchmark-performance-report
```

Or use the direct CLI:

```bash
cd packages/skeinrank-governance-api
poetry run python -m skeinrank_governance_api.benchmark_performance report \
  --synthetic-manifest ../../examples/benchmarks/platform_ops_v1/reports/synthetic/platform_ops_v1-5k-manifest.json \
  --live-report ../../examples/agents/openrouter_alias_scout/reports/live-pilot/openrouter-live-pilot-report-3candidates.json \
  --elapsed-seconds 250 \
  --out ../../examples/benchmarks/platform_ops_v1/reports/platform_ops_v1-cost-latency-throughput-report.json
```

Poetry script:

```bash
poetry run skeinrank-governance-benchmark-performance report \
  --synthetic-manifest ../../examples/benchmarks/platform_ops_v1/reports/synthetic/platform_ops_v1-5k-manifest.json \
  --elapsed-seconds 250
```

## Manual usage override

When you do not have a live-pilot report, provide explicit usage values:

```bash
poetry run python -m skeinrank_governance_api.benchmark_performance report \
  --synthetic-manifest ../../examples/benchmarks/platform_ops_v1/reports/synthetic/platform_ops_v1-5k-manifest.json \
  --elapsed-seconds 300 \
  --llm-calls 10 \
  --prompt-tokens 12000 \
  --completion-tokens 1200 \
  --estimated-cost-usd 0.02
```

## Safety

This report builder is fully offline:

```text
OpenRouter calls: false
Elasticsearch calls: false
database calls: false
runtime mutation: false
```

It reads JSON files and writes a local report only. It does not submit proposals,
approve/apply changes, publish snapshots, call LLM providers, call Elasticsearch,
or touch the governance database.

## Why this is separate from 53B

Patch 53B generates a stable 5k corpus shape and manifest. Patch 53C turns that
manifest plus optional usage/timing inputs into an operator-facing report that
answers practical pilot questions:

```text
How many docs/min can this run handle?
How much model usage did the run consume?
How much did skip/cache/idempotency save?
What would a 100k-document run roughly cost/take if scaled linearly?
```
