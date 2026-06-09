# Contributing to SkeinRank

Thanks for your interest in SkeinRank.

SkeinRank is an open-source terminology control plane for enterprise search, RAG, and AI-agent workflows. The project is still moving quickly, so contributions are most useful when they are small, testable, and aligned with the current product direction.

## Product direction

The default workflow is:

```text
proposal -> validation -> risk policy -> human review -> snapshot / GitOps rollout
```

Please avoid adding new UI flows that directly mutate production terminology, bindings, enrichment jobs, or runtime snapshots without going through the governed workflow.

Search integrations should keep SkeinRank focused on governed terminology artifacts. Prefer query-time adapters, vector pre-embedding adapters, export artifacts, and short examples over engine-specific management code. Direct backend writes require an explicit operator-controlled delivery workflow with preflight, per-run confirmation, and rollback guidance. See [`docs/concepts/search-integration-scope.md`](docs/concepts/search-integration-scope.md).

## Local setup

### Python packages

Each Python package is managed with Poetry. For example:

```bash
cd packages/skeinrank-governance-api
poetry install
poetry run pytest -q
```

### UI package

```bash
cd packages/skeinrank-ui
npm install
npm run typecheck
npm test -- --run
npm run build
```

### Full local demo stack

From the repository root:

```bash
docker compose -f docker-compose.dev.yml up --build -d
make demo-tour
```

For an already seeded stack:

```bash
make demo-tour-smoke
make demo-tour-show
```

## Before opening a pull request

Run the narrow tests for the area you changed. If the change touches the public demo, run:

```bash
cd packages/skeinrank-governance-api
poetry run python -m pytest \
  tests/test_platform_ops_demo_seed.py \
  tests/test_platform_ops_demo_tour.py \
  -q
```

If the change touches the UI, run:

```bash
cd packages/skeinrank-ui
npm run typecheck
npm test -- --run
npm run build
```

## Contribution scope

Good first contributions usually look like:

- docs fixes;
- small deterministic tests;
- sample dictionaries and walkthrough improvements;
- safe read-only diagnostics;
- connector planning docs;
- bug reports with logs and reproduction steps.

Please open an issue first for larger work such as schema changes, new provider integrations, GitOps import/apply flows, search integration behavior changes, enrichment delivery behavior changes, or MCP tool surface changes.

## Code style

The Python CI uses Ruff and pytest. The UI uses TypeScript, Vitest, and Vite. Keep new code deterministic and avoid live network calls in tests unless a test is explicitly marked as a guarded live smoke.

## Security and secrets

Never commit secrets, `.env` files, generated support bundles, demo reports, OpenRouter API keys, Elasticsearch credentials, or database dumps. See `SECURITY.md` for vulnerability reporting.


## Issues and Discussions

Use Issues for reproducible bugs, failing commands, documentation mistakes, and concrete implementation tasks. Use Discussions for questions, ideas, architecture proposals, integration feedback, and public beta conversations.

Issue labels follow the taxonomy in [`docs/community/github-labels.md`](docs/community/github-labels.md): `type:*`, `area:*`, `status:*`, and `priority:*`. New issues should start as `status: needs-triage` until a maintainer accepts or redirects them.

Architecture changes should usually start as a Discussion in `Architecture / RFC` before becoming implementation issues. Integration ideas for Elasticsearch/OpenSearch, MCP clients, Claude Desktop, Cursor, LangGraph-style agents, RAG pipelines, or GitOps delivery can start in the `Integrations` discussion category.

