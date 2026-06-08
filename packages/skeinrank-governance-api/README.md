# skeinrank-governance-api

FastAPI control-plane API for SkeinRank terminology governance.

The package powers the governance console, dictionary import/export workflows,
proposal review, runtime snapshot export, evidence enrichment, operational checks,
and the MCP/agent-facing control-plane adapter. It sits above
`skeinrank-governance`, which owns SQLAlchemy models, Alembic migrations, and
shared governance primitives.

## Role in the architecture

```text
PostgreSQL governance store
  -> skeinrank-governance SQLAlchemy models and Alembic revisions
  -> skeinrank-governance-api HTTP control plane
  -> skeinrank-ui / CLI / MCP / agents
  -> approved snapshot artifacts
  -> headless runtime workers and search/RAG integrations
```

The runtime extraction path should not call this API for every request. The API is
for control-plane work: editing terminology, validating changes, reviewing
proposals, publishing immutable snapshots, and exporting artifacts that runtime
services can consume.

## Start locally

Install dependencies and run tests from this package directory:

```bash
poetry install
poetry run pytest -q
```

The API uses the same default local SQLite database URL as the governance CLI:

```bash
sqlite:///skeinrank_governance.db
```

Use migration-based setup for production-like local runs:

```bash
poetry run python -m skeinrank_governance_api.migrations upgrade head
poetry run skeinrank-governance-api --reload
```

Uvicorn is also supported:

```bash
poetry run uvicorn skeinrank_governance_api.main:app --reload
```

Check the service:

```bash
curl http://127.0.0.1:8010/healthz
curl http://127.0.0.1:8010/readyz
```

For quick demos only, tables can be created at startup:

```bash
export SKEINRANK_GOVERNANCE_API_CREATE_TABLES=true
```

## Configuration

The API reads database configuration from environment variables. The API-specific
variable has priority:

```bash
export SKEINRANK_GOVERNANCE_API_DATABASE_URL='sqlite:///skeinrank_governance.db'
```

The shared governance variable is supported as a fallback:

```bash
export SKEINRANK_GOVERNANCE_DATABASE_URL='sqlite:///skeinrank_governance.db'
```

PostgreSQL example:

```bash
export SKEINRANK_GOVERNANCE_DATABASE_URL='postgresql+psycopg://user:password@localhost:5432/skeinrank'
```

The local UI origin is allowed by default for browser-based development:

```text
http://127.0.0.1:5173
http://localhost:5173
```

Override CORS origins when needed:

```bash
export SKEINRANK_GOVERNANCE_API_CORS_ORIGINS='http://127.0.0.1:5173,http://localhost:5173'
```

## Auth, users, and roles

Auth is disabled by default so local UI workflows can run without a bootstrap
user. Enable it explicitly for protected-route testing:

```bash
export SKEINRANK_GOVERNANCE_API_AUTH_ENABLED=true
export SKEINRANK_GOVERNANCE_API_BOOTSTRAP_ADMIN=true
export SKEINRANK_GOVERNANCE_API_ADMIN_USERNAME=admin
export SKEINRANK_GOVERNANCE_API_ADMIN_PASSWORD='change-me'
```

The bootstrap user is created only when the users table is empty. Passwords are
stored as PBKDF2-SHA256 hashes and bearer tokens are stored hashed in the
database.

Roles:

- `admin` — full control over profiles, terms, aliases, snapshots, users, and
  operational reports.
- `moderator` — terminology editor for terms, aliases, suggestions, and snapshot
  export. No user-management permission.
- `contributor` — read terminology, validate payloads, and submit suggestions
  for moderator/admin review.

Login and inspect the current user:

```bash
TOKEN=$(curl -s -X POST http://127.0.0.1:8010/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"change-me"}' | python -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')

curl http://127.0.0.1:8010/v1/auth/me \
  -H "Authorization: Bearer $TOKEN"
```

Create a user as admin:

```bash
curl -X POST http://127.0.0.1:8010/v1/auth/users \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"username":"moderator","password":"moderator-secret","role":"moderator","display_name":"Moderator"}'
```

## API surface

