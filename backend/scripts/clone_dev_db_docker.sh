#!/usr/bin/env bash
# Clone remote dev PostgreSQL into local Docker Postgres (pg_dump → pg_restore).

if [[ -d /opt/homebrew/opt/libpq/bin ]]; then
  export PATH="/opt/homebrew/opt/libpq/bin:${PATH}"
elif [[ -d /usr/local/opt/libpq/bin ]]; then
  export PATH="/usr/local/opt/libpq/bin:${PATH}"
fi
#
# Usage (from backend/):
#   ./scripts/local_postgres_up.sh
#   cp temp/clone.env.example temp/clone.env   # set SOURCE_DATABASE_URL
#   ./scripts/clone_dev_db_docker.sh --subset      # 14 app tables (~3 MB, fast)
#   ./scripts/clone_dev_db_docker.sh --accessible  # every public/sphmf table you can SELECT
#   ./scripts/clone_dev_db_docker.sh --full        # alias for --accessible
#   ./scripts/clone_dev_db_docker.sh --reuse-dump
#
# Note: --schema public+sphmf fails on read-only roles (permission denied on some tables).
#       Use --accessible instead of a blind full-schema dump.
#
# Requires: docker, pg_dump, pg_restore, psql (PostgreSQL client tools).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
COMPOSE_FILE="${ROOT}/docker/docker-compose.yml"
ENV_FILE="${ROOT}/docker/.env"
CLONE_ENV="${ROOT}/temp/clone.env"
DUMP_DIR="${ROOT}/temp/dumps"
DUMP_FILE="${DUMP_DIR}/investor_dev.dump"
MODE=""

SUBSET=0
ACCESSIBLE=0
REUSE_DUMP=0
for arg in "$@"; do
  case "${arg}" in
    --subset) SUBSET=1; MODE="subset" ;;
    --accessible|--full) ACCESSIBLE=1; MODE="accessible" ;;
    --reuse-dump) REUSE_DUMP=1 ;;
    -h|--help)
      grep '^#' "$0" | head -20 | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *)
      echo "Unknown option: ${arg}" >&2
      exit 1
      ;;
  esac
done

if [[ "${SUBSET}" -eq 1 && "${ACCESSIBLE}" -eq 1 ]]; then
  echo "ERROR: Use only one of --subset or --accessible/--full." >&2
  exit 1
fi
if [[ -z "${MODE}" ]]; then
  echo "ERROR: Pick a mode: --subset (14 tables) or --accessible (all readable tables)." >&2
  exit 1
fi

if [[ "${SUBSET}" -eq 1 ]]; then
  DUMP_FILE="${DUMP_DIR}/investor_dev.dump"
else
  DUMP_FILE="${DUMP_DIR}/investor_dev_accessible.dump"
fi

if [[ -f "${CLONE_ENV}" ]]; then
  # shellcheck disable=SC1090
  set -a
  source "${CLONE_ENV}"
  set +a
fi

SOURCE_URL="${SOURCE_DATABASE_URL:-${DEV_DATABASE_URL:-}}"
LOCAL_URL="${LOCAL_DATABASE_URL:-postgresql://localdev:localdev@localhost:5433/investor_db_local}"

if [[ -z "${SOURCE_URL}" ]]; then
  echo "ERROR: Set SOURCE_DATABASE_URL in backend/temp/clone.env or export DEV_DATABASE_URL." >&2
  echo "  cp temp/clone.env.example temp/clone.env" >&2
  exit 1
fi

for cmd in docker pg_dump pg_restore psql; do
  if ! command -v "${cmd}" >/dev/null 2>&1; then
    echo "ERROR: '${cmd}' not found. Install PostgreSQL client tools and Docker." >&2
    exit 1
  fi
done

mkdir -p "${DUMP_DIR}" "${ROOT}/temp/docker-pgdata"
"${ROOT}/scripts/local_postgres_up.sh"

ACCESSIBLE_LIST="${DUMP_DIR}/accessible_tables.txt"
ACCESSIBLE_BATCHED=0

# pg_dump 17+/18 archives may SET transaction_timeout; Postgres 16 local Docker rejects it (harmless).
restore_piece_ok() {
  local log="$1"
  [[ -f "${log}" ]] || return 1
  if ! grep -q 'transaction_timeout' "${log}"; then
    return 1
  fi
  local serious
  serious="$(
    grep -E '^(pg_restore: )?error:' "${log}" 2>/dev/null \
      | grep -vi 'transaction_timeout' \
      | grep -vi 'already exists' \
      | grep -vi 'errors ignored on restore' || true
  )"
  [[ -z "${serious}" ]]
}

restore_piece() {
  local piece="$1"
  local fq_table="$2"
  local log="${DUMP_DIR}/.last_restore_err.log"

  if pg_restore --dbname="${LOCAL_URL}" --no-owner --no-acl --clean --if-exists "${piece}" >"${log}" 2>&1; then
    return 0
  fi
  if restore_piece_ok "${log}"; then
    return 0
  fi
  if psql "${LOCAL_URL}" -v ON_ERROR_STOP=0 -c "SELECT 1 FROM ${fq_table} LIMIT 1" >/dev/null 2>&1; then
    if pg_restore --dbname="${LOCAL_URL}" --no-owner --no-acl --data-only --disable-triggers "${piece}" >"${log}" 2>&1; then
      return 0
    fi
    if restore_piece_ok "${log}"; then
      return 0
    fi
  fi
  if pg_restore --dbname="${LOCAL_URL}" --no-owner --no-acl "${piece}" >"${log}" 2>&1; then
    return 0
  fi
  if restore_piece_ok "${log}"; then
    return 0
  fi
  tail -8 "${log}" >&2
  return 1
}

