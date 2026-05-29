# Pause/resume operator checklist

1. Confirm the job uses the Celery backend.
2. Inspect current job status with `GET /v1/governance/elasticsearch/jobs/{job_id}`.
3. Pause only `queued` or `running` jobs.
4. Wait for `paused` before draining workers or ending the maintenance window.
5. Review `result_json.chunked_enrichment.checkpoint`.
6. Resume only after workers and Elasticsearch are healthy.
7. Confirm remaining chunks were requeued under `resumed_chunks`.
8. After success, review counters and rollout metadata before cleanup.