Core service endpoints:

```text
GET  /healthz
GET  /readyz
GET  /schema/health
GET  /metrics
```

Dictionary and snapshot automation:

```text
POST /v1/console/dictionary/validate
POST /v1/console/dictionary/import
GET  /v1/console/dictionary/export?profile_name=infra_incidents
POST /v1/headless/dictionaries/validate
POST /v1/headless/dictionaries/apply
GET  /v1/headless/dictionaries/export?profile_name=infra_incidents
GET  /v1/headless/snapshots/export?binding_id=1
```

Proposal workflow:

```text
POST /v1/governance/profiles/{profile_name}/suggestions/apply-batch
```

Runtime planning and binding-aware canonicalization:

```text
POST /v1/text/canonicalize
POST /v1/query/route-plan
```

`route-plan` is a read-only multi-binding planning surface for selected/rejected bindings before search fan-out.

Elasticsearch/OpenSearch enrichment operations:

```text
POST /v1/governance/elasticsearch/bindings/{binding_id}/jobs/preflight
POST /v1/governance/elasticsearch/bindings/{binding_id}/jobs

The preflight response includes a per-run `confirmation_token`. Write-mode job
starts must echo that token so an operator confirms the exact snapshot, target,
alias, chunk size, document limit, and filter plan before any write is queued.
POST /v1/governance/elasticsearch/jobs/{job_id}/pause
POST /v1/governance/elasticsearch/jobs/{job_id}/resume
```

Operational reports:

```text
GET /v1/ops/troubleshooting/report
GET /v1/ops/alerts/report
GET /v1/governance/isolation-checks
GET /v1/agents/runs?limit=10
```

See [`docs/api/governance-api.md`](../../docs/api/governance-api.md) for the
full API reference.

## Dictionary import, validation, and export

The console dictionary API is intended for users who work from JupyterHub,
scripts, bots, notebooks, or future CLI tools. New payloads should include
`schema_version: skeinrank.dictionary.v1`; legacy payloads without a schema
version are treated as v1 for backward compatibility.

Minimal import payload:

```json
{
  "schema_version": "skeinrank.dictionary.v1",
  "profile_name": "infra_incidents",
  "profile_description": "Infra incident dictionary",
  "mode": "upsert",
  "terms": [
    {
      "canonical_value": "kubernetes",
      "slot": "TOOL",
      "aliases": [
        "k8s",
        {"value": "kube", "confidence": 0.95}
      ]
    }
  ],
  "profile_stop_list": [
    {"value": "tmp", "target": "alias", "reason": "too generic"}
  ],
  "global_stop_list": [
    {"value": "unknown", "target": "both", "reason": "global noise"}
  ]
}
```

Validate without writing:

```bash
curl -X POST http://127.0.0.1:8010/v1/console/dictionary/validate \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d @company_dictionary.json
```

Apply after validation:

```bash
curl -X POST http://127.0.0.1:8010/v1/console/dictionary/import \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d @company_dictionary.json
```

Export a profile back to the same stable shape:

```bash
curl "http://127.0.0.1:8010/v1/console/dictionary/export?profile_name=infra_incidents" \
  -H "Authorization: Bearer $TOKEN"
```

Import modes:

- `upsert` — create missing values and update existing values.
- `strict` — report conflicts when the payload already exists.

The validation/import report includes the resolved schema version, planned
create/update counts, duplicate warnings, alias/canonical conflicts, unsupported
schema-version errors, stop-list blocks, and prompt-like instruction warnings.

## Migration CLI and Terminology-as-Code

`skeinrank-migrate` is a stdlib-based CLI on top of the console and headless
APIs. It does not write to the database directly; it calls the same FastAPI
endpoints used by notebooks, bots, and scripts.

```bash
poetry run skeinrank-migrate --help
poetry run skeinrank-migrate lint ../../examples/migration/console_dictionary.example.yaml
poetry run skeinrank-migrate validate ../../examples/migration/console_dictionary.example.json
poetry run skeinrank-migrate validate ../../examples/migration/console_dictionary.example.yaml
poetry run skeinrank-migrate plan ../../examples/migration/console_dictionary.example.yaml \
  --output console_dictionary.plan.json
poetry run skeinrank-migrate apply ../../examples/migration/console_dictionary.example.json \
  --plan-output console_dictionary.apply-plan.json
poetry run skeinrank-migrate export --profile-name infra_incidents \
  --output infra_incidents.export.json
```

