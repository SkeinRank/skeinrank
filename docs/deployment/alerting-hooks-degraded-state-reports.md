# Alerting hooks and degraded-state reports

Patch 56A adds a read-only alerting layer for operator workflows.

The goal is to convert existing health, troubleshooting, and profile-isolation
signals into a compact degraded-state report that can be copied into an
incident, attached to a support bundle, or passed to an external notification
system.

## HTTP report

```http
GET /v1/ops/alerts/report
```

The response schema is:

```text
skeinrank.alerting_report.v1
```

The endpoint collects:

- `GET /v1/ops/troubleshooting/report` style checks internally;
- profile/binding isolation state from `GET /v1/governance/isolation-checks` logic;
- degraded database/schema/search/observability/profile-isolation signals;
- a sanitized `webhook_json` payload preview.

The endpoint does **not** send webhooks. It only renders the payload that an
operator, CI job, or future integration can deliver explicitly.

## CLI report

```bash
cd packages/skeinrank-governance-api
poetry run python -m skeinrank_governance_api.alerting plan
```

Generate an offline report from saved JSON inputs:

```bash
poetry run python -m skeinrank_governance_api.alerting report \
  --troubleshooting-report /tmp/troubleshooting.json \
  --isolation-report /tmp/isolation.json \
  --environment pilot \
  --out /tmp/skeinrank-alerting-report.json
```

Show a saved report:

```bash
poetry run python -m skeinrank_governance_api.alerting show \
  --file /tmp/skeinrank-alerting-report.json
```

The Poetry script name is:

```bash
poetry run skeinrank-governance-alerting plan
```

## Makefile helpers

From the repository root:

```bash
make alerts-report-plan
make alerts-report-generate
make alerts-report-show
```

Optional saved input files:

```bash
ALERTING_TROUBLESHOOTING_REPORT=examples/pilots/reports/troubleshooting.json \
ALERTING_ISOLATION_REPORT=examples/pilots/reports/isolation.json \
ALERTING_ENVIRONMENT=pilot \
make alerts-report-generate
```

The default generated report is:

```text
examples/pilots/reports/skeinrank-alerting-report.json
```

This path is ignored by git together with other pilot reports.

## Severity mapping

The initial severity rules are intentionally conservative:

| Source | Condition | Severity |
|---|---:|---|
| database | degraded | critical |
| schema | degraded | critical |
| Elasticsearch/OpenSearch | degraded | warning |
| observability | degraded/unknown | warning |
| profile isolation | high/critical sampled issue | critical |
| profile isolation | other failed check | warning |

`not_configured` Elasticsearch is not treated as a degraded alert because many
offline pilots intentionally run without Elasticsearch.

## Safety

The report is read-only:

```json
{
  "read_only": true,
  "database_mutation_enabled": false,
  "runtime_mutation_enabled": false,
  "openrouter_calls": false,
  "elasticsearch_calls": false,
  "webhook_delivery_enabled": false,
  "secrets_included": false
}
```

The generated hook payload is a preview only. No Slack, PagerDuty, webhook, email,
OpenRouter, Elasticsearch, proposal apply, or snapshot publish call is performed.

## Pilot usage

Before a first-company pilot checkpoint:

```bash
curl http://127.0.0.1:8010/v1/ops/alerts/report | python -m json.tool
```

If the report is `degraded`, attach it together with:

```bash
make support-bundle-export
make support-bundle-inspect
```

Do not enable autonomous apply or unattended publish while critical alert events
are present.
