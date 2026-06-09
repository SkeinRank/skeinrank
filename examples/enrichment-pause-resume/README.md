# Enrichment pause/resume examples

These examples show request bodies for pausing and resuming operator-controlled search delivery jobs.

They use the existing Governance API job endpoints and do not define a separate worker protocol. The workflow is intended for jobs that already passed preflight and were started through the explicit admin/API/runbook flow.

## Pause a job

```bash
curl -X POST "http://127.0.0.1:8010/v1/governance/elasticsearch/jobs/123/pause" \
  -H "Content-Type: application/json" \
  -H "X-SkeinRank-Role: admin" \
  --data @examples/enrichment-pause-resume/pause-request.json
```

## Resume a job

```bash
curl -X POST "http://127.0.0.1:8010/v1/governance/elasticsearch/jobs/123/resume" \
  -H "Content-Type: application/json" \
  -H "X-SkeinRank-Role: admin" \
  --data @examples/enrichment-pause-resume/resume-request.json
```

## Inspect checkpoint state

```bash
curl "http://127.0.0.1:8010/v1/governance/elasticsearch/jobs/123" \
  -H "X-SkeinRank-Role: admin"
```

Look at:

```text
result_json.chunked_enrichment.checkpoint
```

The checkpoint helps operators confirm what was processed before a pause, resume, cancel, or rollback decision.
