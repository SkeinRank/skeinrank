# Enrichment pause/resume examples

These examples show request bodies for Patch 61C pause/resume operations.
They use existing governance API endpoints and do not define a separate worker
protocol.

## Pause

```bash
curl -X POST "http://127.0.0.1:8010/v1/governance/elasticsearch/jobs/123/pause" \
  -H "Content-Type: application/json" \
  -H "X-SkeinRank-Role: admin" \
  --data @examples/enrichment-pause-resume/pause-request.json
```

## Resume

```bash
curl -X POST "http://127.0.0.1:8010/v1/governance/elasticsearch/jobs/123/resume" \
  -H "Content-Type: application/json" \
  -H "X-SkeinRank-Role: admin" \
  --data @examples/enrichment-pause-resume/resume-request.json
```

Inspect the checkpoint with:

```bash
curl "http://127.0.0.1:8010/v1/governance/elasticsearch/jobs/123" \
  -H "X-SkeinRank-Role: admin"
```

Look at `result_json.chunked_enrichment.checkpoint`.
