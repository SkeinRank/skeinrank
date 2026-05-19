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
  into governed runtime context for enterprise search, Elasticsearch, and knowledge workflows.
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

---

SkeinRank helps teams make company terminology usable at runtime: normalize noisy domain language, govern canonical terms and aliases, publish immutable snapshots, enrich indexed documents, and serve search-ready context to retrieval and RAG systems.

The project is currently an active preview. The repository includes a lightweight Python package, a FastAPI runtime/server layer, a governance API, a React governance console, Elasticsearch enrichment workflows, and Docker Compose deployment profiles.

## Why SkeinRank

Internal knowledge rarely uses one clean vocabulary. The same concept can appear as `k8s`, `kube`, `kubernetes`, `pg`, `postgres`, `postgresql`, service nicknames, team-specific abbreviations, and incident shorthand.

SkeinRank gives that vocabulary an explicit control plane:

| Layer | What it does |
| --- | --- |
| Local SDK / CLI | Validate dictionaries, extract canonical terms, canonicalize text, and test aliases locally. |
| Governance API / UI | Review terms and aliases, manage profiles, guardrails, API tokens, users, bindings, and snapshots. |
| Elasticsearch workflows | Bind profiles to indices, dry-run enrichment, check evidence, and write runtime context safely. |
| Runtime context | Serve pinned snapshots and canonicalized query/search context to downstream search, RAG, and agent workflows. |

## Quickstart: local dictionary extraction

Use the lightweight `skeinrank` package path when you want to test a dictionary without starting platform services.

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

## Quickstart: platform beta stack

Use Docker Compose when you want to test the governance console, API, PostgreSQL, Elasticsearch, RabbitMQ worker, and UI together.

```bash
cp .env.example .env
docker compose -f docker-compose.dev.yml up --build
```

Default local URLs:

| Service | URL |
| --- | --- |
| UI | `http://127.0.0.1:5173` |
| Governance API | `http://127.0.0.1:8010` |
| Elasticsearch | `http://127.0.0.1:19200` |
| RabbitMQ Management | `http://127.0.0.1:15672` |
| PostgreSQL | `127.0.0.1:15432` |

Full instructions live in [`docs/deployment/docker-compose.md`](docs/deployment/docker-compose.md).

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
packages/skeinrank-core                  Lightweight Python SDK, CLI, extraction, canonicalization
packages/skeinrank-server                FastAPI runtime wrapper for extraction/rerank workflows
packages/skeinrank-provider-elasticsearch Elasticsearch provider and enrichment CLI
packages/skeinrank-governance             SQLAlchemy/Alembic governance foundation
packages/skeinrank-governance-api         FastAPI governance/control-plane API and worker
packages/skeinrank-ui                     React/TypeScript governance console
examples/demo                             Demo corpus, queries, enriched documents, eval output
examples/migration                        Example dictionary import/export payloads
deploy/                                   Dockerfiles, Prometheus, Grafana, OpenTelemetry config
docs/                                     Product, concept, guide, API, and deployment docs
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

## Project status

SkeinRank is under active development and is not a hosted SaaS. The current focus is a production-shaped open-source platform preview: terminology governance, dictionary migration, profile bindings, snapshot-safe runtime context, Elasticsearch enrichment, evidence-assisted review, and local Docker Compose deployment.

## License

Apache-2.0. See [`LICENSE`](LICENSE).
