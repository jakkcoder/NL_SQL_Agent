#!/usr/bin/env bash
# Start local Postgres via Docker Compose.
set -euo pipefail

# Homebrew libpq (pg_dump / pg_restore) is keg-only on macOS.
if [[ -d /opt/homebrew/opt/libpq/bin ]]; then
  export PATH="/opt/homebrew/opt/libpq/bin:${PATH}"
elif [[ -d /usr/local/opt/libpq/bin ]]; then
  export PATH="/usr/local/opt/libpq/bin:${PATH}"
fi

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
COMPOSE_FILE="${ROOT}/docker/docker-compose.yml"
ENV_FILE="${ROOT}/docker/.env"

if [[ ! -f "${ENV_FILE}" ]] && [[ -f "${ROOT}/docker/.env.example" ]]; then
  cp "${ROOT}/docker/.env.example" "${ENV_FILE}"
fi

mkdir -p "${ROOT}/temp/docker-pgdata" "${ROOT}/temp/dumps"

if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: docker is not installed or not on PATH." >&2
  exit 1
fi

docker compose -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" up -d

mkdir -p "${ROOT}/temp/pgadmin-data"

echo "Waiting for Postgres + pgAdmin..."
for _ in $(seq 1 60); do
  if docker compose -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" exec -T investor-postgres-local \
    pg_isready -U "${LOCAL_PG_USER:-localdev}" -d "${LOCAL_PG_DATABASE:-investor_db_local}" >/dev/null 2>&1; then
    echo ""
    echo "Local Postgres: postgresql://${LOCAL_PG_USER:-localdev}:****@localhost:${LOCAL_PG_PORT:-5433}/${LOCAL_PG_DATABASE:-investor_db_local}"
    echo "pgAdmin UI:     http://127.0.0.1:${PGADMIN_PORT:-5050}"
    echo "  Login email:  ${PGADMIN_EMAIL:-local@nl-sql-agent.dev}"
    echo "  Login password: ${PGADMIN_PASSWORD:-localdev} (PGADMIN_DEFAULT_PASSWORD)"
    echo "  Server password (first connect): ${LOCAL_PG_PASSWORD:-localdev} (LOCAL_PG_PASSWORD)"
    echo ""
    echo "Quick SQL test: ./scripts/test_local_postgres_query.sh"
    exit 0
  fi
  sleep 1
done

echo "WARN: Postgres did not become ready within 60s. Check: docker compose -f ${COMPOSE_FILE} logs" >&2
exit 1
