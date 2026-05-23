#!/usr/bin/env bash
set -euo pipefail

API_URL="${SKEINRANK_HEADLESS_API_URL:-http://127.0.0.1:8010}"
DICTIONARY_FILE="${SKEINRANK_HEADLESS_DICTIONARY_FILE:-examples/migration/console_dictionary.example.json}"
SNAPSHOT_OUTPUT="${SKEINRANK_HEADLESS_SNAPSHOT_OUTPUT:-snapshots/infra_incidents.binding.v1.json}"
BINDING_NAME="${SKEINRANK_HEADLESS_BINDING_NAME:-infra incidents local runtime $(date +%s)}"

wait_for_ready() {
  for _ in $(seq 1 60); do
    if curl -fsS "${API_URL}/readyz" >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done
  echo "SkeinRank headless API did not become ready: ${API_URL}/readyz" >&2
  return 1
}

json_field() {
  python -c 'import json,sys; print(json.load(sys.stdin)[sys.argv[1]])' "$1"
}

mkdir -p "$(dirname "${SNAPSHOT_OUTPUT}")"

printf 'Waiting for headless API at %s...\n' "${API_URL}"
wait_for_ready

printf 'Applying dictionary spec v1 from %s...\n' "${DICTIONARY_FILE}"
curl -fsS -X POST "${API_URL}/v1/headless/dictionaries/apply" \
  -H "Content-Type: application/json" \
  --data-binary "@${DICTIONARY_FILE}" \
  | python -m json.tool

printf 'Creating local runtime binding...\n'
BINDING_RESPONSE="$(
  python - "$BINDING_NAME" <<'PY' | curl -fsS -X POST "${API_URL}/v1/governance/elasticsearch/bindings" \
    -H "Content-Type: application/json" \
    --data-binary @-
import json
import sys

print(json.dumps({
    "name": sys.argv[1],
    "profile_name": "infra_incidents",
    "description": "Headless golden path binding for runtime artifact export.",
    "index_name": "infra_incidents_docs",
    "text_fields": ["title", "body"],
    "target_field": "skeinrank",
    "mode": "dry_run",
    "write_strategy": "reindex_alias_swap",
    "is_enabled": True,
}))
PY
)"
BINDING_ID="$(printf '%s' "${BINDING_RESPONSE}" | json_field id)"
printf 'Created binding_id=%s\n' "${BINDING_ID}"

printf 'Exporting runtime snapshot artifact to %s...\n' "${SNAPSHOT_OUTPUT}"
curl -fsS "${API_URL}/v1/headless/snapshots/export?binding_id=${BINDING_ID}&snapshot_version=infra_incidents@v1" \
  -o "${SNAPSHOT_OUTPUT}"

printf 'Inspecting exported artifact...\n'
python - "${SNAPSHOT_OUTPUT}" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
artifact = json.loads(path.read_text(encoding="utf-8"))
summary = {
    "schema_version": artifact.get("schema_version"),
    "artifact_type": artifact.get("artifact_type"),
    "binding_id": artifact.get("binding", {}).get("id"),
    "profile_name": artifact.get("profile", {}).get("name"),
    "snapshot_version": artifact.get("manifest", {}).get("snapshot_version"),
    "alias_entries_total": artifact.get("manifest", {}).get("alias_entries_total"),
    "path": str(path.resolve()),
}
print(json.dumps(summary, indent=2, sort_keys=True))
PY

printf '\nHeadless golden path complete. Artifact: %s\n' "${SNAPSHOT_OUTPUT}"