Export a binding-scoped runtime artifact for headless workers:

```bash
poetry run skeinrank-migrate snapshot-export \
  --binding-id 1 \
  --snapshot-version infra_incidents@v1 \
  --output runtime-snapshot.json

poetry run skeinrank-migrate snapshot-inspect runtime-snapshot.json
```

The snapshot artifact uses schema `skeinrank.runtime_snapshot_artifact.v1` and
includes the binding context plus compiled runtime aliases. It can be committed
to GitOps repositories or loaded by lightweight runtime workers without querying
PostgreSQL on every request.

Related docs and examples:

- [`docs/guides/terminology-as-code.md`](../../docs/guides/terminology-as-code.md)
- [`docs/guides/dictionary-cli-planning.md`](../../docs/guides/dictionary-cli-planning.md)
- [`docs/deployment/gitops-delivery-runbook.md`](../../docs/deployment/gitops-delivery-runbook.md)
- [`examples/terminology-as-code`](../../examples/terminology-as-code)
- [`examples/gitops-delivery`](../../examples/gitops-delivery)

## Headless quickstart

From the repository root, start the API/PostgreSQL-only profile and run the
golden path helper:

```bash
docker compose \
  --env-file deploy/docker/headless.env.example \
  -f docker-compose.headless.yml \
  up --build -d

deploy/docker/scripts/headless-golden-path.sh
```

The helper applies the example dictionary, creates a local binding, exports a
`skeinrank.runtime_snapshot_artifact.v1` file, and prints a summary. See
[`docs/deployment/headless-quickstart.md`](../../docs/deployment/headless-quickstart.md)
for the manual curl flow.

## Proposals, snapshots, and rollback

SkeinRank uses a proposal-first governance boundary for human and agent changes.
Supported `proposal_source_type` values are `human`, `agent`, `cli`, `api`,
`job`, and `import`. If `binding_id` is provided, it must reference a binding for
the same profile.

When `validation_summary` is omitted, the API stores an automatic validation
summary with checks for canonical availability, alias collisions, stop-list
guardrails, noisy aliases, confidence, idempotency hints, and agent audit
payloads. Callers may provide their own `validation_summary` when an external
checker has already run.

Batch-apply reviewed suggestions:

```text
POST /v1/governance/profiles/{profile_name}/suggestions/apply-batch
```

With `publish_snapshot=true` and a matching `binding_id`, the endpoint pins the
resulting runtime snapshot on that binding so headless runtime clients can
consume a reviewed version.

Rollout and rollback metadata are available for safer snapshot operations:

```text
POST /v1/governance/bindings/{binding_id}/snapshots/{snapshot_id}/pin
POST /v1/governance/bindings/{binding_id}/rollback
```

## Runtime routing

The production runtime context is binding-aware:

```text
Profile  = terminology space
Binding  = where and how a profile is applied
Snapshot = immutable terminology version pinned to a binding
```

Runtime-facing endpoints support binding-aware canonicalization and route
planning:

```text
POST /v1/text/canonicalize
POST /v1/query/route-plan
```

Use `binding_id` for production behavior. Profile-only calls remain useful for
preview/dev workflows. See
[`docs/guides/runtime-routing-api.md`](../../docs/guides/runtime-routing-api.md),
[`docs/guides/context-trigger-disambiguation.md`](../../docs/guides/context-trigger-disambiguation.md),
and [`examples/runtime-routing-api`](../../examples/runtime-routing-api).

## Elasticsearch/OpenSearch enrichment

The API supports evidence refresh, preflight checks, and controlled enrichment
jobs for Elasticsearch/OpenSearch-backed pilots and deployments.

Useful docs:

- [`docs/guides/elasticsearch-enrichment.md`](../../docs/guides/elasticsearch-enrichment.md)
- [`docs/guides/enrichment-beta-hardening.md`](../../docs/guides/enrichment-beta-hardening.md)
- [`docs/guides/enrichment-pause-resume-checkpointing.md`](../../docs/guides/enrichment-pause-resume-checkpointing.md)
- [`examples/enrichment-pause-resume`](../../examples/enrichment-pause-resume)
- [`docs/deployment/blue-green-alias-swap-runbook.md`](../../docs/deployment/blue-green-alias-swap-runbook.md)
- [`examples/blue-green-alias-swap`](../../examples/blue-green-alias-swap)

A production-safe flow starts with a read-only preflight, writes to a staged
index, validates the result, and swaps aliases only after operator review.
Chunked jobs expose `result_json.chunked_enrichment.checkpoint` so operators can
resume from remaining chunks.

## MCP and agent integration

The package includes `skeinrank-mcp`, a stdio adapter for agents and MCP clients.
The MCP surface is intentionally proposal-first: agents can inspect, validate,
and submit proposals, but cannot mutate production runtime state directly.

Security model:

- tools are allow-listed and schema-constrained;
- proxy-style arguments such as `endpoint`, `url`, `method`, `command`, `tool`,
  `tool_name`, `operation`, and `runtime_action` are rejected;
- MCP cannot publish snapshots, mutate bindings, run enrichment jobs, rollback
  jobs, read secrets, send email, or call external enterprise tools.

Related docs:

- [`docs/deployment/mcp-integration-kit.md`](../../docs/deployment/mcp-integration-kit.md)
- [`docs/deployment/mcp-claude-desktop.md`](../../docs/deployment/mcp-claude-desktop.md)
- [`docs/deployment/mcp-cursor-agents.md`](../../docs/deployment/mcp-cursor-agents.md)
- [`docs/deployment/mcp-langgraph-agents.md`](../../docs/deployment/mcp-langgraph-agents.md)
- [`docs/deployment/mcp-scoped-credentials-smoke-tests.md`](../../docs/deployment/mcp-scoped-credentials-smoke-tests.md)
- [`examples/mcp-scoped-credentials`](../../examples/mcp-scoped-credentials)
- [`examples/mcp-integration-kit`](../../examples/mcp-integration-kit)
- [`examples/mcp-agent-docs`](../../examples/mcp-agent-docs)
- [`docs/security/mcp-tool-guardrails.md`](../../docs/security/mcp-tool-guardrails.md)

## OpenRouter alias scout and model providers

The OpenRouter alias scout example is a bounded agent workflow for discovering,
validating, and proposing terminology changes. It remains safe by default: local
planning and reporting commands do not call OpenRouter, write to Elasticsearch,
or mutate runtime snapshots unless explicitly configured.

Common offline inspection commands and flags:

```bash
poetry run python ../../examples/agents/openrouter_alias_scout/run_alias_scout.py --print-tool-schemas
poetry run python ../../examples/agents/openrouter_alias_scout/run_alias_scout.py --discover-candidates
poetry run python ../../examples/agents/openrouter_alias_scout/run_alias_scout.py --print-sample-candidate-pack
poetry run python ../../examples/agents/openrouter_alias_scout/run_alias_scout.py --sample-evidence
poetry run python ../../examples/agents/openrouter_alias_scout/run_alias_scout.py --print-sample-evidence-pack
poetry run python ../../examples/agents/openrouter_alias_scout/run_alias_scout.py --print-llm-review-plan
poetry run python ../../examples/agents/openrouter_alias_scout/run_alias_scout.py --print-canonical-hints
poetry run python ../../examples/agents/openrouter_alias_scout/run_alias_scout.py --run-demo-report
poetry run python ../../examples/agents/openrouter_alias_scout/run_alias_scout.py --print-demo-review-prompt
poetry run python ../../examples/agents/openrouter_alias_scout/run_alias_scout.py --print-security-profile
poetry run python ../../examples/agents/openrouter_alias_scout/run_alias_scout.py --run-evaluation-report
poetry run python ../../examples/agents/openrouter_alias_scout/run_alias_scout.py --print-deployment-recipe
poetry run python ../../examples/agents/openrouter_alias_scout/run_alias_scout.py --print-model-provider-plan
```

