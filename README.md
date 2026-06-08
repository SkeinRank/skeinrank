<p align="center">
  <a href="https://skeinrank.github.io">
    <img src="docs/assets/skeinrank-logo.png" alt="SkeinRank logo" width="88" height="88" />
  </a>
</p>

<h1 align="center">SkeinRank</h1>

<p align="center">
  <strong>Your RAG is not failing because retrieval is hard.<br/>It is failing because your company's language is a mess.</strong>
</p>

<p align="center">
  Open-source <strong>Terminology Control Plane</strong> for enterprise search, RAG, and AI-agent workflows.<br/>
  SkeinRank canonicalizes aliases, acronyms, incident shorthand, and ambiguous names into governed, versioned, binding-aware runtime context.
</p>

<p align="center">
  <a href="https://skeinrank.github.io">Website</a>
  ·
  <a href="https://skeinrank.github.io/docs/">Docs</a>
  ·
  <a href="https://skeinrank.github.io/quickstart/">Quickstart</a>
  ·
  <a href="https://pypi.org/project/skeinrank/">PyPI</a>
</p>

<p align="center">
  <a href="https://github.com/SkeinRank/skeinrank/actions/workflows/ci.yml">
    <img alt="CI" src="https://github.com/SkeinRank/skeinrank/actions/workflows/ci.yml/badge.svg" />
  </a>
  <a href="https://pypi.org/project/skeinrank/">
    <img alt="PyPI" src="https://img.shields.io/pypi/v/skeinrank?color=8b5cf6" />
  </a>
  <a href="LICENSE">
    <img alt="License" src="https://img.shields.io/github/license/SkeinRank/skeinrank?color=22d3ee" />
  </a>
  <a href="https://skeinrank.github.io">
    <img alt="Website" src="https://img.shields.io/badge/docs-skeinrank.github.io-0ea5e9" />
  </a>
</p>

<p align="center">
  <img
    src="docs/assets/architecture/skeinrank-sidecar-architecture.jpeg"
    alt="SkeinRank sidecar architecture for search, RAG, and AI agents"
    width="920"
  />
</p>

<p align="center">
  <em>Drop SkeinRank into your stack as a terminology sidecar: canonicalize noisy domain language, resolve runtime context through bindings, and send search-ready requests to your backend.</em>
</p>

---

## See it in 30 seconds

A user types team slang. SkeinRank turns it into something your search engine, RAG workflow, or agent can use safely:

```text
raw query:        "k8s pg timeout"
canonical query:  "kubernetes postgresql timeout"
runtime context:  binding + profile + fields + pinned snapshot
```

The lightweight SDK works without Docker, OpenRouter, Elasticsearch, or a dictionary file:

```python
import skeinrank

print(skeinrank.canonicalize("k8s pg timeout"))
# kubernetes postgresql timeout

print(skeinrank.extract("sev1 on kube after deploy"))
# ['critical incident', 'kubernetes', 'deployment']
```

The built-in `platform_ops_demo` dictionary is intentionally small but shows the product idea: company slang, incidents, CI/CD, search, RAG, and context-shaped phrases:

```python
print(skeinrank.canonicalize("pg timeout"))
# postgresql timeout

print(skeinrank.canonicalize("pg layout"))
# page layout
```

From a source checkout, the same zero-config path is available through the CLI:

```bash
cd packages/skeinrank-core
poetry install
poetry run skeinrank canonicalize "k8s pg timeout" --text
poetry run skeinrank extract "sev1 on kube after deploy" --text --compact
```

For the full platform preview with UI, Governance API, Elasticsearch, RabbitMQ, and AI Inbox:

```bash
cp .env.example .env
docker compose -f docker-compose.dev.yml up --build -d
make demo-reset
make demo-tour
make demo-tour-smoke
```

