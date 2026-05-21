<p align="center">
  <a href="https://skeinrank.github.io">
    <img src="docs/assets/skeinrank-logo.png" alt="SkeinRank logo" width="88" height="88" />
  </a>
</p>

<h1 align="center">SkeinRank</h1>

<p align="center">
  <strong>Open-source terminology control plane for search and RAG.</strong>
</p>

<p align="center">
  Turn messy aliases such as <code>k8s</code>, <code>kube</code>, <code>pg</code>, and <code>postgres</code>
  into governed, versioned runtime context for enterprise search, Elasticsearch, and RAG workflows.
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
  <a href="https://skeinrank.github.io">
    <img src="docs/assets/screenshots/dashboard-runtime-control-center-dark.png" alt="SkeinRank governance console dashboard" width="960" />
  </a>
</p>

---

SkeinRank helps teams make company terminology usable at runtime: normalize noisy domain language, govern canonical terms and aliases, publish immutable snapshots, enrich indexed documents, and serve search-ready context to retrieval, RAG, and agent workflows.

The repository includes a lightweight Python SDK/CLI, FastAPI runtime and governance APIs, a React governance console, PostgreSQL-backed control-plane state, Elasticsearch enrichment jobs, RabbitMQ/Celery workers, and Docker Compose deployment profiles.

## What SkeinRank gives you

| Capability | Why it matters |
| --- | --- |
| Terminology governance | Manage canonical terms, aliases, slots, guardrails, and review workflows in one control plane. |
| Runtime bindings | Bind a profile to a concrete index/search context and pin the safe snapshot used at runtime. |
| Evidence-assisted review | Check aliases against Elasticsearch documents before accepting terminology changes. |
| Enrichment jobs | Write canonical values, slots, matched aliases, and snapshot metadata back into indexed documents. |
| Search Playground | Preview how raw queries become governed runtime context before integrating downstream search/RAG. |

## Why SkeinRank

Internal knowledge rarely uses one clean vocabulary. The same concept can appear as `k8s`, `kube`, `kubernetes`, `pg`, `postgres`, `postgresql`, service nicknames, team-specific abbreviations, and incident shorthand.

Search and RAG systems usually see that as noise. SkeinRank turns it into a managed lifecycle:

```text
Discover → Validate → Review → Publish snapshot → Bind to runtime → Enrich/search → Evaluate
```

The core idea is simple:

```text
Profile = domain terminology
Binding = where and how that terminology is applied
Snapshot = immutable runtime version
Evidence = why a term or alias should be trusted
```

## Quickstart: platform preview

Use Docker Compose when you want to try the full platform: governance console, API, PostgreSQL, Elasticsearch, RabbitMQ worker, and UI.

```bash
cp .env.example .env
docker compose -f docker-compose.dev.yml up --build -d
```

Populate the console with a live demo dataset:

```bash
make demo-reset
```

This loads `examples/platform_ops_demo`, creates the `platform_ops` profile, binds it to the `platform_knowledge_base` Elasticsearch index, creates review suggestions, checks evidence, and runs enrichment for the Dashboard, Terms, Integrations, Suggestions, Search Playground, and Snapshots screens.

Default local URLs:

| Service | URL |
| --- | --- |
| UI | `http://127.0.0.1:5173` |
| Governance API | `http://127.0.0.1:8010` |
| Elasticsearch | `http://127.0.0.1:19200` |
| RabbitMQ Management | `http://127.0.0.1:15672` |
| PostgreSQL | `127.0.0.1:15432` |

Full instructions live in [`docs/deployment/docker-compose.md`](docs/deployment/docker-compose.md).

## Quickstart: local SDK / CLI

Use the lightweight `skeinrank` package path when you want to validate a dictionary or test canonicalization without starting platform services.

```bash
cd packages/skeinrank-core
poetry install

poetry run skeinrank validate-dictionary ../../examples/migration/console_dictionary.example.json
poetry run skeinrank extract "k8s rollout uses pg database" \
  --text \
  --dictionary ../../examples/migration/console_dictionary.example.json
```

