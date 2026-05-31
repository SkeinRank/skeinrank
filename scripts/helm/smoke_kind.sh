#!/usr/bin/env bash
set -euo pipefail

# Optional Helm smoke test for the SkeinRank alpha chart.
#
# This script creates a temporary kind cluster, installs the chart with
# zero-replica smoke values, verifies that the expected Kubernetes resources are
# accepted by the API server, and deletes the cluster on exit.
#
# It intentionally does not start application pods or external dependencies.

CLUSTER_NAME="${KIND_CLUSTER_NAME:-skeinrank-helm-smoke}"
NAMESPACE="${SKEINRANK_HELM_NAMESPACE:-skeinrank}"
RELEASE_NAME="${SKEINRANK_HELM_RELEASE:-skeinrank}"
CHART_DIR="${SKEINRANK_HELM_CHART_DIR:-charts/skeinrank}"
SMOKE_VALUES="${SKEINRANK_HELM_SMOKE_VALUES:-charts/skeinrank/values-kind-smoke.yaml}"
IMAGE_TAG="${SKEINRANK_IMAGE_TAG:-v0.10.0-beta.1}"
KEEP_CLUSTER="${SKEINRANK_KEEP_KIND_CLUSTER:-0}"
KIND_WAIT="${KIND_WAIT:-120s}"
HELM_TIMEOUT="${SKEINRANK_HELM_TIMEOUT:-120s}"

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "error: required command '$1' is not installed or not on PATH" >&2
    exit 127
  fi
}

require_command docker
require_command kind
require_command kubectl
require_command helm

if [[ ! -d "$CHART_DIR" ]]; then
  echo "error: chart directory not found: $CHART_DIR" >&2
  exit 1
fi

if [[ ! -f "$SMOKE_VALUES" ]]; then
  echo "error: smoke values file not found: $SMOKE_VALUES" >&2
  exit 1
fi

cleanup() {
  if [[ "$KEEP_CLUSTER" == "1" ]]; then
    echo "==> Keeping kind cluster '$CLUSTER_NAME' because SKEINRANK_KEEP_KIND_CLUSTER=1"
    return
  fi

  if kind get clusters 2>/dev/null | grep -qx "$CLUSTER_NAME"; then
    echo "==> Deleting kind cluster '$CLUSTER_NAME'"
    kind delete cluster --name "$CLUSTER_NAME"
  fi
}
trap cleanup EXIT

if kind get clusters 2>/dev/null | grep -qx "$CLUSTER_NAME"; then
  echo "==> Reusing existing kind cluster '$CLUSTER_NAME'"
else
  echo "==> Creating kind cluster '$CLUSTER_NAME'"
  kind create cluster --name "$CLUSTER_NAME" --wait "$KIND_WAIT"
fi

kubectl cluster-info --context "kind-$CLUSTER_NAME" >/dev/null

if kubectl get namespace "$NAMESPACE" >/dev/null 2>&1; then
  echo "==> Namespace '$NAMESPACE' already exists"
else
  echo "==> Creating namespace '$NAMESPACE'"
  kubectl create namespace "$NAMESPACE"
fi

echo "==> Linting Helm chart"
helm lint "$CHART_DIR"

RENDERED_MANIFEST="${TMPDIR:-/tmp}/skeinrank-kind-smoke.yaml"
echo "==> Rendering chart with smoke values"
helm template "$RELEASE_NAME" "$CHART_DIR" \
  --namespace "$NAMESPACE" \
  -f "$SMOKE_VALUES" \
  --set "image.tag=$IMAGE_TAG" \
  > "$RENDERED_MANIFEST"

grep -q 'kind: Deployment' "$RENDERED_MANIFEST"
grep -q 'name: skeinrank-governance-api' "$RENDERED_MANIFEST"
grep -q 'name: skeinrank-governance-worker' "$RENDERED_MANIFEST"
grep -q 'name: skeinrank-ui' "$RENDERED_MANIFEST"
if grep -q 'kind: Job' "$RENDERED_MANIFEST"; then
  echo "error: smoke values should disable the migration Job" >&2
  exit 1
fi

echo "==> Installing chart into kind cluster"
helm upgrade --install "$RELEASE_NAME" "$CHART_DIR" \
  --namespace "$NAMESPACE" \
  -f "$SMOKE_VALUES" \
  --set "image.tag=$IMAGE_TAG" \
  --wait \
  --timeout "$HELM_TIMEOUT"

echo "==> Verifying rendered Kubernetes resources"
kubectl -n "$NAMESPACE" get deploy,svc,configmap,secret
kubectl -n "$NAMESPACE" get deployment "${RELEASE_NAME}-governance-api" >/dev/null
kubectl -n "$NAMESPACE" get deployment "${RELEASE_NAME}-governance-worker" >/dev/null
kubectl -n "$NAMESPACE" get deployment "${RELEASE_NAME}-ui" >/dev/null
kubectl -n "$NAMESPACE" get service "${RELEASE_NAME}-governance-api" >/dev/null
kubectl -n "$NAMESPACE" get service "${RELEASE_NAME}-ui" >/dev/null
kubectl -n "$NAMESPACE" get configmap "${RELEASE_NAME}-config" >/dev/null
kubectl -n "$NAMESPACE" get secret "${RELEASE_NAME}-secrets" >/dev/null

for deployment in governance-api governance-worker ui; do
  replicas="$(kubectl -n "$NAMESPACE" get deployment "${RELEASE_NAME}-${deployment}" -o jsonpath='{.spec.replicas}')"
  if [[ "$replicas" != "0" ]]; then
    echo "error: expected ${RELEASE_NAME}-${deployment} to have 0 replicas in smoke mode, got $replicas" >&2
    exit 1
  fi
done

if kubectl -n "$NAMESPACE" get job "${RELEASE_NAME}-governance-migrate" >/dev/null 2>&1; then
  echo "error: migration Job should not be rendered in smoke mode" >&2
  exit 1
fi

echo "==> Helm kind smoke test passed"
