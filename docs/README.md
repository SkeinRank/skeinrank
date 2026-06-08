# SkeinRank docs

SkeinRank is an open-source Terminology Control Plane for enterprise search, RAG, and AI-agent workflows. These docs explain how to evaluate the product safely, operate the governance API, connect runtime search contexts, and prepare production deployments.

Public product site: <https://skeinrank.github.io>

## Start here

- [Overview](overview.md) — what SkeinRank solves and how the repository is organized.
- [Product positioning](product-positioning.md) — personas, product scope, demo story, and public-beta readiness.
- [Terminology Control Plane](concepts/terminology-control-plane.md) — terms, aliases, evidence, guardrails, review, and snapshots.
- [Profiles, bindings, and snapshots](concepts/profiles-bindings-snapshots.md) — the production model for binding-scoped runtime behavior.
- [Headless runtime contracts](concepts/headless-runtime-contracts.md) and [ADR 0001](adr/0001-headless-runtime-contracts.md) — runtime boundaries for API, agents, snapshots, and UI.
- [Dictionary spec v1](concepts/dictionary-spec-v1.md) — stable import/export contract for governed terminology.

## Quick evaluation

Use this section to prove value without serving production traffic.

- [Seeded demo walkthrough](guides/seeded-demo-walkthrough.md) — explore Playground, AI Inbox, Schema & Snapshots, and the read-only legacy cockpit.
- [Demo product tour](guides/demo-product-tour.md) — run `make demo-tour` and `make demo-tour-smoke`; outputs include `platform_ops_demo_tour_report.json`.
- [Headless quickstart](deployment/headless-quickstart.md) — API/PostgreSQL-only evaluation flow for dictionary apply, binding setup, and snapshot artifacts.
- [Containerized benchmark integration](benchmarks/containerized-benchmark-integration.md) — Docker Compose benchmark stack with PostgreSQL, Governance API, and Elasticsearch.
- [Elasticsearch pilot integration](pilots/elasticsearch-pilot-integration.md) — connect an existing Elasticsearch index and generate a read-only integration report.
- [First company pilot runbook](pilots/first-company-pilot-runbook.md) — plan, rehearse, run, review, and exit a pilot safely.

## Core concepts

- [Coverage framework](concepts/coverage-framework.md) — slots, tags, ambiguous aliases, binding policies, and evaluation guardrails.
- [Runtime routing API guide](guides/runtime-routing-api.md) — binding-aware canonicalization, query planning, read-only multi-binding `route-plan`, and search requests.
- [Context-trigger disambiguation](guides/context-trigger-disambiguation.md) — context rules for resolving ambiguous aliases without introducing new endpoints.
- [Coverage workflow guide](guides/coverage-framework.md) — headless workflow for tags, conflicts, ambiguous candidates, policies, and before/after evaluation.

## Terminology-as-Code

- [Terminology-as-Code](guides/terminology-as-code.md) — YAML/JSON dictionaries in Git, JSON APIs, PostgreSQL control-plane state, and binding-scoped runtime artifacts.
- [Dictionary CLI planning](guides/dictionary-cli-planning.md) — local lint, server-backed plan, and apply-from-plan workflow.
- [GitOps delivery runbook](deployment/gitops-delivery-runbook.md) — GitLab CI, ArgoCD, Flux, and binding-scoped runtime artifact delivery.
- [Reference GitOps examples](../examples/gitops-delivery) — GitLab CI, ArgoCD, Flux, and Kustomize examples.

## Runtime API and SDKs

- [Governance API](api/governance-api.md) — important HTTP surfaces and runtime endpoints.
- [Core SDK and CLI](guides/core-sdk-and-cli.md) — local dictionary validation, extraction, canonicalization, and document extraction.
- [Import existing dictionaries](guides/import-dictionary.md) and [reference examples](../examples/import-dictionary) — convert CSV, JSON, and Elasticsearch/OpenSearch synonym lists into reviewable dictionary candidates.
- [Agent dictionary assistant](guides/agent-dictionary-assistant.md), [deterministic suggestion examples](../examples/suggest-dictionary), and [assistant examples](../examples/agent-dictionary-assistant) — create reviewable drafts from local documents with or without OpenRouter.
- [Terminology drift report](guides/terminology-drift-report.md) and [drift scan examples](../examples/drift-scan) — compare a dictionary with local corpus samples, review uncovered aliases, stale terms, binding lag, and ambiguity signals.
- [Governance console](guides/governance-console.md) — API and UI workflow for review-first operations.
- [Runtime routing examples](../examples/runtime-routing-api) — request examples for canonicalization, route planning, and binding-aware search.

