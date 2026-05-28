# First company pilot runbook

Patch 54A turns the benchmark and pilot pieces into a repeatable first-company
pilot path. Use this runbook when a team already has a small Elasticsearch or
OpenSearch index and wants to check whether SkeinRank can improve terminology
normalization, evidence discovery, and runtime query planning before any
production rollout.

The runbook is intentionally conservative. The default path imports a small seed
dictionary and creates a dry-run binding, then performs read-only evidence and
runtime checks. It does **not** call OpenRouter, submit proposals, approve/apply
changes, publish snapshots, or write enriched fields back to Elasticsearch.

## Pilot objective

The first pilot should answer six practical questions:

```text
1. Can the company index be reached from the Governance API?
2. Do the selected text fields exist and contain useful terminology evidence?
3. Can a small dictionary/profile be imported safely?
4. Can a dry-run binding connect the profile to the index/search context?
5. Do evidence checks find real documents for important aliases?
6. Do runtime query-plan checks return the expected canonical values?
```

A successful pilot produces an operator-facing JSON report with schema:

```text
skeinrank.pilot.integration_report.v1
```

## Safety boundaries

Default 54A pilot boundaries:

```text
OpenRouter calls: false
proposal submission: false
approve/apply: false
snapshot publishing: false
Elasticsearch writes: false
runtime mutation after seed: false
```

The only mutating step in the default flow is `pilot-seed`, which imports the
pilot dictionary into the governance database and creates or reuses a dry-run
binding. `pilot-eval` is read-only.

## Inputs to collect before the pilot

Collect these from the company team before editing the config:

```text
pilot owner / reviewer
Elasticsearch or OpenSearch URL
index or alias name
text fields to inspect, for example title/body/content/message
optional filter field/value, for example team=infra or workspace_id=...
target field for future enrichment, for example skeinrank_terms
5-20 initial canonical terms
known aliases/acronyms for those terms
2-5 evidence checks
2-5 runtime queries with expected canonical values
```

Do not put real credentials, tokens, or company data into committed files. Keep
company-specific configs under `/tmp`, an ignored local directory, or a private
ops repository.

## Phase 0 — Local benchmark rehearsal

Before touching a company index, verify that the local benchmark path still works
from the repository root:

```bash
make benchmark-retrieval-eval
make benchmark-retrieval-report
make benchmark-smoke-generate
make benchmark-performance-report
make benchmark-performance-show
```

This proves that the 500-document quality fixture, 5k synthetic smoke manifest,
and cost/latency/throughput report plumbing still work without OpenRouter,
Elasticsearch, database calls, or runtime mutation in the report builder.

For a full local stack rehearsal against PostgreSQL, Governance API, and
Elasticsearch, use:

```bash
make benchmark-stack-run
make pilot-stack-run
```

`pilot-stack-run` starts the benchmark stack, seeds the platform-ops fixture, and
runs the pilot config against the local API with benchmark credentials.

## Phase 1 — Prepare the company pilot config

Copy the example config to a local path:

```bash
cp examples/pilots/elasticsearch_pilot.example.json /tmp/skeinrank-company-pilot.json
```

Edit at least these fields:

```json
{
  "pilot_name": "company_platform_ops_pilot",
  "dictionary": {
    "profile_name": "company_platform_ops",
    "terms": []
  },
  "binding": {
    "name": "Company Platform Ops Docs",
    "index_name": "your-existing-index-or-alias",
    "text_fields": ["title", "body"],
    "target_field": "skeinrank_terms",
    "filter_field": null,
    "filter_value": null,
    "mode": "dry_run"
  },
  "evidence_checks": [],
  "runtime_queries": []
}
```

Keep `mode` as `dry_run` for the first pilot. Add `filter_field` and
`filter_value` when a shared index contains multiple teams, workspaces, or
document domains.

## Phase 2 — Start the API stack

For local development with Docker Compose, start the development stack and wait
until the API is healthy:

```bash
docker compose -f docker-compose.dev.yml up --build -d postgres rabbitmq elasticsearch governance-migrate governance-api
curl http://127.0.0.1:8010/livez | python -m json.tool
curl http://127.0.0.1:8010/schema/health | python -m json.tool
```

When auth is enabled, create a token with the configured admin account and pass
it through `PILOT_AUTH_ARGS`:

```bash
PILOT_AUTH_ARGS='--username admin --password change-me' \
make pilot-preflight PILOT_CONFIG=/tmp/skeinrank-company-pilot.json
```

