# Patch 42B — Real Elasticsearch validation scenario

This directory contains a tiny deterministic fixture set for validating the OpenRouter alias scout against a real Elasticsearch/OpenSearch index.

The scenario is intentionally small:

- `documents.jsonl` — sample incident/runbook documents.
- `failed_queries.jsonl` — sample failed search queries.
- `expected_outcomes.jsonl` — expected alias outcomes for evaluation.

Use the runner to generate fresh fixture artifacts, index them into an isolated local index, and run read-only evidence validation.