clone_accessible_batched() {
  if [[ ! -f "${ACCESSIBLE_LIST}" ]]; then
    echo "Accessible: listing public/sphmf tables with SELECT privilege..."
    psql "${SOURCE_URL}" -v ON_ERROR_STOP=1 -At -f "${ROOT}/scripts/list_accessible_tables.sql" > "${ACCESSIBLE_LIST}"
  fi
  TABLE_COUNT="$(wc -l < "${ACCESSIBLE_LIST}" | tr -d ' ')"
  echo "Tables to dump: ${TABLE_COUNT} (list: ${ACCESSIBLE_LIST})"
  if [[ "${TABLE_COUNT}" -eq 0 ]]; then
    echo "ERROR: No accessible tables found." >&2
    exit 1
  fi
  PIECES_DIR="${DUMP_DIR}/accessible_pieces"
  mkdir -p "${PIECES_DIR}"
  psql "${LOCAL_URL}" -v ON_ERROR_STOP=1 -c "CREATE SCHEMA IF NOT EXISTS sphmf;"
  DONE=0
  FAIL=0
  SKIP=0
  while IFS= read -r t; do
    [[ -z "${t}" ]] && continue
    safe="${t//./_}"
    piece="${PIECES_DIR}/${safe}.dump"
    if [[ "${REUSE_DUMP}" -eq 1 && -f "${piece}" && -s "${piece}" ]]; then
      echo "  restore-only ${t} (reuse dump) ..."
      if restore_piece "${piece}" "${t}"; then
        DONE=$((DONE + 1))
      else
        echo "  WARN: pg_restore failed for ${t}" >&2
        FAIL=$((FAIL + 1))
      fi
      continue
    fi
    echo "  dump+restore ${t} ..."
    if ! pg_dump --format=custom --no-owner --no-acl --dbname="${SOURCE_URL}" --table="${t}" --file="${piece}"; then
      echo "  WARN: pg_dump failed for ${t}" >&2
      FAIL=$((FAIL + 1))
      rm -f "${piece}"
      continue
    fi
    if restore_piece "${piece}" "${t}"; then
      DONE=$((DONE + 1))
    else
      echo "  WARN: pg_restore failed for ${t}" >&2
      FAIL=$((FAIL + 1))
    fi
  done < "${ACCESSIBLE_LIST}"
  echo "Accessible clone: restored=${DONE} skipped=${SKIP} failed=${FAIL} (pieces in ${PIECES_DIR})"
}

if [[ "${ACCESSIBLE}" -eq 1 ]]; then
  echo "Dumping from remote (mode=accessible, per-table resume)..."
  clone_accessible_batched
  ACCESSIBLE_BATCHED=1
elif [[ "${REUSE_DUMP}" -eq 0 ]] || [[ ! -f "${DUMP_FILE}" ]]; then
  echo "Dumping from remote (mode=${MODE})..."
  DUMP_ARGS=(
    --format=custom
    --no-owner
    --no-acl
    --verbose
    --file="${DUMP_FILE}"
    --dbname="${SOURCE_URL}"
  )
  echo "Subset: 14 investor contract tables (same as the app schema contract)."
  TABLES=(
    public.distributor_investor_mapping
    public.investor
    public.tax_status
    public.scheme_master
    public.payout_mechanism
    sphmf.customer_master
    sphmf.multiple_bank
    sphmf.customer_schemes
    sphmf.scheme_setup
    sphmf.processed_trxns
    sphmf.sipstp
    sphmf.dtp_regn
    sphmf.trigger_trxn
    sphmf.transaction_types
  )
  for t in "${TABLES[@]}"; do
    DUMP_ARGS+=(--table="${t}")
  done
  pg_dump "${DUMP_ARGS[@]}"
  ls -lh "${DUMP_FILE}"
  echo "Dump saved: ${DUMP_FILE}"
else
  echo "Reusing existing dump: ${DUMP_FILE}"
fi

if [[ "${ACCESSIBLE_BATCHED:-0}" -eq 0 ]]; then
  echo "Restoring into local Docker Postgres (${MODE})..."
  psql "${LOCAL_URL}" -v ON_ERROR_STOP=1 -c "CREATE SCHEMA IF NOT EXISTS sphmf;"

  LOG="${DUMP_DIR}/last_restore_${MODE}.log"
  if ! pg_restore \
    --dbname="${LOCAL_URL}" \
    --verbose \
    --no-owner \
    --no-acl \
    --clean \
    --if-exists \
    "${DUMP_FILE}" \
    2>&1 | tee "${LOG}"; then
    if restore_piece_ok "${LOG}"; then
      echo "Restore finished (ignored transaction_timeout from newer pg_dump client)."
    else
      echo "WARN: pg_restore reported errors. Check ${LOG}" >&2
    fi
  fi
fi

echo ""
echo "Local table counts (public + sphmf):"
psql "${LOCAL_URL}" -At -c "
  SELECT table_schema, count(*)
  FROM information_schema.tables
  WHERE table_schema IN ('public','sphmf') AND table_type='BASE TABLE'
  GROUP BY 1 ORDER BY 1;"

echo ""
echo "DEV_DATABASE_URL=${LOCAL_URL}"