`make demo-reset` loads the `platform_ops` profile, creates the `platform_knowledge_base` Elasticsearch index, adds evidence-backed AI Inbox proposals, and prepares the Playground plus Schema & Snapshots demo. `make demo-tour-smoke` writes `examples/platform_ops_demo/reports/platform_ops_demo_tour_report.json`; the runner is `examples/platform_ops_demo/demo_product_tour.py`.

Default local URLs: UI `http://127.0.0.1:5173`, Governance API `http://127.0.0.1:8010`, Elasticsearch `http://127.0.0.1:19200`, RabbitMQ Management `http://127.0.0.1:15672`.

Start with [`packages/skeinrank-core/README.md`](packages/skeinrank-core/README.md), [`examples/sdk`](examples/sdk), [`docs/guides/seeded-demo-walkthrough.md`](docs/guides/seeded-demo-walkthrough.md), [`docs/guides/demo-product-tour.md`](docs/guides/demo-product-tour.md), and [`examples/platform_ops_demo`](examples/platform_ops_demo).

## The problem

Users do not search with your canonical vocabulary. They search with team slang, legacy abbreviations, incident shorthand, and ambiguous internal names:

```text
"k8s pg timeout"
```

Your systems may store the same idea as `kubernetes`, `Kube`, `PostgreSQL`, `postgres`, or `psql`. In another workspace, `pg` might mean `page` or `product group`. Search engines, vector databases, RAG prompts, and agents usually see that as noise.

SkeinRank gives that language a single governed lifecycle instead of spreading it across Elasticsearch synonym files, regex snippets, CSVs, prompts, and one-off scripts.

## What SkeinRank does

SkeinRank is a **terminology sidecar** for teams that already run Elasticsearch, OpenSearch, vector search, internal documentation search, RAG, or AI-agent workflows.

It does not replace your search engine. It sits beside your application stack and turns messy company language into governed, versioned, binding-aware runtime context:

| Step | What happens |
| --- | --- |
| Discover | Find internal terms, acronyms, aliases, and ambiguous surfaces. |
| Prove | Attach evidence from documents, incidents, tickets, and search traces. |
| Govern | Review proposed changes through AI Inbox and risk-aware policy. |
| Snapshot | Publish immutable terminology versions for runtime use. |
| Bind | Apply the right vocabulary to the right search context. |
| Serve | Expose API, SDK, CLI, and MCP tools for search, RAG, and agents. |
| Evaluate | Compare retrieval behavior before and after terminology changes. |

SkeinRank is **not a direct production CRUD console** by design. Production terminology changes flow through `proposal -> validation -> risk policy -> review -> snapshot -> rollout`. The product model is intentionally proposal, validation, risk policy, review, snapshots, and GitOps-style rollout.

See [`docs/product-positioning.md`](docs/product-positioning.md) for the product narrative and public-beta checklist.

## Why a control plane, not a synonym file

Every search engine has a synonym list. But a synonym list is configuration, not governance.

At scale, teams need to answer questions a flat config file cannot answer:

- which terminology version is live right now;
- who approved an alias and what evidence supported it;
- how to roll back a bad terminology change;
- why `pg timeout` should resolve differently from `pg layout`;
- how agents can propose terminology without mutating production directly.

SkeinRank treats terminology as a governed, auditable, versioned asset across the search backend you already run.

| SkeinRank capability | Why it matters |
| --- | --- |
| Terminology governance | Canonical terms, aliases, slots, tags, guardrails, and review workflows in one place. |
| Binding-aware runtime | Resolve terminology by application scope, search index, fields, and pinned snapshot. |
| Context-trigger disambiguation | Keep ambiguous aliases safe: `pg timeout` can map differently than `pg layout`. |
| Terminology-as-Code | Lint, plan, apply, export, and snapshot dictionaries through CI/GitOps workflows. |
| Evidence-assisted review | Check aliases against Elasticsearch/OpenSearch evidence before accepting changes. |
| Enrichment safety | Preflight, blue/green alias swap, rollback, pause/resume, and chunk checkpointing. |
| MCP integration | Let Claude Desktop, Cursor-style IDE agents, and LangGraph-style agents inspect and submit proposals safely. |

