#!/usr/bin/env bash
set -euo pipefail

API_URL="${SKEINRANK_SMOKE_API_URL:-http://127.0.0.1:8010}"
USERNAME="${SKEINRANK_SMOKE_ADMIN_USERNAME:-admin}"
PASSWORD="${SKEINRANK_SMOKE_ADMIN_PASSWORD:-change-me}"

json_get() {
  python -c 'import json,sys; print(json.load(sys.stdin)[sys.argv[1]])' "$1"
}

printf 'Checking livez at %s/livez\n' "$API_URL"
curl -fsS "$API_URL/livez" | python -m json.tool >/dev/null

printf 'Checking readyz at %s/readyz\n' "$API_URL"
READY_STATUS=$(curl -fsS "$API_URL/readyz" | json_get status)
if [ "$READY_STATUS" != "ok" ]; then
  echo "API is not ready: $READY_STATUS" >&2
  curl -fsS "$API_URL/readyz" | python -m json.tool >&2
  exit 1
fi

printf 'Logging in as %s\n' "$USERNAME"
ADMIN_TOKEN=$(
  curl -fsS -X POST "$API_URL/v1/auth/login" \
    -H "Content-Type: application/json" \
    -d "{\"username\":\"$USERNAME\",\"password\":\"$PASSWORD\"}" \
  | json_get access_token
)

printf 'Checking authenticated user\n'
curl -fsS "$API_URL/v1/auth/me" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  | python -m json.tool >/dev/null

printf 'Checking Elasticsearch connection status\n'
curl -fsS "$API_URL/v1/governance/elasticsearch/connection/status" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  | python -m json.tool >/dev/null

printf 'SkeinRank dev stack smoke test passed.\n'
