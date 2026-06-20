# Development guide

This repository is a monorepo. Each package keeps its own dependencies and tests. Repository-level commands in the root `Makefile` provide a consistent entrypoint for common checks.

## Requirements

Common local tools:

- Python 3.10+ for core utilities;
- Python 3.11+ for governance API development;
- Poetry for Python packages;
- Node.js 22+ for the UI;
- Docker Compose v2 for full-stack smoke tests;
- `pre-commit` and Ruff for repository hygiene. Ruff can be installed in any active shell, exposed through `RUFF=/path/to/ruff`, or resolved from a pyenv-managed Python version.

## Install package environments

Each Python package owns its Poetry environment. Install only the packages you plan to work on:

```bash
cd packages/skeinrank-core
poetry install --with dev

cd ../skeinrank-governance-api
poetry install --with dev
```

For the UI:

```bash
cd packages/skeinrank-ui
npm install
```

## Repository-level checks

Run these commands from the repository root.

| Command | What it checks |
| --- | --- |
| `make lint` | Ruff lint checks across the repository. The command resolves Ruff from `RUFF`, `PATH`, or pyenv-managed Python versions. |
| `make format-check` | Ruff formatting check without rewriting files. Uses the same Ruff resolver as `make lint`. |
| `make format` | Ruff formatting rewrite. Uses the same Ruff resolver as `make lint`. |
| `make check` | Lint, format check, fast Python tests, migration checks, and documentation checks. |
| `make test-fast` | Narrow core and governance API tests for the most active development path. |
| `make test-scout` | Alias Scout candidate, evidence, LLM, dataset, and canonical lifecycle tests. |
| `make test-migrations` | Governance API migration and schema health tests. |
| `make test-docs` | Documentation and README guard tests. |
| `make test-python` | All Python package test suites. |
| `make test-ui` | UI typecheck, Vitest, and build. |
| `make test-all` | Python package tests plus UI checks. |

Use `make test-fast` while iterating. Use `make check` before committing a cross-package change.

## Ruff resolution

The root `Makefile` does not require Ruff to be installed in the currently selected Python. The lint and format commands run through `tools/dev/resolve_ruff.py`, which resolves Ruff in this order:

1. the `RUFF` environment variable;
2. the current `PATH`;
3. `pyenv which ruff`;
4. any pyenv-managed Python version that exposes `bin/ruff`.

To pin a specific executable for one command:

```bash
RUFF="$HOME/.pyenv/versions/3.11.9/bin/ruff" make check
```

To inspect what executable will be used:

```bash
python3 tools/dev/resolve_ruff.py --print-command check .
```

## Package-specific tests

The root commands delegate to package-local Poetry environments.

Core package:

```bash
make test-core
```

Governance models and migrations package:

```bash
make test-governance-models
```

Governance API:

```bash
make test-governance-api
```

Elasticsearch provider:

```bash
make test-provider-elasticsearch
```

HTTP server wrapper:

```bash
make test-server
```

UI:

```bash
make test-ui
```

## Running commands manually

You can still run package-local commands directly when you need a narrower loop:

```bash
cd packages/skeinrank-core
poetry run pytest -q tests/test_candidate_discovery.py
```

```bash
cd packages/skeinrank-governance-api
poetry run pytest -q tests/test_openrouter_agent_llm_workflow.py
```

## Governance API locally

```bash
cd packages/skeinrank-governance-api
poetry run python -m skeinrank_governance_api.migrations upgrade head
poetry run skeinrank-governance-api --reload
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
- UI typecheck, tests, and build;
- Docker/deployment smoke checks.

Keep package public APIs and CLI names stable. When adding a new public endpoint, CLI command, or UI action, add or update tests in the owning package.