## Core model

| Concept | Meaning |
| --- | --- |
| `Profile` | Domain terminology: canonical values, aliases, slots, tags, stop lists. |
| `Binding` | Runtime search context: profile + index/alias + fields + target field + pinned snapshot. |
| `Snapshot` | Immutable terminology version that can be safely served or exported. |
| `Proposal` | Agent, CLI, or human-submitted terminology change awaiting review. |
| `Evidence` | Documents, query traces, validation findings, and risk metadata behind a proposal. |

In production, runtime requests are **binding-first** because the binding already knows the index, fields, snapshot, filters, and runtime policy:

```json
{
  "binding_id": 1,
  "query": "k8s pg timeout"
}
```

`profile_name` remains useful for preview/dev workflows. `binding_id` is the production search context.

## Control Plane and Data Plane

```text
Control Plane: profiles, proposals, evidence, risk policy, snapshots, audit
Data Plane: immutable runtime snapshots, local canonicalization, enrichment/search integration
```

The focused UI is intentionally small:

```text
Playground -> debug query canonicalization
AI Inbox -> review evidence-backed agent proposals
Schema & Snapshots -> inspect profiles, bindings, aliases, and snapshot state
```

## Quickstart paths

| Path | Use when | Start here |
| --- | --- | --- |
| SDK and dictionary onboarding | You want to try the Python SDK, import an existing synonym file, or draft a dictionary from local docs. | [`packages/skeinrank-core/README.md`](packages/skeinrank-core/README.md), [`docs/guides/import-dictionary.md`](docs/guides/import-dictionary.md), [`docs/guides/agent-dictionary-assistant.md`](docs/guides/agent-dictionary-assistant.md) |
| Terminology drift reports | You want to check whether a dictionary still covers recent docs, incident notes, or runbooks before creating proposals. | [`docs/guides/terminology-drift-report.md`](docs/guides/terminology-drift-report.md), [`examples/drift-scan`](examples/drift-scan) |
| Release stack | You want to run the public beta from prebuilt GHCR images. | `cp .env.example .env` then `docker compose up -d`; [`docs/deployment/release-compose.md`](docs/deployment/release-compose.md) |
| Full dev stack | You want to build from source with PostgreSQL, Elasticsearch, RabbitMQ, Governance API, worker, and UI. | [`docs/deployment/docker-compose.md`](docs/deployment/docker-compose.md) |
| Headless runtime | You want API/PostgreSQL dictionary apply/export and snapshot artifact smoke tests. | [`docker-compose.headless.yml`](docker-compose.headless.yml), [`docs/deployment/headless-quickstart.md`](docs/deployment/headless-quickstart.md) |
| Kubernetes alpha | You want a Helm chart using the published GHCR images. | [`charts/skeinrank`](charts/skeinrank), [`docs/deployment/helm-chart.md`](docs/deployment/helm-chart.md) |
| Production-oriented Compose | You want a hardened Compose template and security notes. | [`docker-compose.prod.yml`](docker-compose.prod.yml), [`docs/deployment/production-compose.md`](docs/deployment/production-compose.md) |

<details>
<summary>Runtime API</summary>

SkeinRank exposes binding-aware runtime endpoints for canonicalization, query planning, and search integration:

```text
POST /v1/text/canonicalize
POST /v1/query/plan
POST /v1/query/route-plan
POST /v1/search
POST /v1/search/multi
```

`route-plan` is read-only: it returns selected/rejected bindings, canonical queries, scores, and runtime context without executing search.

Start here: [`docs/guides/runtime-routing-api.md`](docs/guides/runtime-routing-api.md), [`docs/guides/context-trigger-disambiguation.md`](docs/guides/context-trigger-disambiguation.md), [`examples/runtime-routing-api`](examples/runtime-routing-api).

