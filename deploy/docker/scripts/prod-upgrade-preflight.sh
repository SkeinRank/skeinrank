#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
ENV_FILE="${SKEINRANK_PROD_ENV_FILE:-${REPO_ROOT}/.env}"
COMPOSE_FILE="${SKEINRANK_PROD_COMPOSE_FILE:-${REPO_ROOT}/docker-compose.prod.yml}"
STRICT_ENV="${SKEINRANK_PROD_PREFLIGHT_STRICT_ENV:-false}"
RUN_BACKUP="true"
RUN_SCHEMA_CHECK="true"

usage() {
  cat <<'USAGE'
Usage: deploy/docker/scripts/prod-upgrade-preflight.sh [options]

Runs production-ish Compose preflight checks before an upgrade.

Options:
  --strict-env       Treat env validation warnings as failures.
  --no-backup       Skip the portable governance backup export step.
  --no-schema-check Skip the Alembic/schema health one-shot step.
  -h, --help        Show this help.

Environment:
  SKEINRANK_PROD_ENV_FILE            Path to .env file. Defaults to repo .env.
  SKEINRANK_PROD_COMPOSE_FILE        Path to docker-compose.prod.yml.
  SKEINRANK_PROD_PREFLIGHT_STRICT_ENV=true enables strict env validation.
USAGE
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --strict-env)
      STRICT_ENV="true"
      ;;
    --no-backup)
      RUN_BACKUP="false"
      ;;
    --no-schema-check)
      RUN_SCHEMA_CHECK="false"
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

if [ ! -f "$ENV_FILE" ]; then
  echo "Production env file not found: $ENV_FILE" >&2
  echo "Create it from .env.production.example and replace placeholder secrets first." >&2
  exit 1
fi

if [ ! -f "$COMPOSE_FILE" ]; then
  echo "Production compose file not found: $COMPOSE_FILE" >&2
  exit 1
fi

ENV_ARGS=(--file "$ENV_FILE")
if [ "$STRICT_ENV" = "true" ]; then
  ENV_ARGS+=(--strict)
fi

COMPOSE=(docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE")

cd "$REPO_ROOT"

printf 'Running production env validation for %s\n' "$ENV_FILE"
(
  cd packages/skeinrank-governance-api
  poetry run python -m skeinrank_governance_api.env_validation validate "${ENV_ARGS[@]}"
)

printf 'Validating production Compose config with %s\n' "$COMPOSE_FILE"
"${COMPOSE[@]}" config >/dev/null

if [ "$RUN_BACKUP" = "true" ]; then
  printf 'Exporting pre-upgrade governance backup through Compose ops profile\n'
  "${COMPOSE[@]}" --profile ops run --rm governance-backup-export
else
  echo "Skipping backup export because --no-backup was provided." >&2
fi

if [ "$RUN_SCHEMA_CHECK" = "true" ]; then
  printf 'Checking migrated schema through Compose ops profile\n'
  "${COMPOSE[@]}" --profile ops run --rm governance-schema-check
else
  echo "Skipping schema check because --no-schema-check was provided." >&2
fi

printf 'SkeinRank production upgrade preflight passed.\n'
