# Helm production values guide

This page documents the production-oriented knobs for the alpha SkeinRank Helm
chart. The chart still installs only the SkeinRank control-plane workloads and
expects external PostgreSQL, RabbitMQ, and Elasticsearch/OpenSearch.

Use the example override file as a starting point:

```bash
cp charts/skeinrank/values-production.example.yaml /tmp/skeinrank-values.yaml
```

Then edit `/tmp/skeinrank-values.yaml` with your real hosts, resource budgets,
Secret name, and ingress hosts.

## Production install shape

Create a namespace:

```bash
kubectl create namespace skeinrank
```

Create the runtime Secret outside Helm:

```bash
kubectl -n skeinrank create secret generic skeinrank-runtime-secrets \
  --from-literal=SKEINRANK_GOVERNANCE_API_DATABASE_URL='postgresql+psycopg://USER:PASSWORD@postgres.example:5432/app_db' \
  --from-literal=SKEINRANK_GOVERNANCE_API_ADMIN_PASSWORD='change-me' \
  --from-literal=SKEINRANK_GOVERNANCE_API_CELERY_BROKER_URL='amqp://USER:PASSWORD@rabbitmq.example:5672//' \
  --from-literal=SKEINRANK_GOVERNANCE_API_ELASTICSEARCH_USERNAME='' \
  --from-literal=SKEINRANK_GOVERNANCE_API_ELASTICSEARCH_PASSWORD='' \
  --from-literal=SKEINRANK_GOVERNANCE_API_ELASTICSEARCH_API_KEY=''
```

Render the chart with production values before installing:

```bash
helm lint charts/skeinrank
helm template skeinrank charts/skeinrank \
  --namespace skeinrank \
  -f /tmp/skeinrank-values.yaml \
  >/tmp/skeinrank-production.yaml
```

Install or upgrade:

```bash
helm upgrade --install skeinrank charts/skeinrank \
  --namespace skeinrank \
  -f /tmp/skeinrank-values.yaml
```

## Secret strategy

For production, prefer:

```yaml
secrets:
  existingSecret: skeinrank-runtime-secrets
```

When `secrets.existingSecret` is set, the chart does not render Secret
`stringData`. The Secret must contain the same keys used by the alpha chart:

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

## External dependencies

The chart expects these services to exist before install:

| Dependency | Helm value / Secret key |
| --- | --- |
| PostgreSQL | `SKEINRANK_GOVERNANCE_API_DATABASE_URL` in the runtime Secret |
| RabbitMQ | `SKEINRANK_GOVERNANCE_API_CELERY_BROKER_URL` in the runtime Secret |
| Elasticsearch/OpenSearch | `config.elasticsearchUrl` plus optional credentials in the runtime Secret |

This keeps the alpha chart small and avoids bundling stateful dependencies that
would need their own backup, persistence, and upgrade policy.

## Ingress

Ingress is disabled by default. Enable it only when an ingress controller is
installed and DNS is configured.

```yaml
ingress:
  enabled: true
  className: nginx
  ui:
    enabled: true
    host: skeinrank.example.com
    tlsSecretName: skeinrank-ui-tls
  api:
    enabled: true
    host: api.skeinrank.example.com
    tlsSecretName: skeinrank-api-tls
```

The ingress template routes UI traffic to the UI service and API traffic to the
Governance API service. Keep `config.corsOrigins` and
`config.uiGovernanceApiUrl` aligned with these hosts.

## Resource requests and limits

Use explicit resource budgets before running in a shared cluster:

```yaml
governanceApi:
  replicaCount: 2
  resources:
    requests:
      cpu: 250m
      memory: 512Mi
    limits:
      cpu: 1000m
      memory: 1Gi

ui:
  replicaCount: 2
  resources:
    requests:
      cpu: 100m
      memory: 128Mi
    limits:
      cpu: 500m
      memory: 256Mi
```

The worker is intentionally conservative by default. Increase worker
concurrency only after RabbitMQ, PostgreSQL, and Elasticsearch/OpenSearch have
sufficient capacity.

## Pod disruption budgets

PodDisruptionBudgets are disabled by default so the alpha chart works in local
single-node clusters. Enable them for multi-node production-style clusters:

```yaml
podDisruptionBudgets:
  governanceApi:
    enabled: true
    minAvailable: 1
  ui:
    enabled: true
    minAvailable: 1
```

Avoid enabling a PDB for a single-replica worker until you understand how your
cluster handles voluntary disruptions.

## Migration job

The migration job is enabled by default and runs:

```text
python -m skeinrank_governance_api.migrations upgrade head
```

In alpha values it is rendered as a regular release resource, not a Helm hook.
Keep `migrations.hook.enabled=false` unless you have verified the hook behavior
for your release process.

## Preflight checklist

Before using the chart outside local testing:

- Create the runtime Secret outside Helm.
- Point `config.elasticsearchUrl` to the in-cluster reachable endpoint.
- Align `config.corsOrigins` and `config.uiGovernanceApiUrl` with ingress hosts.
- Set resource requests and limits for API, UI, worker, and migration job.
- Decide whether PodDisruptionBudgets fit the cluster size.
- Render the chart with `helm template` and inspect the manifests.
- Run the Compose beta stack first when evaluating SkeinRank on one machine.

An optional kind smoke test is available in [`helm-smoke-test.md`](helm-smoke-test.md). It validates chart installation against a live Kubernetes API server without starting application pods or external dependencies.