Python SDK:

```python
from skeinrank import load_dictionary, extract_terms

dictionary = load_dictionary("examples/migration/console_dictionary.example.json")
result = extract_terms("k8s rollout uses pg database", dictionary=dictionary)

print(result.canonical_values)  # ["kubernetes", "postgresql"]
```

See [`docs/guides/core-sdk-and-cli.md`](docs/guides/core-sdk-and-cli.md) for CLI, SDK, document extraction, packaging, and publishing notes.

## Documentation

Start here:

- [`docs/overview.md`](docs/overview.md) — product overview and repository map.
- [`docs/concepts/terminology-control-plane.md`](docs/concepts/terminology-control-plane.md) — terminology, aliases, guardrails, evidence, and snapshots.
- [`docs/concepts/profiles-bindings-snapshots.md`](docs/concepts/profiles-bindings-snapshots.md) — why production runtime should be binding-first.
- [`docs/guides/core-sdk-and-cli.md`](docs/guides/core-sdk-and-cli.md) — local SDK/CLI workflows.
- [`docs/guides/governance-console.md`](docs/guides/governance-console.md) — governance API and UI workflows.
- [`docs/guides/elasticsearch-enrichment.md`](docs/guides/elasticsearch-enrichment.md) — enrichment, dry-runs, jobs, evidence, and cancellation.
- [`docs/guides/development.md`](docs/guides/development.md) — development checks and package layout.
- [`docs/api/governance-api.md`](docs/api/governance-api.md) — important governance/runtime API surfaces.

Deployment docs:

- [`docs/deployment/docker-compose.md`](docs/deployment/docker-compose.md)
- [`docs/deployment/security.md`](docs/deployment/security.md)
- [`docs/deployment/observability.md`](docs/deployment/observability.md)
- [`docs/deployment/dev-stack-troubleshooting.md`](docs/deployment/dev-stack-troubleshooting.md)

## Repository layout

```text
packages/skeinrank-core                    Lightweight Python SDK, CLI, extraction, canonicalization
packages/skeinrank-server                  FastAPI runtime wrapper for extraction/rerank workflows
packages/skeinrank-provider-elasticsearch  Elasticsearch provider and enrichment CLI
packages/skeinrank-governance              SQLAlchemy/Alembic governance foundation
packages/skeinrank-governance-api          FastAPI governance/control-plane API and worker
packages/skeinrank-ui                      React/TypeScript governance console
examples/platform_ops_demo                 Local preview seed data and automation
examples/demo                              Demo corpus, queries, enriched documents, eval output
examples/migration                         Example dictionary import/export payloads
deploy/                                    Dockerfiles, Prometheus, Grafana, OpenTelemetry config
docs/                                      Product, concept, guide, API, and deployment docs
```

## Development checks

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

The GitHub Actions workflow runs Ruff, package tests, UI type checks/tests/builds, and Docker/deployment smoke checks.

## Docker Compose dev stack

SkeinRank includes Docker Compose profiles for local development and production-like deployment.

Main files:

- [`docker-compose.dev.yml`](docker-compose.dev.yml) — local development stack.
- [`docker-compose.prod.yml`](docker-compose.prod.yml) — production-oriented stack.
- [`docs/deployment/docker-compose.md`](docs/deployment/docker-compose.md) — Docker Compose setup guide.
- [`docs/deployment/dev-stack-troubleshooting.md`](docs/deployment/dev-stack-troubleshooting.md) — local stack troubleshooting.
- [`docs/deployment/security.md`](docs/deployment/security.md) — deployment and security notes.

## Project status

SkeinRank is an active open-source platform preview, not a hosted SaaS. The current focus is terminology governance, profile bindings, snapshot-safe runtime context, Elasticsearch enrichment, evidence-assisted review, Search Playground workflows, and local Docker Compose deployment.

## License

Apache-2.0. See [`LICENSE`](LICENSE).
