# Optional kind Helm smoke test

SkeinRank includes an optional kind-based smoke test for the alpha Helm chart.
It validates that Kubernetes accepts the rendered manifests without starting the
application pods or requiring PostgreSQL, RabbitMQ, or Elasticsearch/OpenSearch.

This is intentionally lighter than a full end-to-end Kubernetes environment.
The chart still expects external runtime dependencies for real application
rollouts.

## What the smoke test checks

The smoke test:

1. Creates a temporary kind cluster.
2. Runs `helm lint charts/skeinrank`.
3. Renders the chart with `charts/skeinrank/values-kind-smoke.yaml`.
4. Installs the chart into the kind cluster with zero replicas.
5. Verifies the expected Deployments, Services, ConfigMap, and Secret exist.
6. Verifies the migration Job is disabled in smoke mode.
7. Deletes the kind cluster on exit.

The smoke values file keeps the install safe and fast:

```text
charts/skeinrank/values-kind-smoke.yaml
```

It sets:

```yaml
governanceApi:
  replicaCount: 0
governanceWorker:
  replicaCount: 0
ui:
  replicaCount: 0
migrations:
  enabled: false
```

## Local run

Install the required tools:

```bash
brew install kind kubectl helm
```

Docker Desktop must be running because kind creates Kubernetes nodes as Docker
containers.

Run the smoke test from the repository root:

```bash
bash scripts/helm/smoke_kind.sh
```

To test a specific published image tag:

```bash
SKEINRANK_IMAGE_TAG=v0.10.0-beta.1 bash scripts/helm/smoke_kind.sh
```

To keep the cluster for debugging:

```bash
SKEINRANK_KEEP_KIND_CLUSTER=1 bash scripts/helm/smoke_kind.sh
```

Then clean it manually:

```bash
kind delete cluster --name skeinrank-helm-smoke
```

## GitHub Actions

The workflow is intentionally manual:

```text
.github/workflows/helm-smoke.yml
```

Run it from:

```text
GitHub → Actions → helm-smoke → Run workflow
```

Pass the image tag to render, for example:

```text
v0.10.0-beta.1
```

The workflow is not a required branch-protection check. Use it before release
publishing or when changing Helm templates in ways that should be verified
against a live Kubernetes API server.

## k3d alternative

The official smoke script uses kind because it is simple in GitHub Actions. For
local Kubernetes experiments, k3d is also fine. Use the same chart and values:

```bash
k3d cluster create skeinrank-helm-smoke
kubectl create namespace skeinrank
helm upgrade --install skeinrank charts/skeinrank \
  --namespace skeinrank \
  -f charts/skeinrank/values-kind-smoke.yaml \
  --set image.tag=v0.10.0-beta.1
k3d cluster delete skeinrank-helm-smoke
```

The k3d example is for local inspection only; the maintained smoke path is the
kind script.
