# Pilot examples

`elasticsearch_pilot.example.json` is the 49E starter config for a controlled
first-company pilot.

Copy it outside the repository, adjust the target index, fields, seed dictionary,
evidence checks, and golden runtime queries, then run:

```bash
make pilot-plan PILOT_CONFIG=/tmp/skeinrank-pilot.json
make pilot-preflight PILOT_CONFIG=/tmp/skeinrank-pilot.json
make pilot-seed PILOT_CONFIG=/tmp/skeinrank-pilot.json
make pilot-eval PILOT_CONFIG=/tmp/skeinrank-pilot.json
make pilot-report PILOT_CONFIG=/tmp/skeinrank-pilot.json
```

The pilot path is intentionally safe: no OpenRouter calls, no proposal submit,
no approve/apply, no snapshot publish, and no Elasticsearch writes.
