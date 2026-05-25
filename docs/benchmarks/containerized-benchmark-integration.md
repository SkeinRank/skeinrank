# Containerized benchmark integration harness

Patch 48C adds a full-stack benchmark harness for the existing `platform_ops_v1`
fixture. It answers a different question than the deterministic 48A benchmark:

```text
Can the benchmark workflow run against the Docker Compose stack with
PostgreSQL, Governance API, and Elasticsearch evidence checks?
```

The harness still does **not** call OpenRouter. It uses the deterministic 48A
agent workflow, but runs it against the containerized PostgreSQL database and
checks HTTP endpoints plus Elasticsearch evidence retrieval.

## Stack flow

From the repository root:

```bash
make benchmark-stack-prune-containers
make benchmark-stack-up
make benchmark-stack-wait
make benchmark-stack-reset
make benchmark-stack-seed
make benchmark-stack-eval
make benchmark-stack-report
make benchmark-stack-clean
make benchmark-stack-down
```

The shorthand flow is:

```bash
make benchmark-stack-run
```

`benchmark-stack-run` starts the stack, waits for API/Elasticsearch, resets old
benchmark state, seeds the DB and Elasticsearch index, evaluates the benchmark,
and prints the stack report. It does not stop the stack automatically so that you
can inspect logs and endpoints afterwards.

## What it starts

The target uses the development Compose stack and starts only the services needed
for the integration benchmark:

```text
postgres
rabbitmq
elasticsearch
governance-migrate
governance-api
```

The UI and worker are not required for this benchmark.

## What it verifies

The stack report schema is `skeinrank.benchmark_stack_report.v1`. It includes:

- the base deterministic 48A benchmark scores;
- `/healthz` API check;
- `/schema/health` Alembic/schema check;
- `/metrics` availability check;
- Elasticsearch corpus index count check;
- Elasticsearch evidence endpoint checks for expected aliases;
- HTTP `/v1/query/plan` checks for golden runtime queries.

A passing run should show the base scores:

```text
expected_alias_recall = 1.0
runtime_canonicalization_accuracy = 1.0
unexpected_proposals = 0
unchanged_skip_rate = 1.0
```

and all stack checks should have `status = passed`.

## Defaults

The Makefile defaults match `docker-compose.dev.yml`:

```text
BENCHMARK_STACK_DATABASE_URL=postgresql+psycopg://app_user:skeinrank_dev_password@127.0.0.1:15432/app_db
BENCHMARK_STACK_API_URL=http://127.0.0.1:8010
BENCHMARK_STACK_ES_URL=http://127.0.0.1:19200
BENCHMARK_STACK_ADMIN_USERNAME=admin
BENCHMARK_STACK_ADMIN_PASSWORD=change-me
```

Override these when using custom ports or credentials:

```bash
make benchmark-stack-eval \
  BENCHMARK_STACK_DATABASE_URL='postgresql+psycopg://app_user:secret@127.0.0.1:15432/app_db' \
  BENCHMARK_STACK_API_URL='http://127.0.0.1:8010' \
  BENCHMARK_STACK_ES_URL='http://127.0.0.1:19200'
```

## Direct CLI

The direct CLI is useful for scripts and CI jobs:

```bash
cd packages/skeinrank-governance-api
poetry run python -m skeinrank_governance_api.benchmark_stack wait
poetry run python -m skeinrank_governance_api.benchmark_stack seed --reset
poetry run python -m skeinrank_governance_api.benchmark_stack eval \
  --out ../../examples/benchmarks/platform_ops_v1/reports/platform_ops_v1-stack-report.json
poetry run python -m skeinrank_governance_api.benchmark_stack report \
  --file ../../examples/benchmarks/platform_ops_v1/reports/platform_ops_v1-stack-report.json
```

The Poetry script alias is:

```bash
poetry run skeinrank-governance-benchmark-stack eval
```

## Reset and cleanup

Use:

```bash
make benchmark-stack-clean
```

This removes the generated stack report, deletes the benchmark-owned profile from
the governance DB, and deletes the benchmark Elasticsearch index.

Use:

```bash
make benchmark-stack-down
```

when you want to stop the Compose stack. It does not pass `-v`, so Docker volumes
are preserved unless you remove them explicitly.

## Relationship to 48A and 48B

```text
48A = deterministic in-process benchmark
48B = guarded OpenRouter live pilot
48C = Docker Compose + DB + API + Elasticsearch integration benchmark
```

Run 48A first when you want a fast local regression check. Run 48C when you want
to prove that the same workflow works through the containerized stack and evidence
surfaces.


### Benchmark stack troubleshooting

If `benchmark-stack-up` reports a Docker container name conflict for `skeinrank-*-dev`, the stack target now prunes the fixed dev-stack benchmark containers before startup:

```bash
make benchmark-stack-prune-containers
make benchmark-stack-up
```

The prune step removes containers only; named volumes are not deleted. Use `docker compose -f docker-compose.dev.yml down -v` only when you intentionally want to remove persisted dev volumes.

The stack benchmark connects to PostgreSQL from the local Poetry environment, so run `cd packages/skeinrank-governance-api && poetry install` after applying dependency changes.

## Isolation and stale Docker state

The stack uses a deterministic benchmark Compose environment file:

```text
deploy/docker/benchmark.env.example
```

The Makefile forces a dedicated Compose project name (`skeinrank-benchmark`) and fixed local credentials for the benchmark stack. This avoids accidental reuse of production `.env` values.

If Postgres reports `password authentication failed`, an old Docker volume was probably created with different `POSTGRES_*` values. Run:

```bash
make benchmark-stack-prune-containers
make benchmark-stack-up
```

`benchmark-stack-prune-containers` removes the benchmark containers and benchmark volumes, so it is destructive for the local benchmark stack by design.

If `/healthz` briefly closes the connection during startup, `benchmark-stack-wait` retries until the API and Elasticsearch are ready.