Do not commit real passwords or bearer tokens.

## Phase 3 — Run the pilot flow

Run the plan first. It is offline and does not contact the API:

```bash
make pilot-plan PILOT_CONFIG=/tmp/skeinrank-company-pilot.json
```

Run preflight to check API/schema/Elasticsearch/index mapping:

```bash
make pilot-preflight PILOT_CONFIG=/tmp/skeinrank-company-pilot.json
```

If preflight passes, seed the pilot dictionary and dry-run binding:

```bash
make pilot-seed PILOT_CONFIG=/tmp/skeinrank-company-pilot.json
```

Then run read-only evidence and runtime query checks:

```bash
make pilot-eval PILOT_CONFIG=/tmp/skeinrank-company-pilot.json
make pilot-report PILOT_CONFIG=/tmp/skeinrank-company-pilot.json
```

Or run the full preflight/seed/eval flow in one command:

```bash
make pilot-run PILOT_CONFIG=/tmp/skeinrank-company-pilot.json
```

Generated pilot reports are local artifacts under `examples/pilots/reports/` by
default. Keep company reports out of public commits unless they are sanitized.

## Phase 4 — Interpret the report

A passing report should have:

```json
{
  "schema_version": "skeinrank.pilot.integration_report.v1",
  "status": "passed",
  "checks_failed": 0,
  "safety": {
    "openrouter_calls": false,
    "proposal_submit_enabled": false,
    "approve_apply_enabled": false,
    "runtime_mutation_enabled": false,
    "elasticsearch_write_enabled": false
  }
}
```

Review these sections with the company owner:

```text
evidence_checks[]  — did important aliases appear in the expected documents?
runtime_checks[]   — did query planning produce expected canonical values?
safety             — verify the pilot stayed read-only after seeding
checks_failed      — decide whether config, dictionary, or text fields need tuning
```

Common outcomes:

```text
Passed evidence + passed runtime checks
  The first pilot is healthy. Prepare a small reviewer demo.

Failed evidence checks
  Check text_fields, filter_field/filter_value, index alias, or evidence query names.

Failed runtime checks
  Add missing aliases/terms or tighten ambiguous short aliases before expanding scope.

Mapping preflight failed
  Update binding.text_fields to fields that exist in the index mapping.
```

## Phase 5 — Optional validated agent pilot

Only after the read-only pilot passes, a reviewer can run a guarded OpenRouter
validated pilot. Keep strict limits and use a seeded profile/binding context:

```bash
OPENROUTER_VALIDATED_PILOT_ARGS="--profile-name company_platform_ops --max-candidates 3 --max-llm-calls 3 --max-proposals 3 --max-run-cost-usd 0.03 --force-refresh-cache" \
make benchmark-agent-live-validated-pilot-report
```

This mode still does not approve/apply changes or publish snapshots. It validates
LLM-prepared proposals through the Governance API before any submission path is
considered. Use `read -s OPENROUTER_API_KEY` instead of typing tokens directly in
shell history.

## Phase 6 — Exit criteria

Do not move beyond the first pilot until all are true:

```text
preflight passed
pilot seed completed with the expected profile and binding
pilot report status passed, or failures are explained and accepted
no Elasticsearch writes were performed
no proposals were auto-applied
reviewer understands evidence and runtime query results
cost/latency estimate is documented if live agent usage was tested
next action is written down: tune dictionary, add evidence checks, or plan 54B
```

## Troubleshooting

If the API is not reachable:

```bash
curl http://127.0.0.1:8010/livez | python -m json.tool
make benchmark-stack-wait
```

If schema health fails:

```bash
cd packages/skeinrank-governance-api
poetry run python -m skeinrank_governance_api.migrations check
```

If the pilot binding is missing during `pilot-eval`, run:

```bash
make pilot-seed PILOT_CONFIG=/tmp/skeinrank-company-pilot.json
```

If OpenRouter validated pilot fails before model calls with `Profile not found`,
seed the benchmark stack or pass a profile/binding that exists in the currently
running Governance API database.

## Related docs

- `docs/pilots/elasticsearch-pilot-integration.md`
- `docs/benchmarks/containerized-benchmark-integration.md`
- `docs/benchmarks/retrieval-eval-baseline.md`
- `docs/benchmarks/synthetic-smoke-generator.md`
- `docs/benchmarks/cost-latency-throughput-report.md`
- `docs/benchmarks/openrouter-live-pilot.md`