</details>

<details>
<summary>Benchmark workflows</summary>

SkeinRank includes deterministic benchmark and pilot workflows that do not require OpenRouter or production data by default.

| Area | Commands / docs |
| --- | --- |
| Headless benchmark | `make benchmark-reset`, `make benchmark-seed`, `make benchmark-eval`, `make benchmark-report`; [`docs/benchmarks/headless-agent-workflow.md`](docs/benchmarks/headless-agent-workflow.md) |
| Containerized benchmark | `make benchmark-stack-run`; [`docs/benchmarks/containerized-benchmark-integration.md`](docs/benchmarks/containerized-benchmark-integration.md) |
| Retrieval eval | `make benchmark-retrieval-eval`, `make benchmark-retrieval-compare`; [`docs/benchmarks/retrieval-eval-baseline.md`](docs/benchmarks/retrieval-eval-baseline.md) |
| Synthetic smoke | `make benchmark-smoke-generate`; [`docs/benchmarks/synthetic-smoke-generator.md`](docs/benchmarks/synthetic-smoke-generator.md) |
| Performance report | `make benchmark-performance-report`; [`docs/benchmarks/cost-latency-throughput-report.md`](docs/benchmarks/cost-latency-throughput-report.md) |
| First-company pilot | `make pilot-plan`; [`docs/pilots/elasticsearch-pilot-integration.md`](docs/pilots/elasticsearch-pilot-integration.md) |

</details>

<details>
<summary>Terminology-as-Code and GitOps</summary>

SkeinRank supports a safe file-based workflow for teams that manage terminology in Git.

The model is **YAML outside, JSON inside**: people review YAML/JSON dictionary artifacts in Git, the API speaks JSON, PostgreSQL remains the control-plane source of truth, and runtime workers consume binding-scoped immutable snapshot artifacts.

```bash
cd packages/skeinrank-governance-api
poetry run skeinrank-migrate lint ../../examples/terminology-as-code/platform_ops.dictionary.yaml
poetry run skeinrank-migrate plan ../../examples/terminology-as-code/platform_ops.dictionary.yaml --output plan.json
poetry run skeinrank-migrate apply ../../examples/terminology-as-code/platform_ops.dictionary.yaml --plan-output applied-plan.json
poetry run skeinrank-migrate export --profile-name platform_ops --output dictionary.json
poetry run skeinrank-migrate snapshot-export --binding-id 1 --source latest --output runtime-snapshot.json
poetry run skeinrank-migrate snapshot-eval --before before.json --after after.json --queries queries.jsonl --output snapshot-evaluation.json
```

Docs and examples: [`docs/guides/terminology-as-code.md`](docs/guides/terminology-as-code.md), [`docs/guides/dictionary-cli-planning.md`](docs/guides/dictionary-cli-planning.md), [`docs/deployment/gitops-delivery-runbook.md`](docs/deployment/gitops-delivery-runbook.md), [`examples/terminology-as-code`](examples/terminology-as-code), [`examples/gitops-delivery`](examples/gitops-delivery).

</details>

<details>
<summary>Enrichment safety</summary>

Elasticsearch/OpenSearch enrichment is treated as an operator workflow, not a casual UI action. Use preflight and blue/green alias swap for production-like runs.

Important surfaces include:

```text
POST /v1/governance/elasticsearch/bindings/{binding_id}/dry-run
POST /v1/governance/elasticsearch/bindings/{binding_id}/jobs/preflight
POST /v1/governance/elasticsearch/bindings/{binding_id}/jobs
POST /v1/governance/elasticsearch/jobs/{job_id}/pause
POST /v1/governance/elasticsearch/jobs/{job_id}/resume
POST /v1/governance/elasticsearch/jobs/{job_id}/cancel
POST /v1/governance/elasticsearch/jobs/{job_id}/rollback
```

