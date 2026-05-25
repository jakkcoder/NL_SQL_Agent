# Full copy of the dev PostgreSQL database (local)

Yes—you can keep a **full** copy of the dev warehouse **on your machine**, but it should stay **PostgreSQL → PostgreSQL**. The repo’s SQLite sync script is only for a **subset** of tables (catalog / contract convenience), not a whole-server clone.

## Why not “entire DB in SQLite”?

- Dev DBs usually use multiple schemas (`public`, `sphmf`, …), custom types, partitions, indexes, and sometimes extensions.
- Application SQL in this project is written for **PostgreSQL** (`information_schema`, `NOW()`, `ANY(%s::TEXT[])`, etc.).
- A faithful “everything” mirror is **`pg_dump` / `pg_restore`** (or logical replication), not SQLite.

## Typical approach: dump from dev, restore into local Postgres

**Requirements**

- [PostgreSQL client tools](https://www.postgresql.org/download/) (`pg_dump`, `pg_restore`, `psql`) installed locally, version **compatible** with the server (same major version, or newer client than server, within supported matrix).
- Network path to dev (VPN, etc.) and credentials that are allowed to **read all objects** you care about.
- Enough **disk** (dump size is often a large fraction of DB size; custom format compresses somewhat).

**1. Create an empty local database**

```bash
createdb investor_db_local
# or via psql: CREATE DATABASE investor_db_local;
```

**2. Dump from dev (custom format, parallel-friendly)**

Replace placeholders with your real host, user, and DB name. Do **not** paste passwords into shell history; use `.pgpass` or prompt.

```bash
pg_dump \
  --format=custom \
  --no-owner \
  --no-acl \
  --dbname='postgresql://USER@HOST:PORT/SOURCE_DBNAME?sslmode=require' \
  --file=./investor_dev.dump
```

- `--no-owner --no-acl` helps when restoring as a different local superuser; your team may prefer owner/ACL preserved—ask DBA.
- If the dev role is **read-only**, some objects (e.g. certain extensions, event triggers, or privileged-only catalogs) may **not** appear in the dump. You still get a **data + schema** clone for objects that role can read.

**3. Restore into local**

```bash
pg_restore \
  --dbname='postgresql://USER@localhost:5432/investor_db_local' \
  --verbose \
  --no-owner \
  --no-acl \
  ./investor_dev.dump
```

Resolve errors (missing extensions, version mismatch) with DBA help or by installing the same extension versions locally.

**4. Point the app at local**

In `backend/.env`:

```env
DEV_DATABASE_URL=postgresql://USER:PASSWORD@localhost:5432/investor_db_local
```

Unset `FILTER_CATALOG_SQLITE_PATH` if you want catalog merge to use this same DB, or keep SQLite for catalog-only offline work.

## Alternatives

- **Plain SQL dump** (`pg_dump --format=plain --file=dev.sql`) then `psql -f dev.sql`—simple but slower and heavier for large DBs.
- **Docker Postgres** (recommended in this repo): `backend/scripts/local_postgres_up.sh` + `clone_dev_db_docker.sh` — see [local_docker_postgres.md](./local_docker_postgres.md). Local port defaults to **5433**; dumps and data under `backend/temp/`.
- **Team-managed snapshot**: many orgs provide weekly sanitized dumps; use those instead of live `pg_dump` from shared dev if policy requires it.

## Security

- Never commit dumps or `.env` with real URLs/passwords.
- Treat dumps like **sensitive data** (PII/financial) even from “dev”.