Live execution remains opt-in through flags such as `--llm-review` and validated
proposal submission controls. Reports use schemas including
`skeinrank.agent_llm_review_report.v1`, `skeinrank.agent_demo_report.v1`,
`skeinrank.agent_evaluation_report.v1`, `skeinrank.agent_security_profile.v1`,
and `skeinrank.agent_deployment_recipe.v1`.

Model-provider support keeps OpenRouter as the default provider and adds a
`local_endpoint` adapter for self-hosted `/chat/completions` deployments. Use
`--print-model-provider-plan` to inspect provider configuration without exposing
secrets.

Related docs:

- [`docs/guides/openrouter-agent.md`](../../docs/guides/openrouter-agent.md)
- [`docs/deployment/openrouter-alias-scout.md`](../../docs/deployment/openrouter-alias-scout.md)
- [`docs/deployment/openrouter-agent-full-demo.md`](../../docs/deployment/openrouter-agent-full-demo.md)
- [`docs/deployment/model-provider-abstraction.md`](../../docs/deployment/model-provider-abstraction.md)
- [`docs/deployment/model-provider-adapters.md`](../../docs/deployment/model-provider-adapters.md)
- [`docs/deployment/company-model-integration.md`](../../docs/deployment/company-model-integration.md)

## Benchmarks and dry-run evaluation

The package includes deterministic local benchmark tools so teams can measure
proposal and retrieval behavior before touching production systems.

Headless proposal benchmark:

```bash
poetry run skeinrank-governance-benchmark seed --reset
poetry run skeinrank-governance-benchmark eval \
  --out ../../examples/benchmarks/platform_ops_v1/reports/platform_ops_v1-report.json
poetry run skeinrank-governance-benchmark report \
  --file ../../examples/benchmarks/platform_ops_v1/reports/platform_ops_v1-report.json
```

Retrieval evaluator and comparison report:

```bash
poetry run skeinrank-governance-retrieval-eval plan
poetry run skeinrank-governance-retrieval-eval eval \
  --out ../../examples/benchmarks/platform_ops_v1/reports/platform_ops_v1-retrieval-report.json
poetry run skeinrank-governance-retrieval-eval report \
  --file ../../examples/benchmarks/platform_ops_v1/reports/platform_ops_v1-retrieval-report.json
poetry run skeinrank-governance-retrieval-compare compare \
  --input ../../examples/benchmarks/platform_ops_v1/reports/platform_ops_v1-retrieval-report.json \
  --out ../../examples/benchmarks/platform_ops_v1/reports/platform_ops_v1-retrieval-comparison-report.json
```

Containerized benchmark stack:

```bash
make benchmark-stack-up
make benchmark-stack-wait
make benchmark-stack-seed
make benchmark-stack-eval
make benchmark-stack-report
poetry run python -m skeinrank_governance_api.benchmark_stack eval
poetry run skeinrank-governance-benchmark-stack report
```

Synthetic 5k smoke corpus and performance report:

```bash
poetry run skeinrank-governance-synthetic-smoke plan
poetry run skeinrank-governance-synthetic-smoke generate
poetry run skeinrank-governance-synthetic-smoke report
poetry run skeinrank-governance-benchmark-performance plan \
  --synthetic-manifest ../../examples/benchmarks/platform_ops_v1/reports/synthetic/platform_ops_v1-5k-manifest.json
poetry run skeinrank-governance-benchmark-performance report \
  --synthetic-manifest ../../examples/benchmarks/platform_ops_v1/reports/synthetic/platform_ops_v1-5k-manifest.json \
  --elapsed-seconds 300
poetry run skeinrank-governance-benchmark-performance show \
  --file ../../examples/benchmarks/platform_ops_v1/reports/platform_ops_v1-cost-latency-throughput-report.json
```

