# Patch 54B — Troubleshooting bundle export

Patch 54B adds a read-only support bundle exporter for first-company pilots.
The goal is to collect enough diagnostic context to debug a pilot without asking
an operator to copy dozens of logs, reports, configs, and health snapshots by
hand.

The exporter is intentionally conservative:

- OpenRouter calls: false
- Elasticsearch calls: false
- database calls: false
- proposal submission: false
- approve/apply: false
- snapshot publishing: false
- runtime mutation: false
- raw `.env` files: excluded
- secret-looking values: redacted

## Commands

From the repository root:

```bash
make support-bundle-plan
make support-bundle-export
make support-bundle-inspect
```

The default ZIP is written to:

```text
examples/pilots/reports/skeinrank-troubleshooting-bundle.zip
```

Generated pilot reports are ignored by git, so the ZIP is meant to be a local
support artifact, not a committed file.

## Optional API health snapshots

The exporter can optionally capture read-only HTTP health snapshots from a
running Governance API:

```bash
SUPPORT_BUNDLE_API_URL=http://127.0.0.1:8010 \
make support-bundle-export
```

If you have an ops token with `ops:reports:read`, you can also capture the
sanitized ops troubleshooting report:

```bash
SUPPORT_BUNDLE_API_URL=http://127.0.0.1:8010 \
SUPPORT_BUNDLE_API_TOKEN="$SKEINRANK_AGENT_API_TOKEN" \
make support-bundle-export
```

The token value is not written into the bundle.

## What is included

The ZIP contains:

```text
manifest.json
README.txt
commands/replay_commands.txt
env/redacted_environment.json
system/runtime_metadata.json
api/api_snapshots.json
files/...
```

The `files/` directory contains sanitized copies of relevant docs, example
configs, pilot reports, benchmark reports, agent reports, and benchmark manifests
when they exist locally.

Typical useful files:

```text
docs/pilots/first-company-pilot-runbook.md
examples/pilots/elasticsearch_pilot.example.json
examples/pilots/reports/pilot-integration-report.json
examples/benchmarks/platform_ops_v1/reports/platform_ops_v1-cost-latency-throughput-report.json
examples/agents/openrouter_alias_scout/reports/live-pilot/openrouter-live-pilot-report.json
```

Missing optional local reports are listed in `manifest.json` rather than causing
export failure.

## Secret handling

The bundle redacts common secret shapes and secret-looking keys:

```text
api_key
authorization
password
secret
token
credential
private_key
sk-or-v1-...
Authorization: Bearer ...
```

It also excludes raw `.env` files, SQLite/database files, Python bytecode, cache
folders, and `.git` internals.

## Direct CLI

The Make targets call the package CLI:

```bash
cd packages/skeinrank-governance-api
poetry run python -m skeinrank_governance_api.support_bundle plan --project-root ../..
poetry run python -m skeinrank_governance_api.support_bundle export --project-root ../..
poetry run python -m skeinrank_governance_api.support_bundle inspect --file ../../examples/pilots/reports/skeinrank-troubleshooting-bundle.zip
```

The installed console script is also available:

```bash
poetry run skeinrank-governance-support-bundle export --project-root ../..
```

## How to use in a pilot

1. Run the pilot or benchmark checks.
2. Export the bundle.
3. Inspect the manifest.
4. Share the ZIP privately with the operator/support reviewer.
5. Keep the ZIP out of public commits.

```bash
make pilot-run
make benchmark-performance-report
make support-bundle-export
make support-bundle-inspect
```

## Follow-up

Patch 54B is a local support bundle. A later production support bundle can add
container logs, API-authenticated recent run summaries, and stricter tenant/profile
isolation checks once the production deployment shape is finalized.