Runbooks: [`docs/guides/elasticsearch-enrichment.md`](docs/guides/elasticsearch-enrichment.md), [`docs/guides/enrichment-beta-hardening.md`](docs/guides/enrichment-beta-hardening.md), [`docs/deployment/blue-green-alias-swap-runbook.md`](docs/deployment/blue-green-alias-swap-runbook.md), [`docs/guides/enrichment-pause-resume-checkpointing.md`](docs/guides/enrichment-pause-resume-checkpointing.md), [`examples/blue-green-alias-swap`](examples/blue-green-alias-swap).

</details>

<details>
<summary>MCP and agent integration</summary>

SkeinRank includes a dependency-light MCP stdio adapter. It exposes only proposal-safe tools: agents can inspect, validate, and submit pending proposals, but they do not publish snapshots or mutate runtime directly.

```bash
cd packages/skeinrank-governance-api
poetry run skeinrank-mcp --print-tool-manifest
poetry run skeinrank-mcp --print-env-template
poetry run skeinrank-mcp --smoke-test
```

MCP tools:

```text
skeinrank_list_bindings
skeinrank_explain_query
skeinrank_validate_alias
skeinrank_submit_alias_proposal
skeinrank_get_proposal_status
```

Docs and examples: [`docs/deployment/mcp-integration-kit.md`](docs/deployment/mcp-integration-kit.md), [`docs/deployment/mcp-scoped-credentials-smoke-tests.md`](docs/deployment/mcp-scoped-credentials-smoke-tests.md), [`docs/deployment/mcp-claude-desktop.md`](docs/deployment/mcp-claude-desktop.md), [`docs/deployment/mcp-cursor-agents.md`](docs/deployment/mcp-cursor-agents.md), [`docs/deployment/mcp-langgraph-agents.md`](docs/deployment/mcp-langgraph-agents.md), [`examples/mcp-integration-kit`](examples/mcp-integration-kit), [`examples/mcp-scoped-credentials`](examples/mcp-scoped-credentials), [`examples/mcp-agent-docs`](examples/mcp-agent-docs), [`examples/agents/openrouter_alias_scout`](examples/agents/openrouter_alias_scout), [`docs/guides/openrouter-agent.md`](docs/guides/openrouter-agent.md).

</details>

<details>
<summary>Docker, Kubernetes, and operations</summary>

## Docker Compose dev stack

Use the dev stack when you want to build SkeinRank from source and run the full local preview with PostgreSQL, Elasticsearch, RabbitMQ, the Governance API, worker, and UI.

```bash
cp .env.example .env
docker compose -f docker-compose.dev.yml up --build -d
```

See [`docs/deployment/docker-compose.md`](docs/deployment/docker-compose.md) for the full install flow, [`docs/deployment/dev-stack-troubleshooting.md`](docs/deployment/dev-stack-troubleshooting.md) for common local failures, [`docs/deployment/security.md`](docs/deployment/security.md) for deployment/security notes, and [`docker-compose.prod.yml`](docker-compose.prod.yml) for the production-oriented Compose template.

## Docker images and Kubernetes

Release images are published to GHCR by [`.github/workflows/docker-publish.yml`](.github/workflows/docker-publish.yml). The workflow runs automatically for `v*` git tags and can be launched manually for an existing tag such as `v0.10.0-beta.1`.

Main references:

- [`docs/deployment/docker-images.md`](docs/deployment/docker-images.md) — GHCR image publishing and manual rebuilds for existing tags.
- [`docs/deployment/release-compose.md`](docs/deployment/release-compose.md) — `docker-compose.yml` release stack using GHCR images.
- [`docs/deployment/helm-chart.md`](docs/deployment/helm-chart.md) — alpha Helm chart for Kubernetes installs using the published GHCR images.
- [`docs/deployment/helm-production.md`](docs/deployment/helm-production.md) — production-oriented Helm values, ingress, PDB, resources, and secret strategy.
- [`docs/deployment/helm-smoke-test.md`](docs/deployment/helm-smoke-test.md) — optional kind smoke test for the alpha Helm chart.
- [`docs/deployment/ci-routing.md`](docs/deployment/ci-routing.md) — path-aware CI routing and the `ci-required` gate.
- [`docs/deployment/release-checklist.md`](docs/deployment/release-checklist.md) — release validation checklist.

Operational runbooks: [`docs/deployment/observability.md`](docs/deployment/observability.md), [`docs/deployment/env-and-secrets.md`](docs/deployment/env-and-secrets.md), [`docs/deployment/backup-restore.md`](docs/deployment/backup-restore.md), [`docs/deployment/upgrade-guide.md`](docs/deployment/upgrade-guide.md), [`docs/deployment/migration-safety.md`](docs/deployment/migration-safety.md), [`docs/deployment/alerting-hooks-degraded-state-reports.md`](docs/deployment/alerting-hooks-degraded-state-reports.md), [`docs/pilots/troubleshooting-bundle-export.md`](docs/pilots/troubleshooting-bundle-export.md), [`docs/pilots/support-bundle-production.md`](docs/pilots/support-bundle-production.md).

</details>

<details>
<summary>Documentation map</summary>

| Topic | Start here |
| --- | --- |
| Product overview | [`docs/overview.md`](docs/overview.md), [`docs/product-positioning.md`](docs/product-positioning.md) |
| Core concepts | [`docs/concepts/terminology-control-plane.md`](docs/concepts/terminology-control-plane.md), [`docs/concepts/profiles-bindings-snapshots.md`](docs/concepts/profiles-bindings-snapshots.md), [`docs/concepts/headless-runtime-contracts.md`](docs/concepts/headless-runtime-contracts.md), [`docs/adr/0001-headless-runtime-contracts.md`](docs/adr/0001-headless-runtime-contracts.md) |
| Dictionary and coverage | [`docs/concepts/dictionary-spec-v1.md`](docs/concepts/dictionary-spec-v1.md), [`docs/concepts/coverage-framework.md`](docs/concepts/coverage-framework.md), [`docs/guides/coverage-framework.md`](docs/guides/coverage-framework.md), [`examples/coverage-framework`](examples/coverage-framework) |
| SDK onboarding | [`packages/skeinrank-core/README.md`](packages/skeinrank-core/README.md), [`docs/guides/import-dictionary.md`](docs/guides/import-dictionary.md), [`docs/guides/agent-dictionary-assistant.md`](docs/guides/agent-dictionary-assistant.md), [`examples/import-dictionary`](examples/import-dictionary), [`examples/suggest-dictionary`](examples/suggest-dictionary), [`examples/agent-dictionary-assistant`](examples/agent-dictionary-assistant) |
| API and UI | [`docs/api/governance-api.md`](docs/api/governance-api.md), [`docs/guides/governance-console.md`](docs/guides/governance-console.md), [`docs/guides/proposal-inbox-ui.md`](docs/guides/proposal-inbox-ui.md) |
| AI safety | [`docs/security/prompt-injection.md`](docs/security/prompt-injection.md), [`docs/security/rag-context-boundaries.md`](docs/security/rag-context-boundaries.md), [`docs/security/agent-tool-safety.md`](docs/security/agent-tool-safety.md), [`docs/security/mcp-tool-guardrails.md`](docs/security/mcp-tool-guardrails.md), [`docs/security/prompt-like-detector.md`](docs/security/prompt-like-detector.md), [`docs/security/prompt-injection-regression-corpus.md`](docs/security/prompt-injection-regression-corpus.md) |
| Deployment | [`docs/deployment/docker-compose.md`](docs/deployment/docker-compose.md), [`docs/deployment/release-compose.md`](docs/deployment/release-compose.md), [`docs/deployment/headless-quickstart.md`](docs/deployment/headless-quickstart.md), [`docs/deployment/production-compose.md`](docs/deployment/production-compose.md), [`docs/deployment/security.md`](docs/deployment/security.md), [`docs/deployment/observability.md`](docs/deployment/observability.md) |
| Pilots | [`docs/pilots/first-company-pilot-runbook.md`](docs/pilots/first-company-pilot-runbook.md), [`examples/pilots/first_company_pilot_checklist.md`](examples/pilots/first_company_pilot_checklist.md), [`docs/pilots/elasticsearch-pilot-integration.md`](docs/pilots/elasticsearch-pilot-integration.md) |
| Community | [`docs/community/discussions.md`](docs/community/discussions.md), [`docs/community/github-labels.md`](docs/community/github-labels.md) |
| Development | [`docs/guides/development.md`](docs/guides/development.md), [`docs/deployment/ci-routing.md`](docs/deployment/ci-routing.md) |

