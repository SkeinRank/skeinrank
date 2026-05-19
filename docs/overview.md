# Overview

SkeinRank is an open-source terminology control plane for search and RAG systems.

It focuses on a practical enterprise problem: internal documents, incident reports, runbooks, tickets, and logs often use inconsistent domain language. A single concept might appear as `k8s`, `kube`, `kubernetes`, `pg`, `postgres`, `postgresql`, or a local team nickname. Search and retrieval pipelines lose signal when this terminology stays unmanaged.

SkeinRank turns that noisy terminology into governed runtime context.

## Core capabilities

| Capability | Description |
| --- | --- |
| Dictionary-first extraction | Load company terminology from JSON dictionaries and extract canonical terms from text or documents. |
| Alias canonicalization | Map aliases such as `k8s -> kubernetes` and `pg -> postgresql`. |
| Profiles | Keep terminology separated by domain, team, product, or document collection. |
| Bindings | Apply profiles to a concrete runtime search context such as an Elasticsearch index or alias. |
| Snapshots | Serve immutable terminology versions to runtime extraction and search workflows. |
| Guardrails | Block noisy terms globally or per profile before they pollute search context. |
| Evidence workflows | Check whether a term or alias appears in real indexed content before approving it. |
| Enrichment jobs | Write SkeinRank context into Elasticsearch documents through safe dry-run and job workflows. |

## Product layers

```text
Local SDK / CLI
  -> dictionary validation, extraction, canonicalization, document text extraction

Governance API / UI
  -> profiles, terms, aliases, suggestions, guardrails, users, tokens, bindings, snapshots

Elasticsearch workflows
  -> connection discovery, binding dry-runs, enrichment jobs, evidence snapshots

Runtime context
  -> pinned snapshots, canonical query context, binding-aware search/RAG side-car usage
```

## Repository layout

```text
packages/skeinrank-core
  Lightweight Python package, SDK, CLI, extraction pipeline, canonicalization, and tests.

packages/skeinrank-server
  FastAPI runtime wrapper for extraction and search/rerank-style workflows.

packages/skeinrank-provider-elasticsearch
  Elasticsearch provider and CLI enrichment path.

packages/skeinrank-governance
  SQLAlchemy models, Alembic migrations, and admin CLI foundation.

packages/skeinrank-governance-api
  FastAPI governance/control-plane API, runtime APIs, worker, migrations, and tests.

packages/skeinrank-ui
  React/TypeScript governance console.

examples/demo
  Small demo documents, queries, enriched output, and evaluation report.

examples/migration
  Example dictionary import/export payload.

deploy
  Dockerfiles, Docker scripts, Prometheus, Grafana, and OpenTelemetry configuration.

docs
  Product, concept, guide, API, and deployment documentation.
```

## When to use SkeinRank

SkeinRank is useful when a team has search or RAG workflows where domain terminology matters and the vocabulary changes over time.

Common examples:

- internal wiki and runbook search;
- incident and postmortem retrieval;
- support ticket search;
- domain-specific Elasticsearch/OpenSearch indexes;
- RAG pipelines that need canonical entity/context hints;
- governance workflows where contributors suggest aliases but reviewers approve changes.

## Current status

SkeinRank is an active open-source platform preview. The lightweight core package is usable locally, and the platform stack is intended for local product smoke tests, integration experiments, and future production hardening.
