# Development guide

This repository is a monorepo. Each package keeps its own dependencies and tests, while repository-level checks cover linting and formatting.

## Requirements

Common local tools:

- Python 3.10+;
- Poetry for Python packages;
- Node.js 22+ for the UI;
- Docker Compose v2 for full-stack smoke tests;
- `pre-commit` and Ruff for repository hygiene.

## Repository-level hygiene

From the repository root:

```bash
python -m pip install -r requirements-dev.txt
pre-commit install
ruff check .
ruff format --check .
```

## Core package tests

```bash
cd packages/skeinrank-core
poetry install
poetry run pytest -q
```

## Server package tests

```bash
cd packages/skeinrank-server
poetry install
poetry run pytest -q
```

## Elasticsearch provider tests

```bash
cd packages/skeinrank-provider-elasticsearch
poetry install
poetry run pytest -q
```

## Governance foundation tests

```bash
cd packages/skeinrank-governance
poetry install
poetry run pytest -q
poetry run alembic upgrade head
```

## Governance API tests

```bash
cd packages/skeinrank-governance-api
poetry install
poetry run pytest -q
```

Run the API locally:

```bash
poetry run python -m skeinrank_governance_api.migrations upgrade head
poetry run skeinrank-governance-api --reload
```

## UI checks

```bash
cd packages/skeinrank-ui
npm install
npm run typecheck
npm run test
npm run build
```

## Docker Compose smoke test

```bash
cp .env.example .env
docker compose -f docker-compose.dev.yml up --build
```

Run the bundled smoke helper after the stack is up:

```bash
deploy/docker/scripts/dev-smoke-test.sh
```

## CI

GitHub Actions runs:

- Ruff checks and format checks;
- Python package tests;
- UI typecheck/tests/build;
- Docker/deployment smoke checks.

Keep package public APIs and CLI names stable. When adding a new public endpoint, CLI command, or UI action, add or update tests in the owning package.