</details>

<details>
<summary>Repository layout and development checks</summary>

```text
packages/skeinrank-core                    Python SDK, CLI, extraction, canonicalization
packages/skeinrank-server                  FastAPI runtime wrapper for extraction/rerank workflows
packages/skeinrank-provider-elasticsearch  Elasticsearch provider and enrichment CLI
packages/skeinrank-governance              SQLAlchemy/Alembic governance foundation
packages/skeinrank-governance-api          FastAPI governance/control-plane API, workers, MCP adapter
packages/skeinrank-ui                      React/TypeScript governance console
examples/platform_ops_demo                 Local preview seed data and guided tour automation
examples/sdk                               Zero-friction SDK demo script and exported demo dictionary
examples/migration                         Example dictionary import/export payloads
examples/coverage-framework                Tags, ambiguous alias, binding policy, and evaluation examples
examples/import-dictionary                 Convert CSV, JSON, and ES synonyms into dictionary candidates
examples/suggest-dictionary                Build deterministic dictionary drafts from local documents
examples/agent-dictionary-assistant        Optional OpenRouter-assisted draft grouping with offline demo
examples/agents/openrouter_alias_scout       Offline alias scout for agent-driven terminology discovery
deploy/                                    Dockerfiles, Prometheus, Grafana, OpenTelemetry config
docs/                                      Product, concept, guide, API, and deployment docs
charts/skeinrank                           Alpha Helm chart
```

Run repository-level hygiene from the root:

```bash
python -m pip install -r requirements-dev.txt
pre-commit install
ruff check .
ruff format --check .
```

Run package tests from each package directory with its own tooling. For example:

```bash
cd packages/skeinrank-core
poetry install
poetry run pytest -q
```

The GitHub Actions workflow uses path-aware routing so docs/deployment changes do not run unrelated package installs, while package and UI changes still run their own checks. See [`docs/deployment/ci-routing.md`](docs/deployment/ci-routing.md).

</details>

## Community

- Use [Issues](https://github.com/SkeinRank/skeinrank/issues) for reproducible bugs, failing commands, docs mistakes, and concrete implementation tasks.
- Use [Discussions](https://github.com/SkeinRank/skeinrank/discussions) for questions, ideas, architecture proposals, integration feedback, and public beta conversations.
- See [`docs/community/discussions.md`](docs/community/discussions.md) for discussion categories and pinned discussion drafts.
- See [`docs/community/github-labels.md`](docs/community/github-labels.md) for the repository label taxonomy and GitHub CLI sync commands.

## Project status

SkeinRank is an active open-source platform preview, not a hosted SaaS. The current focus is binding-aware runtime canonicalization, safe terminology governance, AI Inbox review, Terminology-as-Code, MCP agent integration, and Elasticsearch/OpenSearch enrichment safety.

## License

Apache-2.0. See [`LICENSE`](LICENSE).