Report schemas and metrics include `skeinrank.retrieval_eval_report.v1`,
`skeinrank.retrieval_comparison_report.v1`, `skeinrank.synthetic_smoke_manifest.v1`,
`skeinrank.benchmark_stack_report.v1`, `skeinrank.benchmark_performance_report.v1`,
`NDCG@10`, `MRR@10`, `Recall@10`, `Precision@10`,
`hard_negative_leakage@10`, and `generic_token_noise@10`.

Related docs:

- [`docs/benchmarks/headless-agent-workflow.md`](../../docs/benchmarks/headless-agent-workflow.md)
- [`docs/benchmarks/retrieval-eval-baseline.md`](../../docs/benchmarks/retrieval-eval-baseline.md)
- [`docs/benchmarks/containerized-benchmark-integration.md`](../../docs/benchmarks/containerized-benchmark-integration.md)
- [`docs/benchmarks/synthetic-smoke-generator.md`](../../docs/benchmarks/synthetic-smoke-generator.md)
- [`docs/benchmarks/cost-latency-throughput-report.md`](../../docs/benchmarks/cost-latency-throughput-report.md)

## Pilot and support workflows

The pilot CLI provides a dependency-light HTTP workflow for first-company
Elasticsearch/OpenSearch evaluations. It reads a JSON config, validates the API
and index mapping, imports a seed dictionary, creates or reuses a dry-run
Elasticsearch binding, and writes a read-only evidence/query-plan report.

```bash
poetry run skeinrank-governance-pilot plan \
  --config ../../examples/pilots/elasticsearch_pilot.example.json

poetry run skeinrank-governance-pilot run \
  --api-url http://127.0.0.1:8010 \
  --config ../../examples/pilots/elasticsearch_pilot.example.json \
  --out ../../examples/pilots/reports/pilot-integration-report.json
```

Use `--token ...` or `--username ... --password ...` when auth is enabled. The
CLI does not call OpenRouter, submit proposals, approve/apply changes, or write
to Elasticsearch.

Support bundle tooling captures read-only diagnostics for pilot and production
handoffs:

```bash
poetry run skeinrank-governance-support-bundle plan
poetry run skeinrank-governance-support-bundle export
poetry run skeinrank-governance-support-bundle inspect --file support-bundle.zip
```

The support bundle code is available as `skeinrank_governance_api.support_bundle`.
Production-style exports can include health summaries, recent agent runs, log
inventory, config inventory, alerting report snapshots, and isolation-check
reports without sending webhooks, calling model providers, or mutating runtime
state.

Related docs:

- [`docs/pilots/elasticsearch-pilot-integration.md`](../../docs/pilots/elasticsearch-pilot-integration.md)
- [`docs/pilots/first-company-pilot-runbook.md`](../../docs/pilots/first-company-pilot-runbook.md)
- [`docs/pilots/troubleshooting-bundle-export.md`](../../docs/pilots/troubleshooting-bundle-export.md)
- [`docs/pilots/support-bundle-production.md`](../../docs/pilots/support-bundle-production.md)
- [`examples/pilots`](../../examples/pilots)

## Operations and deployment

Database migrations:

```bash
poetry run python -m skeinrank_governance_api.migrations upgrade head
poetry run python -m skeinrank_governance_api.migrations current
poetry run python -m skeinrank_governance_api.migrations history
poetry run python -m skeinrank_governance_api.migrations check
```

Backup and restore:

```bash
poetry run python -m skeinrank_governance_api.backup_restore export --out backups/governance.json
poetry run python -m skeinrank_governance_api.backup_restore inspect --file backups/governance.json
poetry run python -m skeinrank_governance_api.backup_restore restore --file backups/governance.json --dry-run
poetry run skeinrank-governance-backup-drill plan
```

Production Compose helpers from the repository root:

```bash
cp .env.production.example .env
make prod-env-check
poetry run python -m skeinrank_governance_api.env_validation validate --file ../../.env
docker compose --env-file .env -f docker-compose.prod.yml config
docker compose --env-file .env -f docker-compose.prod.yml up --build -d
deploy/docker/scripts/prod-smoke-test.sh
deploy/docker/scripts/prod-smoke-test.sh --strict
```

Observability and diagnostics:

