# Backend scripts

Run from `backend/` with `export PYTHONPATH=.` (and `source .venv/bin/activate`).

| Script | Purpose |
|--------|---------|
| **local_postgres_up.sh** | Start Docker Postgres + pgAdmin (port 5433). |
| **local_postgres_down.sh** | Stop local Docker stack. |
| **test_local_postgres_query.sh** | Quick connectivity check to local Postgres. |
| **clone_dev_db_docker.sh** | Clone remote dev DB into local Docker volume. |
| **switch_dev_database_to_local.sh** | Point `.env` at local Docker Postgres. |
| **sync_filter_catalog_sqlite.py** | Copy contract tables from Postgres/SQLite into a local mirror file. |
| **refresh_filter_catalog.py** | Refresh `app/data/filter_catalog.json` from DB distinct values. |
| **init_dev_sqlite_demo.py** | Create tiny `app/data/dev_investor_demo.sqlite` for offline catalog dev. |
| **build_schema_guide_modules.py** | Regenerate modular schema guide JSON under `app/data/schema_guide_modules/`. |
| **verify_backend_queries.py** | Smoke-test ADK `/run` for benchmark NL questions (pass/fail; use `--verbose` for dumps). |
| **list_accessible_tables.sql** | Ad-hoc SQL helper (run in psql/pgAdmin). |

**Data maintenance (under `app/data/`):**

- `export_investor_schema_contract.py` — introspect Postgres → `investor_db_schema_contract.json`
- `build_investor_schema_guide.py` — build monolith schema guide from contract + catalog

**Typical dev flow**

```bash
./scripts/local_postgres_up.sh
PYTHONPATH=. python scripts/sync_filter_catalog_sqlite.py
export PYTHONPATH=. && uvicorn app.main:app --host 127.0.0.1 --port 8000
# other terminal:
PYTHONPATH=. python scripts/verify_backend_queries.py
```
