# Support bundle: logs, config, health, and last runs

This guide extends the sanitized first-company pilot support bundle into a production-oriented operator artifact.

The bundle remains read-only. It does not send webhooks, call OpenRouter, call Elasticsearch, mutate the database, apply proposals, or publish snapshots. It collects local files and optional HTTP snapshots only when an operator explicitly passes a Governance API URL.

## Generate a bundle

From the repository root:

```bash
make support-bundle-plan
make support-bundle-export
make support-bundle-inspect
```

The default output is ignored by git:

```text
examples/pilots/reports/skeinrank-troubleshooting-bundle.zip
```

## Include API health snapshots

To include read-only health/degraded-state snapshots, run the API separately and pass the URL:

```bash
SUPPORT_BUNDLE_API_URL=http://127.0.0.1:8010 \
make support-bundle-export
```

When auth is enabled, pass a read-only operator token with `ops:reports:read` and `agent:runs:read` scopes:

```bash
SUPPORT_BUNDLE_API_URL=http://127.0.0.1:8010 \
SUPPORT_BUNDLE_API_TOKEN="$ADMIN_OR_OPERATOR_TOKEN" \
make support-bundle-export
```

The token is used only as an Authorization header for read-only snapshots and is not written into the bundle.

## What the ZIP contains

Start with these files inside the ZIP:

```text
manifest.json
health/health_summary.json
runs/last_agent_runs.json
logs/log_inventory.json
config/config_inventory.json
api/api_snapshots.json
env/redacted_environment.json
system/runtime_metadata.json
commands/replay_commands.txt
```

### Health summary

`health/health_summary.json` summarizes optional API snapshots such as:

```text
/livez
/readyz
/schema/health
/v1/ops/troubleshooting/report
/v1/ops/alerts/report
/v1/governance/isolation-checks
/v1/agents/runs?limit=10
```

If a snapshot is degraded, unavailable, or returns an HTTP error, the summary marks the endpoint as degraded.

### Last runs

`runs/last_agent_runs.json` is a sanitized summary derived from:

```text
GET /v1/agents/runs?limit=10
```

It keeps only operational metadata: run id, agent name, status, profile, binding id, timestamps, artifact/report URI. It intentionally does not copy raw prompts, provider keys, or full LLM payloads.

### Logs

`logs/log_inventory.json` lists discovered `.log` files and indicates whether the bundled copy was truncated. Log files are redacted before they are written to the ZIP. Large logs include only the tail up to the configured limit.

### Config

`config/config_inventory.json` lists selected deployment/config files such as `docker-compose*.yml`, `deploy/docker/*.env.example`, `Makefile`, and package metadata. Raw `.env` files are intentionally excluded.

## Safety expectations

A generated support bundle should report:

```json
{
  "openrouter_calls": false,
  "elasticsearch_calls": false,
  "database_calls": false,
  "runtime_mutation_enabled": false,
  "raw_secrets_included": false
}
```

If the API snapshots show degraded state, attach this bundle together with the alerting report when escalating an operator issue.