## Governance console UI

- [Proposal Inbox UI](guides/proposal-inbox-ui.md) — review evidence, risk, validation findings, and approve/reject actions.
- [Playground snapshot compare UI](guides/playground-snapshot-compare-ui.md) — compare binding-backed runtime snapshots.
- [Schema & Snapshots tree UI](guides/schema-snapshots-tree-ui.md) — inspect bindings, profiles, canonical terms, aliases, and snapshot drift.
- [UI polish and degraded banners](guides/ui-polish-empty-states-degraded-banners.md) — degraded-state banner and actionable empty states.
- [Control Plane navigation](guides/control-plane-navigation-slim-down.md) — primary navigation contract for Playground, AI Inbox, and Schema & Snapshots.
- [Read-only legacy admin cockpit](guides/read-only-legacy-admin-cockpit.md) — legacy write-control lockdown and local-development bypass.

## MCP and agents

- [MCP integration kit](deployment/mcp-integration-kit.md) and [reference examples](../examples/mcp-integration-kit) — stdio adapter setup, tool manifest, env template, smoke test, and safe proposal-first tool contract.
- [MCP scoped credentials smoke tests](deployment/mcp-scoped-credentials-smoke-tests.md) and [scoped credential examples](../examples/mcp-scoped-credentials) — validate service-account credential boundaries.
- [Claude Desktop MCP guide](deployment/mcp-claude-desktop.md), [Cursor MCP guide](deployment/mcp-cursor-agents.md), and [LangGraph MCP guide](deployment/mcp-langgraph-agents.md) — client-specific setup for the existing adapter surface.
- [MCP agent docs examples](../examples/mcp-agent-docs) — example client configs, agent policies, and smoke checklist.
- [OpenRouter alias scout](deployment/openrouter-alias-scout.md) and [agent walkthrough](guides/openrouter-agent.md) — proposal-first alias discovery and review flow.
- [OpenRouter full demo](deployment/openrouter-agent-full-demo.md) and [OpenRouter alias scout example](../examples/agents/openrouter_alias_scout) — guarded live-review and local evaluation assets.

## Elasticsearch and enrichment

- [Elasticsearch/OpenSearch delivery](guides/elasticsearch-enrichment.md) — operator-controlled dry run, evidence, jobs, confirmation, and cancellation.
- [Operator-controlled search delivery hardening](guides/enrichment-beta-hardening.md) — preflight, per-run confirmation, concurrency guard, and delivery safety rules.
- [Pause/resume checkpointing](guides/enrichment-pause-resume-checkpointing.md) — Celery-backed enrichment job checkpoint metadata.
- [Blue/green alias swap runbook](deployment/blue-green-alias-swap-runbook.md) and [blue/green examples](../examples/blue-green-alias-swap) — operator-reviewed alias publish, cancellation, and rollback flow.

## Deployment and operations

- [Docker Compose development stack](deployment/docker-compose.md) — local stack for development and integration checks.
- [Production Compose](deployment/production-compose.md) — production-oriented Compose profile.
- [Release Compose](deployment/release-compose.md) — run SkeinRank with published GHCR images.
- [Docker images](deployment/docker-images.md) — GHCR image publishing for release tags and manual rebuilds.
- [Helm chart](deployment/helm-chart.md), [production Helm values](deployment/helm-production.md), and [Helm smoke test](deployment/helm-smoke-test.md) — Kubernetes installation and validation.
- [Environment and secrets](deployment/env-and-secrets.md) — configuration and secret handling.
- [Deployment security](deployment/security.md) — production security posture and linked safety docs.
- [Observability](deployment/observability.md) — metrics, logs, traces, and dashboards.
- [Alerting and degraded-state reports](deployment/alerting-hooks-degraded-state-reports.md) — read-only operator alert payloads and status reports.
- [Backup and restore](deployment/backup-restore.md) and [verified restore scenario](deployment/backup-restore-verified-scenario.md) — recovery operations.
- [Migration safety](deployment/migration-safety.md) — migration checks and safe rollout guidance.
- [Upgrade guide](deployment/upgrade-guide.md) and [release checklist](deployment/release-checklist.md) — release and upgrade operations.
- [CI routing](deployment/ci-routing.md) — path-aware GitHub Actions routing for package, UI, docs, deployment, Docker, and Helm changes.
- [Development guide](guides/development.md) — local development checks and package workflow.

