# Local temp workspace (gitignored artifacts)

Use this folder for **local-only** database clone files. Nothing here should be committed.

| Path | Purpose |
|------|---------|
| `dumps/` | `pg_dump` custom-format files from remote dev |
| `docker-pgdata/` | Docker Postgres data volume (created by `docker compose`) |
| `clone.env` | Optional: copy from `clone.env.example` with remote `SOURCE_DATABASE_URL` |

## Quick start

From `backend/` (VPN on when pulling from remote):

```bash
# 1) Start local Postgres in Docker
./scripts/local_postgres_up.sh

# 2) Clone remote dev → local (one-time or refresh)
cp temp/clone.env.example temp/clone.env   # edit SOURCE_DATABASE_URL
./scripts/clone_dev_db_docker.sh --subset
# More tables (everything your DB user can SELECT):
# ./scripts/clone_dev_db_docker.sh --accessible

# 3) Point the app at local Docker Postgres
# In backend/.env:
# DEV_DATABASE_URL=postgresql://localdev:localdev@localhost:5433/investor_db_local
```

- `--subset` — 14 contract tables (enough for this app)
- `--accessible` — all other `public` / `sphmf` tables your user can read

See [docs/local_docker_postgres.md](../docs/local_docker_postgres.md).
