# Helm chart alpha

SkeinRank includes an alpha Helm chart for Kubernetes installs that use the
published GHCR images:

- `ghcr.io/skeinrank/skeinrank-governance-api:<tag>`
- `ghcr.io/skeinrank/skeinrank-governance-worker:<tag>`
- `ghcr.io/skeinrank/skeinrank-ui:<tag>`

The chart is intentionally small in this first alpha. It installs the SkeinRank
control-plane workloads and expects PostgreSQL, RabbitMQ, and Elasticsearch or
OpenSearch to already exist.

## What the chart installs

The chart lives under [`charts/skeinrank`](../../charts/skeinrank) and renders:

- `Deployment` + `Service` for the Governance API.
- `Deployment` for the Governance worker.
- `Deployment` + `Service` for the React UI.
- A migration `Job` that runs `python -m skeinrank_governance_api.migrations upgrade head`.
- A `ConfigMap` for non-secret runtime settings.
- A `Secret` for database, broker, admin password, and optional Elasticsearch credentials.
- A `ServiceAccount` by default.

It does **not** deploy PostgreSQL, RabbitMQ, Elasticsearch, OpenSearch,
Prometheus, or Grafana. Ingress and PodDisruptionBudget resources are optional
and disabled by default.

## Render locally

```bash
helm lint charts/skeinrank
helm template skeinrank charts/skeinrank --namespace skeinrank
```

The default values use the public beta image tag:

```text
v0.10.0-beta.1
```

Override it when testing a different release:

```bash
helm template skeinrank charts/skeinrank \
  --set image.tag=v0.10.0-beta.1
```

## Minimal install shape

Create a namespace:

```bash
kubectl create namespace skeinrank
```

Create an external Secret for production-style installs:

```bash
kubectl -n skeinrank create secret generic skeinrank-runtime-secrets \
  --from-literal=SKEINRANK_GOVERNANCE_API_DATABASE_URL='postgresql+psycopg://USER:PASSWORD@postgres.example:5432/app_db' \
  --from-literal=SKEINRANK_GOVERNANCE_API_ADMIN_PASSWORD='change-me' \
  --from-literal=SKEINRANK_GOVERNANCE_API_CELERY_BROKER_URL='amqp://USER:PASSWORD@rabbitmq.example:5672//' \
  --from-literal=SKEINRANK_GOVERNANCE_API_ELASTICSEARCH_USERNAME='' \
  --from-literal=SKEINRANK_GOVERNANCE_API_ELASTICSEARCH_PASSWORD='' \
  --from-literal=SKEINRANK_GOVERNANCE_API_ELASTICSEARCH_API_KEY=''
```

Install with the existing Secret:

```bash
helm upgrade --install skeinrank charts/skeinrank \
  --namespace skeinrank \
  --set secrets.existingSecret=skeinrank-runtime-secrets \
  --set config.elasticsearchUrl='http://elasticsearch.example:9200' \
  --set config.corsOrigins='http://localhost:5173' \
  --set config.uiGovernanceApiUrl='http://localhost:8010'
```

Port-forward for local inspection:

```bash
kubectl -n skeinrank port-forward svc/skeinrank-governance-api 8010:8010
kubectl -n skeinrank port-forward svc/skeinrank-ui 5173:5173
```

Then check:

```bash
curl http://127.0.0.1:8010/livez
open http://127.0.0.1:5173
```

## Values that matter first

| Value | Purpose |
| --- | --- |
| `image.tag` | Release image tag, for example `v0.10.0-beta.1`. |
| `secrets.existingSecret` | Existing Kubernetes Secret containing the required runtime secret keys. |
| `config.elasticsearchUrl` | Elasticsearch/OpenSearch endpoint seen from the cluster. |
| `config.corsOrigins` | Browser origins allowed to call the Governance API. |
| `config.uiGovernanceApiUrl` | Governance API URL used by the UI. |
| `governanceApi.resources` | API CPU/memory requests and limits. |
| `governanceWorker.resources` | Worker CPU/memory requests and limits. |
| `ui.resources` | UI CPU/memory requests and limits. |
| `ingress.enabled` | Optional ingress for the UI and Governance API. |
| `podDisruptionBudgets.*.enabled` | Optional PDBs for multi-node clusters. |
| `governanceApi.service.type` | Service type for the API; defaults to `ClusterIP`. |
| `ui.service.type` | Service type for the UI; defaults to `ClusterIP`. |

## Secret contract

When `secrets.existingSecret` is set, the Secret must provide these keys:

```text
SKEINRANK_GOVERNANCE_API_DATABASE_URL
SKEINRANK_GOVERNANCE_API_ADMIN_PASSWORD
SKEINRANK_GOVERNANCE_API_CELERY_BROKER_URL
SKEINRANK_GOVERNANCE_API_ELASTICSEARCH_USERNAME
SKEINRANK_GOVERNANCE_API_ELASTICSEARCH_PASSWORD
SKEINRANK_GOVERNANCE_API_ELASTICSEARCH_API_KEY
```

The Elasticsearch username, password, and API key values may be empty when the
cluster does not require authentication.

## Production-oriented values

A production-oriented override example is available at:

```text
charts/skeinrank/values-production.example.yaml
```

It demonstrates:

- `secrets.existingSecret` for externally managed runtime secrets.
- resource requests and limits for API, worker, UI, and migration job.
- optional UI/API ingress hosts.
- optional PodDisruptionBudgets for multi-node clusters.

See [`helm-production.md`](helm-production.md) for the production values guide and
preflight checklist.

## Optional kind smoke test

For Kubernetes API validation without starting application pods, use the optional
kind smoke test:

```bash
bash scripts/helm/smoke_kind.sh
```

The smoke test installs the chart with zero replicas and disables the migration
Job through:

```text
charts/skeinrank/values-kind-smoke.yaml
```

See [`helm-smoke-test.md`](helm-smoke-test.md) for local and GitHub Actions usage.

## Current alpha limitations

- External dependencies are required; the chart does not bundle databases or search backends.
- No persistent volumes are rendered by this chart.
- Ingress is optional but still requires your own controller, DNS, and TLS strategy.
- The migration job is rendered as a regular release resource by default; Helm hook mode is available but disabled in alpha values.
- The chart is validated with `helm lint` and `helm template`; an optional kind smoke test is available in [`helm-smoke-test.md`](helm-smoke-test.md).

For one-machine evaluation, use the release Compose stack first:
[`release-compose.md`](release-compose.md).
