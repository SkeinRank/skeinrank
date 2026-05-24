#!/usr/bin/env bash
set -euo pipefail

ACTION="${1:-run}"
COMPOSE=(
  docker compose
  --env-file deploy/docker/openrouter-agent-full-demo.env.example
  -f docker-compose.dev.yml
  -f deploy/docker/openrouter-agent-full-demo.compose.yml
)

case "$ACTION" in
  config)
    "${COMPOSE[@]}" config
    ;;
  run)
    "${COMPOSE[@]}" up --build --abort-on-container-exit --exit-code-from openrouter-agent-full-demo openrouter-agent-full-demo
    ;;
  up)
    "${COMPOSE[@]}" up --build -d postgres rabbitmq elasticsearch governance-migrate governance-api governance-worker
    ;;
  down)
    "${COMPOSE[@]}" down
    ;;
  reset)
    "${COMPOSE[@]}" down -v
    ;;
  *)
    echo "Usage: $0 [config|run|up|down|reset]" >&2
    exit 64
    ;;
esac
