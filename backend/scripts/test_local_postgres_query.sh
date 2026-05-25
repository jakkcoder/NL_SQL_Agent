#!/usr/bin/env bash
# Smoke-test local Docker Postgres (same DB as the app / pgAdmin).
set -euo pipefail

if [[ -d /opt/homebrew/opt/libpq/bin ]]; then
  export PATH="/opt/homebrew/opt/libpq/bin:${PATH}"
fi

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOCAL_URL="${LOCAL_DATABASE_URL:-postgresql://localdev:localdev@localhost:5433/investor_db_local}"

echo "Connecting: ${LOCAL_URL/@localdev:****@/@localdev:****@/}"
echo ""

psql "${LOCAL_URL}" -v ON_ERROR_STOP=1 <<'SQL'
SELECT current_database() AS db, current_user AS usr, version() AS pg_version;

SELECT table_schema, count(*) AS tables
FROM information_schema.tables
WHERE table_schema IN ('public', 'sphmf') AND table_type = 'BASE TABLE'
GROUP BY 1 ORDER BY 1;

SELECT COUNT(*) AS investor_rows FROM public.investor;
SELECT COUNT(*) AS mapping_rows FROM public.distributor_investor_mapping;

SELECT i.first_name, i.last_name, cm.city
FROM public.distributor_investor_mapping dim
JOIN public.investor i ON i.uuid = dim.investor_uuid
JOIN sphmf.customer_master cm ON cm.folio_no = dim.folio_number
WHERE cm.city IS NOT NULL
LIMIT 5;
SQL

echo ""
echo "OK — local Postgres queries succeeded."
