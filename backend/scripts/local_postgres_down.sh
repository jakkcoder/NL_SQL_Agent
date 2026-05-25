#!/usr/bin/env bash
# Stop local Postgres Docker container (keeps data volume in backend/temp/docker-pgdata).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
COMPOSE_FILE="${ROOT}/docker/docker-compose.yml"
ENV_FILE="${ROOT}/docker/.env"

if [[ -f "${ENV_FILE}" ]]; then
  docker compose -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" down
else
  docker compose -f "${COMPOSE_FILE}" down
fi

echo "Stopped nl-sql-agent-postgres-local (data kept under backend/temp/docker-pgdata)."
