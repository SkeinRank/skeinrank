#!/usr/bin/env bash
set -euo pipefail

API_URL="${SKEINRANK_PROD_SMOKE_API_URL:-http://127.0.0.1:8010}"
STRICT_READY="${SKEINRANK_PROD_SMOKE_STRICT_READY:-false}"
USERNAME="${SKEINRANK_PROD_SMOKE_ADMIN_USERNAME:-${SKEINRANK_GOVERNANCE_API_ADMIN_USERNAME:-admin}}"
PASSWORD="${SKEINRANK_PROD_SMOKE_ADMIN_PASSWORD:-${SKEINRANK_GOVERNANCE_API_ADMIN_PASSWORD:-}}"

usage() {
  cat <<'EOF'
Usage: deploy/docker/scripts/prod-smoke-test.sh [--strict]

Checks production-ish Compose endpoints. By default /readyz is reported as a
warning so first local starts are not blocked by optional external services such
as Elasticsearch. Use --strict or SKEINRANK_PROD_SMOKE_STRICT_READY=true when
external dependencies must be ready.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --strict)
      STRICT_READY="true"
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

json_field() {
  python -c 'import json,sys; print(json.load(sys.stdin)[sys.argv[1]])' "$1"
}

json_get() {
  python -c 'import json,sys; print(json.load(sys.stdin).get(sys.argv[1]))' "$1"
}

require_status_ok() {
  local path="$1"
  local status
  status="$(curl -fsS "${API_URL}${path}" | json_field status)"
  if [ "$status" != "ok" ]; then
    echo "Unexpected status from ${path}: ${status}" >&2
    curl -fsS "${API_URL}${path}" | python -m json.tool >&2
    exit 1
  fi
}

printf 'Checking production liveness at %s/livez
' "$API_URL"
require_status_ok /livez

printf 'Checking production health at %s/healthz
' "$API_URL"
require_status_ok /healthz

printf 'Checking production readiness at %s/readyz
' "$API_URL"
READYZ_PAYLOAD="$(curl -fsS "${API_URL}/readyz")"
READYZ_STATUS="$(printf '%s' "$READYZ_PAYLOAD" | json_get status)"
if [ "$READYZ_STATUS" != "ok" ]; then
  if [ "$STRICT_READY" = "true" ]; then
    echo "Unexpected status from /readyz in strict mode: ${READYZ_STATUS}" >&2
    printf '%s' "$READYZ_PAYLOAD" | python -m json.tool >&2
    exit 1
  fi
  echo "Warning: /readyz returned ${READYZ_STATUS}; continuing because strict readiness is disabled." >&2
  printf '%s' "$READYZ_PAYLOAD" | python -m json.tool >&2
fi

printf 'Checking schema health at %s/schema/health
' "$API_URL"
SCHEMA_OK="$(curl -fsS "${API_URL}/schema/health" | python -c 'import json,sys; print(json.load(sys.stdin).get("ok"))')"
if [ "$SCHEMA_OK" != "True" ]; then
  echo "Schema health is not ok" >&2
  curl -fsS "${API_URL}/schema/health" | python -m json.tool >&2
  exit 1
fi

printf 'Checking metrics endpoint at %s/metrics
' "$API_URL"
curl -fsS "${API_URL}/metrics" | grep -q 'skeinrank_database_up'
curl -fsS "${API_URL}/metrics" | grep -q 'skeinrank_schema_ok'

if [ -n "$PASSWORD" ]; then
  printf 'Checking authenticated troubleshooting report as %s
' "$USERNAME"
  ADMIN_TOKEN="$(
    curl -fsS -X POST "${API_URL}/v1/auth/login"       -H "Content-Type: application/json"       -d "{"username":"${USERNAME}","password":"${PASSWORD}"}"     | json_field access_token
  )"
  curl -fsS "${API_URL}/v1/ops/troubleshooting/report"     -H "Authorization: Bearer ${ADMIN_TOKEN}"     | python -m json.tool >/dev/null
else
  echo "Skipping authenticated troubleshooting report check: no admin password provided." >&2
fi

printf 'SkeinRank production-oriented Compose smoke test passed.
'