## Security and safety

- [Prompt injection risk taxonomy](security/prompt-injection.md) — AI-safety boundary for untrusted data, evidence, proposals, and runtime context.
- [RAG context boundaries](security/rag-context-boundaries.md) — keep retrieved text as data, not instructions.
- [Agent tool safety](security/agent-tool-safety.md) — proposal-first safety model for MCP and agent integrations.
- [Prompt-like instruction detector](security/prompt-like-detector.md) — review metadata for risky instructions in evidence, imports, and proposals.
- [MCP tool guardrails](security/mcp-tool-guardrails.md) — enforced MCP tool policy, forbidden runtime tools, and closed tool schemas.
- [Prompt injection regression corpus](security/prompt-injection-regression-corpus.md) — stable JSONL corpus and evaluator for prompt-injection checks.
- [Apply policy and risk levels](policies/apply-policy-risk-levels.md) — risk classification for safe apply workflows.
- [Role boundaries](policies/role-boundaries.md) — agent, reviewer, and admin responsibilities.
- [Profile isolation checks](policies/profile-isolation-checks.md) — read-only profile/binding alignment checks.
- [Token rotation and scoped agent credentials](policies/token-rotation-scoped-agent-credentials.md) — scoped credential lifecycle.

## Benchmarks and quality gates

- [Headless agent workflow benchmark](benchmarks/headless-agent-workflow.md) — deterministic workflow quality report, proposal quality metrics, and agent decision diagnostics.
- [OpenRouter live pilot](benchmarks/openrouter-live-pilot.md) — guarded live-review pilot with cost limits and no runtime mutation.
- [Retrieval evaluation baseline](benchmarks/retrieval-eval-baseline.md) — qrels, hard negatives, query-hygiene metrics, NDCG@10, MRR@10, Recall@10, and baseline-vs-SkeinRank deltas.
- [Retrieval comparison workflow](benchmarks/retrieval-eval-baseline.md#retrieval-comparison-workflow) — `benchmark-retrieval-compare` diagnostics for before/after quality checks.
- [Synthetic smoke generator](benchmarks/synthetic-smoke-generator.md) — deterministic 5k synthetic corpus for scale checks.
- [Cost, latency, and throughput report](benchmarks/cost-latency-throughput-report.md) — offline cost, latency, throughput, savings, and projection report.

## Pilots and support

- [Pilot integration](pilots/elasticsearch-pilot-integration.md) — first external index integration flow.
- [Pilot runbook](pilots/first-company-pilot-runbook.md) — safe operator workflow for a first company pilot.
- [Troubleshooting bundle export](pilots/troubleshooting-bundle-export.md) — sanitized support bundle export for pilot troubleshooting.
- [Production support bundle](pilots/support-bundle-production.md) — logs, config inventory, health snapshots, alerts, degraded state, and last agent runs.

## Model providers and company integration

- [Model provider abstraction](deployment/model-provider-abstraction.md) — provider-agnostic model configuration.
- [Model provider adapters](deployment/model-provider-adapters.md) — adapter contracts for model providers.
- [Company model integration](deployment/company-model-integration.md) — connect company-hosted or managed model endpoints.

## Community

- [GitHub Discussions](community/discussions.md) — Q&A, announcements, ideas, integrations, and show-and-tell setup.
- [GitHub labels](community/github-labels.md) — issue and PR label taxonomy.
- [Contributing](../CONTRIBUTING.md), [Security](../SECURITY.md), and [Code of Conduct](../CODE_OF_CONDUCT.md) — project participation and disclosure guidance.
