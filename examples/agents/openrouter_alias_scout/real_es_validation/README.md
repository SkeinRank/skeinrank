# Real Elasticsearch validation scenario

This directory contains a tiny deterministic fixture set for validating the OpenRouter alias scout against a real Elasticsearch/OpenSearch index.

The scenario is intentionally small and isolated:

- `documents.jsonl` — sample incident/runbook documents;
- `failed_queries.jsonl` — sample failed search queries;
- `expected_outcomes.jsonl` — expected alias outcomes for evaluation.

Use the runner to generate fresh fixture artifacts, index them into an isolated local index, and run read-only evidence validation.

## What it demonstrates

- failed-query alias candidate discovery;
- compact evidence sampling from a real search backend;
- deterministic expected-outcome checks;
- proposal-first validation before any governance mutation.

## Safety boundary

This scenario is for isolated local validation. It should not point at a production index unless an operator intentionally provides non-local configuration and review controls.

The alias scout should validate and propose. It should not directly publish snapshots, mutate production bindings, or change search-engine configuration.
