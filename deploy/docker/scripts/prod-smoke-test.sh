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

TMP_FILES=()

cleanup() {
  local file
  for file in "${TMP_FILES[@]}"; do
    rm -f "$file"
  done
}
trap cleanup EXIT

make_temp_file() {
  local file
  file="$(mktemp)"
  TMP_FILES+=("$file")
  printf '%s' "$file"
}

print_json_file() {
  python -m json.tool "$1"
}

json_field_file() {
  python -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))[sys.argv[2]])' "$1" "$2"
}

json_get_file() {
  python -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8")).get(sys.argv[2]))' "$1" "$2"
}

fetch_json() {
  local path="$1"
  local output_file="$2"

  if ! curl -fsS --connect-timeout 5 --max-time 20 -o "$output_file" "${API_URL}${path}"; then
    echo "API endpoint ${path} is not reachable at ${API_URL}${path}." >&2
    echo "Check that the production Compose stack is running, for example: make prod-up" >&2
    exit 1
  fi

  if ! python -m json.tool "$output_file" >/dev/null 2>&1; then
    echo "API endpoint ${path} did not return valid JSON." >&2
    cat "$output_file" >&2 || true
    exit 1
  fi
}

fetch_text() {
  local path="$1"
  local output_file="$2"

  if ! curl -fsS --connect-timeout 5 --max-time 20 -o "$output_file" "${API_URL}${path}"; then
    echo "API endpoint ${path} is not reachable at ${API_URL}${path}." >&2
    echo "Check that the production Compose stack is running, for example: make prod-up" >&2
    exit 1
  fi
}

require_status_ok() {
  local path="$1"
  local payload_file
  local status

  payload_file="$(make_temp_file)"
  fetch_json "$path" "$payload_file"
  status="$(json_field_file "$payload_file" status)"
  if [ "$status" != "ok" ]; then
    echo "Unexpected status from ${path}: ${status}" >&2
    print_json_file "$payload_file" >&2
    exit 1
  fi
}

printf 'Checking production liveness at %s/livez\n' "$API_URL"
require_status_ok /livez

printf 'Checking production health at %s/healthz\n' "$API_URL"
require_status_ok /healthz

printf 'Checking production readiness at %s/readyz\n' "$API_URL"
READYZ_PAYLOAD_FILE="$(make_temp_file)"
fetch_json /readyz "$READYZ_PAYLOAD_FILE"
READYZ_STATUS="$(json_get_file "$READYZ_PAYLOAD_FILE" status)"
if [ "$READYZ_STATUS" != "ok" ]; then
  if [ "$STRICT_READY" = "true" ]; then
    echo "Unexpected status from /readyz in strict mode: ${READYZ_STATUS}" >&2
    print_json_file "$READYZ_PAYLOAD_FILE" >&2
    exit 1
  fi
  echo "Warning: /readyz returned ${READYZ_STATUS}; continuing because strict readiness is disabled." >&2
  print_json_file "$READYZ_PAYLOAD_FILE" >&2
fi

printf 'Checking schema health at %s/schema/health\n' "$API_URL"
SCHEMA_PAYLOAD_FILE="$(make_temp_file)"
fetch_json /schema/health "$SCHEMA_PAYLOAD_FILE"
SCHEMA_OK="$(json_get_file "$SCHEMA_PAYLOAD_FILE" ok)"
if [ "$SCHEMA_OK" != "True" ]; then
  echo "Schema health is not ok" >&2
  print_json_file "$SCHEMA_PAYLOAD_FILE" >&2
  exit 1
fi

printf 'Checking metrics endpoint at %s/metrics\n' "$API_URL"
METRICS_PAYLOAD_FILE="$(make_temp_file)"
fetch_text /metrics "$METRICS_PAYLOAD_FILE"
grep -q 'skeinrank_database_up' "$METRICS_PAYLOAD_FILE"
grep -q 'skeinrank_schema_ok' "$METRICS_PAYLOAD_FILE"

if [ -n "$PASSWORD" ]; then
  printf 'Checking authenticated troubleshooting report as %s\n' "$USERNAME"
  LOGIN_PAYLOAD="$(python - "${USERNAME}" "${PASSWORD}" <<'PY'
import json
import sys

print(json.dumps({"username": sys.argv[1], "password": sys.argv[2]}))
PY
  )"
  LOGIN_RESPONSE_FILE="$(make_temp_file)"
  if ! curl -fsS --connect-timeout 5 --max-time 20 -X POST "${API_URL}/v1/auth/login" \
      -H "Content-Type: application/json" \
      --data-binary "${LOGIN_PAYLOAD}" \
      -o "$LOGIN_RESPONSE_FILE"; then
    echo "Authentication endpoint is not reachable at ${API_URL}/v1/auth/login." >&2
    exit 1
  fi
  if ! python -m json.tool "$LOGIN_RESPONSE_FILE" >/dev/null 2>&1; then
    echo "Authentication endpoint did not return valid JSON." >&2
    cat "$LOGIN_RESPONSE_FILE" >&2 || true
    exit 1
  fi
  ADMIN_TOKEN="$(json_field_file "$LOGIN_RESPONSE_FILE" access_token)"

  TROUBLESHOOTING_RESPONSE_FILE="$(make_temp_file)"
  if ! curl -fsS --connect-timeout 5 --max-time 20 "${API_URL}/v1/ops/troubleshooting/report" \
      -H "Authorization: Bearer ${ADMIN_TOKEN}" \
      -o "$TROUBLESHOOTING_RESPONSE_FILE"; then
    echo "Troubleshooting report endpoint is not reachable at ${API_URL}/v1/ops/troubleshooting/report." >&2
    exit 1
  fi
  python -m json.tool "$TROUBLESHOOTING_RESPONSE_FILE" >/dev/null
else
  echo "Skipping authenticated troubleshooting report check: no admin password provided." >&2
fi

printf 'SkeinRank production-oriented Compose smoke test passed.\n'
