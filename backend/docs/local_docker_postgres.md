# Local PostgreSQL via Docker (offline dev clone)

Run the investor warehouse **on your machine** so chat/SQL tools do not need VPN or the remote dev host after a one-time clone.

## Layout

| Path | Role |
|------|------|
| `backend/docker/docker-compose.yml` | Postgres 16 + pgAdmin 4 |
| `backend/docker/pgadmin/servers.json` | Pre-registered local server in pgAdmin |
| `backend/temp/` | Dumps + Docker data volume (gitignored) |
| `backend/scripts/local_postgres_up.sh` | Start container |
| `backend/scripts/clone_dev_db_docker.sh` | `pg_dump` remote → `pg_restore` local |

Default local URL (port **5433** avoids clashing with an existing Postgres on 5432):

```text
postgresql://localdev:localdev@localhost:5433/investor_db_local
```

## Prerequisites

- Docker Engine running ([Docker Desktop](https://www.docker.com/products/docker-desktop/) or [Colima](https://github.com/abiosoft/colima): `brew install colima && colima start`)
- PostgreSQL **client** tools (`pg_dump`, `pg_restore`, `psql`): `brew install libpq` then `export PATH="/opt/homebrew/opt/libpq/bin:$PATH"`
- One-time network access to remote dev (VPN) for the dump step

## Steps

### 1. Start local Postgres + pgAdmin

```bash
cd backend
chmod +x scripts/local_postgres_up.sh scripts/local_postgres_down.sh scripts/clone_dev_db_docker.sh scripts/test_local_postgres_query.sh
./scripts/local_postgres_up.sh
```

This starts **both** containers: Postgres on port **5433** and pgAdmin on **http://127.0.0.1:5050**.

#### pgAdmin login

| Field | Default |
|-------|---------|
| URL | http://127.0.0.1:5050 |
| Email | `local@nl-sql-agent.dev` |
| Password | `localdev` |

After login, open **Servers → NL SQL Agent (local clone)**. When prompted for the database password, use **`localdev`** (same as `LOCAL_PG_PASSWORD`).

#### Run a test query in pgAdmin

1. Expand **NL SQL Agent (local clone) → Databases → investor_db_local → Schemas → public → Tables**.
2. Right-click **investor** → **Query Tool**.
3. Run:

```sql
SELECT COUNT(*) FROM public.investor;
SELECT COUNT(*) FROM public.distributor_investor_mapping;
```

Or use **Tools → Query Tool** on the database and run a join:

```sql
SELECT i.first_name, i.last_name, cm.city
FROM public.distributor_investor_mapping dim
JOIN public.investor i ON i.uuid = dim.investor_uuid
JOIN sphmf.customer_master cm ON cm.folio_no = dim.folio_number
WHERE cm.city IS NOT NULL
LIMIT 10;
```

#### Test from the terminal (no browser)

```bash
./scripts/test_local_postgres_query.sh
```

#### DBeaver (DB viewer)

A connection **NL SQL Agent (local Docker)** is registered in DBeaver when you import or sync from this repo.

| Field | Value |
|-------|-------|
| Host | `localhost` |
| Port | `5433` |
| Database | `investor_db_local` |
| User | `localdev` |
| Password | `localdev` (same as `LOCAL_PG_PASSWORD`) |

**First connect:** password `localdev` (same as Docker `LOCAL_PG_PASSWORD`).

If you see *SCRAM-based authentication, but no password was provided*:

1. **Quit DBeaver** (Cmd+Q), reopen (reloads `data-sources.json`).
2. **Edit connection** → set **Password** to `localdev` → enable **Save password** → **Test connection** → **Save**.

Or re-import: **Database** → **Import connections** → choose `backend/docker/dbeaver/import-local-connection.xml` (includes user + password).

DBeaver 25+ reads `configuration.password` in `data-sources.json` (not `auth-properties` alone).

Importable connection JSON (for another machine): `backend/docker/dbeaver/data-sources.local.json`  
(DBeaver: **Database** → **Driver Manager** not needed → **Database** → **New Database Connection** → **Import** from that file, or copy the `postgres-jdbc-nl-sql-agent-local` block into your workspace `data-sources.json`.)

Keep **hdfcmf-dev-postgres** (VPN remote) for `clone_dev_db_docker.sh`; use the local connection for day-to-day SQL.

**Smoke query:**

```sql
SELECT COUNT(*) FROM public.investor;
```

### 2. Configure remote source URL

```bash
cp temp/clone.env.example temp/clone.env
# Edit temp/clone.env — set SOURCE_DATABASE_URL to your read-only dev URL
```

`temp/clone.env` is gitignored. You can also export `DEV_DATABASE_URL` from `backend/.env` before cloning.

### 3. Clone

**Subset** (14 tables used by the app — fast, recommended for chat/SQL):

```bash
./scripts/clone_dev_db_docker.sh --subset
```

**All other tables you can read** (read-only role; skips tables that deny `SELECT`):

```bash
./scripts/clone_dev_db_docker.sh --accessible
```

This lists accessible `public` + `sphmf` tables, then `pg_dump --table=…` each (avoids a full-schema lock that fails with `permission denied`). May take a long time and several GB depending on grants.

`--full` is an alias for `--accessible`. A blind `--schema public --schema sphmf` dump **does not work** with the typical read-only dev user.

**Refresh without re-dumping** (reuse `temp/dumps/investor_dev.dump`):

```bash
./scripts/clone_dev_db_docker.sh --reuse-dump
```

### 4. Point the app at local

In `backend/.env`:

```env
DEV_DATABASE_URL=postgresql://localdev:localdev@localhost:5433/investor_db_local
```

Restart uvicorn. Optional: unset `FILTER_CATALOG_SQLITE_PATH` / `DEV_LOCAL_SQLITE_MIRROR` if you want catalog merge and SQL execution to use this same DB.

### 5. Stop container (data kept)

```bash
./scripts/local_postgres_down.sh
```

Data persists under `backend/temp/docker-pgdata/`. To wipe and start fresh:

```bash
./scripts/local_postgres_down.sh
rm -rf temp/docker-pgdata
./scripts/local_postgres_up.sh
```

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `docker: command not found` | Install/start Docker Desktop |
| `pg_dump: command not found` | `brew install libpq` and add to PATH, or install Postgres.app clients |
| Port 5433 in use | Set `LOCAL_PG_PORT=5434` in `backend/docker/.env` and update `LOCAL_DATABASE_URL` |
| Many `WARN: pg_restore failed` but table exists | Homebrew `pg_dump` 18 writes `SET transaction_timeout`; local Postgres 16 rejects it — restore usually still works. Re-run `./scripts/clone_dev_db_docker.sh --accessible --reuse-dump` after updating the script (restore-only for saved pieces). |
| `pg_restore` extension errors | Install matching extensions locally or use `--subset` and ignore non-critical restore warnings |
| Dump auth / SSL | Use `?sslmode=require` on `SOURCE_DATABASE_URL`; URL-encode `@` in passwords |
| Read-only role missing tables | Ask DBA for broader read access or use team-provided dump file + `--reuse-dump` |

## Security

- Never commit `temp/clone.env`, dumps (`.dump`), or `docker-pgdata/`.
- Treat dumps as sensitive (PII/financial data).

See also [dev_database_full_clone.md](./dev_database_full_clone.md) for non-Docker restore options.