```bash
curl http://127.0.0.1:8010/metrics | grep -E "skeinrank_(database_up|schema_ok|agent_runs_current)"
curl http://127.0.0.1:8010/v1/ops/troubleshooting/report | python -m json.tool
poetry run python -m skeinrank_governance_api.troubleshooting report
poetry run skeinrank-governance-alerting report
```

Alerting hooks expose an alerting report for degraded-state summaries. When auth
is enabled, operational HTTP reports require an admin user or a service-account
token with the matching read scope.

Deployment docs:

- [`docs/deployment/production-compose.md`](../../docs/deployment/production-compose.md)
- [`docs/deployment/docker-compose.md`](../../docs/deployment/docker-compose.md)
- [`docs/deployment/env-and-secrets.md`](../../docs/deployment/env-and-secrets.md)
- [`docs/deployment/security.md`](../../docs/deployment/security.md)
- [`docs/deployment/observability.md`](../../docs/deployment/observability.md)
- [`docs/deployment/backup-restore.md`](../../docs/deployment/backup-restore.md)
- [`docs/deployment/backup-restore-verified-scenario.md`](../../docs/deployment/backup-restore-verified-scenario.md)
- [`docs/deployment/upgrade-guide.md`](../../docs/deployment/upgrade-guide.md)
- [`docs/deployment/migration-safety.md`](../../docs/deployment/migration-safety.md)
- [`docs/deployment/release-checklist.md`](../../docs/deployment/release-checklist.md)
- [`docs/deployment/helm-chart.md`](../../docs/deployment/helm-chart.md)
- [`docs/deployment/helm-production.md`](../../docs/deployment/helm-production.md)
- [`docs/deployment/helm-smoke-test.md`](../../docs/deployment/helm-smoke-test.md)

## Security and policy docs

Security docs cover prompt-injection boundaries, MCP tool safety, RAG context
boundaries, apply-policy risk levels, role boundaries, scoped credentials, token
rotation, and tenant/profile isolation checks.

- [`docs/security/prompt-injection.md`](../../docs/security/prompt-injection.md)
- [`docs/security/prompt-like-detector.md`](../../docs/security/prompt-like-detector.md)
- [`docs/security/prompt-injection-regression-corpus.md`](../../docs/security/prompt-injection-regression-corpus.md)
- [`docs/security/rag-context-boundaries.md`](../../docs/security/rag-context-boundaries.md)
- [`docs/security/agent-tool-safety.md`](../../docs/security/agent-tool-safety.md)
- [`docs/security/mcp-tool-guardrails.md`](../../docs/security/mcp-tool-guardrails.md)
- [`docs/policies/apply-policy-risk-levels.md`](../../docs/policies/apply-policy-risk-levels.md)
- [`docs/policies/role-boundaries.md`](../../docs/policies/role-boundaries.md)
- [`docs/policies/token-rotation-scoped-agent-credentials.md`](../../docs/policies/token-rotation-scoped-agent-credentials.md)
- [`docs/policies/profile-isolation-checks.md`](../../docs/policies/profile-isolation-checks.md)

## Current package scope

This package provides:

- FastAPI app factory and Uvicorn launcher command;
- environment-based configuration;
- SQLAlchemy session dependency;
- health, readiness, schema-health, metrics, and troubleshooting endpoints;
- local auth, user management, roles, and scoped service-account flows;
- governance REST endpoints for profiles, terms, aliases, suggestions, stop
  lists, snapshots, bindings, rollback, and proposal review;
- console and headless dictionary validation/import/export endpoints;
- binding-scoped runtime snapshot export;
- binding-aware runtime canonicalization and route planning;
- Elasticsearch/OpenSearch evidence and enrichment job APIs;
- MCP stdio adapter for proposal-first agent integrations;
- benchmark, pilot, support-bundle, backup/restore, alerting, and migration CLIs;
- deployment docs for Docker Compose, Helm, GitOps, security, observability,
  upgrade, backup/restore, and operational runbooks.

## Related documentation

- [Headless Compose quickstart](../../docs/deployment/headless-quickstart.md) — run the API/PostgreSQL headless runtime contract with `docker-compose.headless.yml`.
