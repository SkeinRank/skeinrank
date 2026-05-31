# Path-aware CI routing

SkeinRank keeps the main `ci` workflow available on every pull request and `main` push, but routes the expensive jobs based on changed paths.

The goal is to avoid running every package install, test suite, and UI build for docs-only or deployment-only changes while still keeping branch protection predictable.

## Workflow entry point

The routing lives in:

```text
.github/workflows/ci.yml
```

The workflow always starts with the `changes` job. It checks the changed file list and emits boolean outputs for the areas that need validation:

```text
core
server
provider_elasticsearch
governance
governance_api
ui
docs_contracts
python_any
force_all
```

## Routed jobs

The default CI jobs keep their existing names so current branch protection rules continue to work:

```text
lint
test (packages/skeinrank-core, 3.11)
test (packages/skeinrank-server, 3.11)
test (packages/skeinrank-provider-elasticsearch, 3.11)
test (packages/skeinrank-governance, 3.11)
test (packages/skeinrank-governance-api, 3.11)
ui
```

When a package is not affected, its matrix job exits quickly after the routing step instead of installing Poetry dependencies and running tests.

The final `ci-required` job is a stable aggregate gate. It succeeds only when the routed jobs either pass or are intentionally skipped.

## Routing rules

| Changed area | CI behavior |
| --- | --- |
| `packages/skeinrank-core/**` | Run core package tests and Python lint. |
| `packages/skeinrank-server/**` | Run server package tests and Python lint. |
| `packages/skeinrank-provider-elasticsearch/**` | Run Elasticsearch provider tests and Python lint. |
| `packages/skeinrank-governance/**` | Run governance package tests and Python lint. |
| `packages/skeinrank-governance-api/**` | Run governance API tests and Python lint. |
| `packages/skeinrank-ui/**` | Run UI typecheck, tests, and build. |
| `docs/**`, `README.md`, Compose, Docker, Helm, examples, scripts | Run governance API contract tests because those tests validate docs/deployment contracts. |
| `.github/workflows/ci.yml`, `ruff.toml`, `requirements-dev.txt`, `.pre-commit-config.yaml` | Force all routed CI jobs. |

## Docker and Helm workflows

Docker image publishing is not part of normal PR CI. It remains in:

```text
.github/workflows/docker-publish.yml
```

It runs only for `v*` tags or manual `workflow_dispatch`.

Helm chart lint/render checks stay in:

```text
.github/workflows/helm-chart.yml
```

The optional live Kubernetes smoke test stays manual-only in:

```text
.github/workflows/helm-smoke.yml
```

Do not add the optional kind smoke workflow as a required branch-protection check until the chart is stable enough for every Helm PR.

## Branch protection recommendation

The safest minimal required check is:

```text
ci-required
```

Keeping the older individual checks is also supported because the jobs keep their existing names and skipped routed jobs complete successfully. For lower branch-rule maintenance, prefer `ci-required` once the workflow has passed on `main`.
