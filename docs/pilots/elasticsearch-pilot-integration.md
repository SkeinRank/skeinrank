# Elasticsearch pilot integration path

Patch 49E adds a repeatable first-company pilot path for teams that already have
an Elasticsearch/OpenSearch index and want to try SkeinRank without committing to
a production rollout.

The flow is intentionally conservative:

```bash
make pilot-plan
make pilot-preflight
make pilot-seed
make pilot-eval
make pilot-report
```

Or run everything in one step:

```bash
make pilot-run
```

The report schema is `skeinrank.pilot.integration_report.v1`.

## What it does

The pilot CLI reads a JSON config such as
`examples/pilots/elasticsearch_pilot.example.json` and then:

1. checks `/healthz`, `/schema/health`, and Elasticsearch connection status;
2. verifies that the configured index mapping contains the expected text fields;
3. validates and imports the seed dictionary through `/v1/console/dictionary/*`;
4. creates or reuses an Elasticsearch binding in `dry_run` mode;
5. runs bounded evidence checks through `/v1/governance/elasticsearch/bindings/{binding_id}/evidence`;
6. runs query-plan checks through `/v1/query/plan`;
7. writes a JSON report for reviewers.

No OpenRouter calls are made by this flow. Proposal submission, approve/apply,
snapshot publish, and Elasticsearch writes are not performed.

## Config

Copy the example and edit it for the target company index:

```bash
cp examples/pilots/elasticsearch_pilot.example.json /tmp/skeinrank-pilot.json
# Absolute paths such as /tmp/skeinrank-pilot.json are supported by Makefile targets.
```

Update at least:

```json
{
  "dictionary": {
    "profile_name": "company_platform_ops",
    "terms": []
  },
  "binding": {
    "index_name": "your-existing-index",
    "text_fields": ["title", "body"],
    "target_field": "skeinrank_terms"
  }
}
```

Then run:

```bash
make pilot-plan PILOT_CONFIG=/tmp/skeinrank-pilot.json
make pilot-preflight PILOT_CONFIG=/tmp/skeinrank-pilot.json
make pilot-seed PILOT_CONFIG=/tmp/skeinrank-pilot.json
make pilot-eval PILOT_CONFIG=/tmp/skeinrank-pilot.json
make pilot-report PILOT_CONFIG=/tmp/skeinrank-pilot.json
```

## Auth

When auth is disabled locally, no extra flags are needed. When auth is enabled,
use either a bearer token:

```bash
make pilot-run \
  PILOT_CONFIG=/tmp/skeinrank-pilot.json \
  PILOT_AUTH_ARGS='--token sk_pat_...'
```

or a short-lived admin login token created by username/password:

```bash
make pilot-run \
  PILOT_CONFIG=/tmp/skeinrank-pilot.json \
  PILOT_AUTH_ARGS='--username admin --password change-me'
```

Do not commit real tokens or company credentials.

## Local stack smoke

For local development, the example config can be exercised against the benchmark
stack after the benchmark corpus is indexed:

```bash
make pilot-stack-run
```

This target starts the isolated benchmark Compose project, seeds the
`platform_ops_v1` Elasticsearch index, then runs the pilot config against the
local Governance API.

## Expected report shape

A successful report includes:

```json
{
  "schema_version": "skeinrank.pilot.integration_report.v1",
  "status": "passed",
  "checks_failed": 0,
  "evidence_checks": [],
  "runtime_checks": [],
  "safety": {
    "openrouter_calls": false,
    "proposal_submit_enabled": false,
    "approve_apply_enabled": false,
    "runtime_mutation_enabled": false,
    "elasticsearch_write_enabled": false
  }
}
```

## Troubleshooting

If preflight fails with missing text fields, update `binding.text_fields` to use
fields that exist in the index mapping.

If the dictionary import fails, run the same payload through the dictionary
validator and inspect the reported conflicts:

```bash
cd packages/skeinrank-governance-api
poetry run skeinrank-governance-pilot preflight \
  --config ../../examples/pilots/elasticsearch_pilot.example.json
```

If `pilot-eval` says the binding was not found, run `make pilot-seed` first. The
seed command is idempotent: it reuses an existing binding when the binding name
and index match.
