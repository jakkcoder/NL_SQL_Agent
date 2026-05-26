# NL SQL Agent

Local/dev-first MVP for a mutual fund distributor **Individual investor** search chatbot.

The backend uses Google ADK for the agent and keeps SQL execution deterministic:

- **Individual investors:** **`generate_catalog_sql_query_tool`** maps natural language to parameters for the warehouse function **`public.filter_dp_investor_menu`** (portal-aligned filters; see `planning/complete_function.sql` and `app/data/filter_dp_investor_menu_catalog.json`), then executes `SELECT * FROM public.filter_dp_investor_menu(...)`.
- Non-Individual investor search is **not** in this MVP.
- Out of scope: pending investors, PAN/folio/mobile/email lookup, flexible duration phrases (unless enabled as above for contract-grounded reporting only).

**Schema for SQL generation:** Packaged `investor_db_schema_guide.json` and modular guides under `app/data/schema_guide_modules/`. Refresh contract JSON from Postgres with `PYTHONPATH=. python app/data/export_investor_schema_contract.py` from `backend/`.

**Filter catalog without hitting the warehouse every session:** Run `PYTHONPATH=. python scripts/sync_filter_catalog_sqlite.py` from `backend/` (while connected to Postgres). By default it copies **all 14** investor-contract tables (`INVESTOR_CONTRACT_TABLES`) into SQLite as `public_*` / `sphmf_*` tables plus **6 views** so catalog merge SQL still works. Use `--mode catalog` for a quick **6-table** copy only. Set `FILTER_CATALOG_SQLITE_PATH=app/data/filter_catalog_local.sqlite` in `backend/.env`, **or** set `DEV_LOCAL_SQLITE_MIRROR` to the same path in **development** to also **skip live schema introspection** (packaged `investor_db_schema_contract.json` only) while still using `DEV_DATABASE_URL` for executing warehouse SQL. This mirror is **not** every table in the remote cluster—only the contract the app uses; for a full Postgres clone use `pg_dump` to a local Postgres instance.

## Prerequisites

- Python 3.10+
- Read-only PostgreSQL access for dev (often a **private IP** like `10.x.x.x` — connect only when **VPN / corporate network** is up)
- AWS Bedrock credentials (default LLM) or Google model credentials

**`DEV_DATABASE_URL`:** use `postgresql://USER:PASSWORD@HOST:PORT/DATABASE`. If the password contains `@`, `#`, or other reserved characters, **URL-encode** them (for `@` use `%40`). If TLS is required, append `?sslmode=require`. Put the final URL only in `backend/.env` (never commit it).

**Offline local Postgres (Docker):** Clone dev once, then run the chatbot against **localhost:5433** without VPN. See [Local Docker PostgreSQL](#local-docker-postgresql) below.

**Offline catalog mirror (dev):** Run `PYTHONPATH=. python scripts/init_dev_sqlite_demo.py` to create `app/data/dev_investor_demo.sqlite`. Set `DEV_LOCAL_SQLITE_MIRROR` to that path for catalog refresh without VPN Postgres. SQL execution still uses PostgreSQL unless you use local Docker Postgres.

Use the virtualenv at **`backend/.venv`** only. Do **not** use a repo-root `.venv` (missing deps, wrong `app` imports).

## One-time setup

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `backend/.env`:

| Setting | Example / notes |
|---------|-----------------|
| `APP_ENV` | `local` |
| `ADK_WEB_UI` | `true` (chat UI at `/`) |
| `USE_LOCAL_DOCKER_POSTGRES` | `true` (default) — app SQL hits local Docker, not remote VPN |
| `LOCAL_DATABASE_URL` | `postgresql://localdev:localdev@localhost:5433/investor_db_local` |
| `DEV_DATABASE_URL` | Remote read-only URL (clone source; optional when local Docker is on) |
| `DEFAULT_DEV_ARN` | `ARN-0411` |
| `DYNAMIC_SQL_LLM_MODEL` | optional catalog SQL generator override (LiteLLM) |
| `BEDROCK_QUERY_GENERATOR_MODEL_ID` | large-context Bedrock model for `generate_catalog_sql_query_tool` (default Sonnet 3.5) |
| `QUERY_GENERATOR_LLM_MODEL` | optional LiteLLM override for the catalog SQL generator |
| `FILTER_CATALOG_SQLITE_PATH` | optional; SQLite file for catalog merge only |
| `LLM_PROVIDER` | `bedrock` |
| `BEDROCK_MODEL_ID` | small/fast Bedrock model for the **root ADK agent** (default Haiku) |
| `BEDROCK_ROOT_MODEL_ID` | optional root override (else `BEDROCK_MODEL_ID`) |
| `AWS_REGION` | e.g. `ap-south-1` |
| `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` | Bedrock credentials |

## Local Docker PostgreSQL

Runs **Postgres 16** and **pgAdmin 4** via Compose. Data is stored under `backend/temp/` (gitignored).

**Requires:** [Docker Desktop](https://www.docker.com/products/docker-desktop/) running, or [Colima](https://github.com/abiosoft/colima) (`brew install colima && colima start`).

### Start containers (every dev session)

```bash
cd backend
chmod +x scripts/local_postgres_up.sh scripts/local_postgres_down.sh scripts/test_local_postgres_query.sh
./scripts/local_postgres_up.sh
```

This starts:

| Service | URL / port |
|---------|------------|
| PostgreSQL | `localhost:5433` — `postgresql://localdev:localdev@localhost:5433/investor_db_local` |
| pgAdmin | http://127.0.0.1:5050 — email `local@nl-sql-agent.dev`, password `localdev` |

In pgAdmin, open **Servers → NL SQL Agent (local clone)** and enter database password **`localdev`** when prompted.

**DBeaver:** use connection **NL SQL Agent (local Docker)** — `localhost:5433`, database `investor_db_local`, user/password `localdev`. See [backend/docs/local_docker_postgres.md](backend/docs/local_docker_postgres.md#dbeaver-db-viewer).

**Smoke-test SQL** (terminal):

```bash
./scripts/test_local_postgres_query.sh
```

**Stop containers** (keeps data on disk):

```bash
./scripts/local_postgres_down.sh
```

**Start again later** — run `./scripts/local_postgres_up.sh` only; no re-clone needed.

### One-time clone from remote dev (VPN on)

```bash
cd backend
cp temp/clone.env.example temp/clone.env
# Edit temp/clone.env — set SOURCE_DATABASE_URL to your read-only dev URL

./scripts/clone_dev_db_docker.sh --subset      # 14 app tables (~3 MB, recommended)
# ./scripts/clone_dev_db_docker.sh --accessible   # all tables your user can SELECT (slow)
```

Point the app at local Docker in `backend/.env` (defaults in `.env.example`):

```env
USE_LOCAL_DOCKER_POSTGRES=true
LOCAL_DATABASE_URL=postgresql://localdev:localdev@localhost:5433/investor_db_local
```

Or run `./scripts/switch_dev_database_to_local.sh` after cloning.

Full guide: [backend/docs/local_docker_postgres.md](backend/docs/local_docker_postgres.md).

### Compose directly (optional)

```bash
cd backend
docker compose -f docker/docker-compose.yml --env-file docker/.env up -d
docker compose -f docker/docker-compose.yml ps
```

(`docker/.env` is created from `docker/.env.example` on first `./scripts/local_postgres_up.sh`.)

## Start the backend

Start **Docker Postgres first** if you use the local clone (`./scripts/local_postgres_up.sh`).

From the repo, every time:

```bash
cd backend
source .venv/bin/activate
export PYTHONPATH=.
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

**Browser:** [http://127.0.0.1:8000/](http://127.0.0.1:8000/) → choose **`investor_search_agent`**.

`export PYTHONPATH=.` is required so Python can `import app` when the agent runs. Without it, `/health` may work but chat fails with `No module named 'app'`.

### Alternative: ADK CLI

Same UI, started via Google ADK instead of uvicorn:

```bash
cd backend
source .venv/bin/activate
export PYTHONPATH=.
adk web app/agents --port 8001 --reload
```

Open [http://127.0.0.1:8000/](http://127.0.0.1:8000/) or [http://127.0.0.1:8000/dev-ui/](http://127.0.0.1:8000/dev-ui/).

### URLs

| URL | Purpose |
|-----|---------|
| http://127.0.0.1:8000/ | Chat UI (redirects to `/dev-ui/` when `ADK_WEB_UI=true`) |
| http://127.0.0.1:8000/dev-ui/ | Chat UI directly |
| http://127.0.0.1:8000/health | Health check (always available) |
| http://127.0.0.1:8000/list-apps | Lists agents, e.g. `investor_search_agent` |

### Troubleshooting

**`http://127.0.0.1:8000/` → Not Found**

- Set `ADK_WEB_UI=true` in `backend/.env` (on by default when `APP_ENV=local`).
- Restart uvicorn after changing `.env`.

**Chat error: `No module named 'app'`**

- Run from `backend/` with `export PYTHONPATH=.` before uvicorn or `adk web`.
- Use `backend/.venv`, not `NL_SQL_Agent/.venv` at the repo root.

**`Address already in use` on port 8000**

```bash
lsof -i :8000
kill <pid>
```

Or use port 8001: `uvicorn app.main:app --reload --host 127.0.0.1 --port 8001` and open http://127.0.0.1:8001/

**`cd: no such file or directory: backend`**

You are already inside `backend/`. Skip the extra `cd backend` and run only `source .venv/bin/activate` and the uvicorn line.

**Chat fails: `POST /run` 500 — Bedrock `The security token included in the request is invalid`**

The server is running correctly (`/health` and `/list-apps` return 200). The failure is **AWS Bedrock authentication** when the agent calls the LLM.

**If `aws configure` already works:** your `backend/.env` may still contain placeholder lines that **override** `~/.aws/credentials`:

```env
AWS_ACCESS_KEY_ID=replace-with-aws-access-key-id
AWS_SECRET_ACCESS_KEY=replace-with-aws-secret-access-key
```

Remove those lines or leave them empty, then restart uvicorn. The app ignores `replace-with-...` values and uses the AWS CLI credential chain instead.

1. Clear `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and `AWS_SESSION_TOKEN` in `.env` (use `aws configure` / default profile), **or** paste the same real keys into `.env`.
2. Ensure the IAM principal can invoke Bedrock in `AWS_REGION` (e.g. `ap-south-1`) for `BEDROCK_MODEL_ID`.
3. For SSO/temp creds, set all three env vars including `AWS_SESSION_TOKEN`.
4. Restart uvicorn after any `.env` change.

Verify Bedrock from the same shell:

```bash
cd backend
source .venv/bin/activate
aws sts get-caller-identity --region ap-south-1
# optional: aws bedrock list-foundation-models --region ap-south-1 --by-output-modality TEXT | head
```

**Bedrock / `No module named 'botocore'`**

```bash
cd backend && source .venv/bin/activate && pip install -r requirements.txt
```

**Use Google Gemini instead of Bedrock (optional)**

In `backend/.env`:

```env
LLM_PROVIDER=google
GOOGLE_API_KEY=your-gemini-api-key
```

Restart the server. (`GOOGLE_ADK_MODEL` defaults to `gemini-2.0-flash`.)

**Search fails: `Connection refused` on `localhost:5432` / `5433` or pool timeout**

The LLM step can succeed while **PostgreSQL is down**. Investor rows come only from the DB.

1. Start local Docker: `cd backend && ./scripts/local_postgres_up.sh` (port **5433**, not 5432).
2. Confirm `USE_LOCAL_DOCKER_POSTGRES=true` and `LOCAL_DATABASE_URL` in `backend/.env`.
3. Restart uvicorn after `.env` changes.
4. Run `./scripts/test_local_postgres_query.sh` to verify connectivity.

Optional smoke test (server must be running on :8000):

```bash
cd backend
source .venv/bin/activate
export PYTHONPATH=.
python scripts/verify_backend_queries.py
```

### API examples (optional)

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/list-apps
```

```bash
curl -X POST http://127.0.0.1:8000/run \
  -H "Content-Type: application/json" \
  -d '{
    "appName": "investor_search_agent",
    "userId": "local_user",
    "sessionId": "local_session",
    "newMessage": {
      "role": "user",
      "parts": [{"text": "show investors with STP"}]
    }
  }'
```

### ADK session state (`final_query` / `last_sql`)

When **`generate_catalog_sql_query_tool`** runs, it **writes** `final_query`, `last_sql`, and `last_sql_parameters` with the catalog SQL generator output (`engine`: `catalog_sql_generator`) for debugging and downstream viewers.

**Geography** (e.g. “investors in Mumbai”) depends on what the catalog generator can express in SQL from **filter_catalog_json** (``parameter`` hints and allowed ``values``); extend the catalog and prompts if you need stricter city predicates.

## Tests

```bash
cd backend
source .venv/bin/activate
export PYTHONPATH=.
pytest
```

Unit tests cover catalog SQL, schema guides, routing, and ADK session state. For live API checks with Postgres running:

```bash
python scripts/verify_backend_queries.py
python scripts/verify_backend_queries.py --verbose
```

See `backend/scripts/README.md` for all maintenance scripts.

### LLM calls per turn (current catalog SQL path)

Investor data questions run **`generate_catalog_sql_query_tool`** (directly or via **`detect_intent_tool`**). Each successful path uses **multiple LiteLLM calls** inside the tool—not a single model.

| Step | When | Model tier (default) | Config |
|------|------|----------------------|--------|
| 1. Root ADK agent | Every user message (picks tool, may summarize) | Haiku — `BEDROCK_MODEL_ID` | 1–2 completions if the model calls `detect_intent_tool` then replies |
| 2. Schema guide module router | Each catalog SQL generation | Haiku — `BEDROCK_MODULE_ROUTER_MODEL_ID` or root | Skipped if `QUERY_GENERATOR_MODULE_ROUTER_LLM=false` (keyword routing only) |
| 3. Catalog SQL generator | Each catalog SQL generation | **Sonnet** — `BEDROCK_QUERY_GENERATOR_MODEL_ID` | Largest prompt (~modular guide, up to `QUERY_GENERATOR_MODULAR_GUIDE_MAX_CHARS`) |
| 4. Validation repair | Only if `sql_guard` rejects SQL | Haiku — `BEDROCK_CATALOG_SQL_VALIDATION_REPAIR_MODEL_ID` | `CATALOG_SQL_VALIDATION_REPAIR_ENABLED=true` (default); max 1× |
| 5. Execute repair | Only if PostgreSQL execution fails | Same as step 3 (Sonnet) | `CATALOG_SQL_MAX_RETRIES_ON_EXECUTE_ERROR=1` (default); max 1× |

**Greeting-only** turns: step 1 only (Haiku, tiny prompt).

Deterministic steps (no LLM): `sanitize_catalog_sql`, `normalize_catalog_sql_parameters`, `sql_guard`, `catalog_sql_executor`.

See [planning/architecture.html](planning/architecture.html) for diagrams.

### Estimated cost per question (Bedrock on-demand, approximate)

Rates vary by **region** and **model ID**; verify in [Amazon Bedrock pricing](https://aws.amazon.com/bedrock/pricing/). Below uses common **Claude 3 Haiku** (~$0.25 / $1.25 per 1M input/output) and **Claude 3.5 Sonnet** (~$3 / $15 per 1M) as a planning baseline.

| Scenario | LLM calls (typical) | Est. tokens (in → out) | Est. cost / question |
|----------|---------------------|-------------------------|----------------------|
| Greeting | 1× Haiku (root) | ~3k → ~0.4k | **~$0.001** |
| Investor SQL — happy path | 1× Haiku root + 1× Haiku router + 1× Sonnet generator | ~3k→0.5k + ~2.5k→0.3k + ~14k→2k | **~$0.08–0.10** |
| + validation repair | +1× Haiku | +~3k→~1k | **+$0.002** |
| + execute repair | +1× Sonnet (full regen) | +~14k→~2k | **+$0.07–0.09** |
| Worst case (both repairs) | 2× Haiku + 2× Sonnet + root | — | **~$0.17–0.20** |

### Volume estimates (investor SQL questions, LLM only)

Assumes **every request** is one investor data question on the **happy path** ($0.08–$0.10 each). Add ~2× for **worst case** if many validation + execute repairs. **PostgreSQL**, VPC, and app compute are **not** included. Greetings (~$0.001 each) are negligible at scale.

| Requests | Happy path (low → high) | Mid (~$0.09 / req) | Worst case ($0.17 → $0.20 / req) |
|----------|-------------------------|--------------------|-------------------------------------|
| **100** | $8 – $10 | **~$9** | $17 – $20 |
| **1,000** | $80 – $100 | **~$90** | $170 – $200 |
| **10,000** | $800 – $1,000 | **~$900** | $1,700 – $2,000 |
| **1,000,000** | $80,000 – $100,000 | **~$90,000** | $170,000 – $200,000 |

**Rough monthly examples** (happy path mid column): ~330 investor questions/day → **~$900/month**; ~3,300/day → **~$9,000/month**; ~33,000/day → **~$90,000/month**.

### Model mix comparison (cost impact vs current defaults)

Same token budget per investor question (~3k→0.5k root, ~2.5k→0.3k router, ~14k→2k SQL generator). **Validation/execute repair** uses the same tier as the router / generator columns below when those paths fire. Dollar math uses on-demand list pricing (verify in your region).

| Config | Root | Module router | SQL generator | Val. repair | Est. $ / req | vs current (~$0.09) | 1,000 req | 10,000 req | 1,000,000 req | Quality / risk |
|--------|------|---------------|---------------|-------------|--------------|---------------------|-----------|------------|---------------|----------------|
| **A — Current default** | Claude 3 Haiku | Claude 3 Haiku | **Claude 3.5 Sonnet** | Claude 3 Haiku | **$0.08–0.10** | baseline | ~$90 | ~$900 | ~$90k | Recommended — best SQL accuracy |
| B — Keyword router only | Claude 3 Haiku | *(deterministic)* | Claude 3.5 Sonnet | Claude 3 Haiku | **~$0.07–0.09** | ~5–10% lower | ~$80 | ~$800 | ~$80k | Set `QUERY_GENERATOR_MODULE_ROUTER_LLM=false`; test module recall |
| C — Cheaper small steps | Nova Micro | Nova Micro | Claude 3.5 Sonnet | Nova Micro | **~$0.07–0.08** | ~10–15% lower | ~$75 | ~$750 | ~$75k | `BEDROCK_MODULE_ROUTER_MODEL_ID=amazon.nova-micro-v1:0`; keep Sonnet for SQL |
| D — Nova Lite small steps | Nova Lite | Nova Lite | Claude 3.5 Sonnet | Nova Lite | **~$0.07–0.08** | ~10–15% lower | ~$75 | ~$750 | ~$75k | Router/repair on Nova Lite; Sonnet unchanged |
| E — Nova Pro SQL gen | Claude 3 Haiku | Claude 3 Haiku | **Amazon Nova Pro** | Claude 3 Haiku | **~$0.02–0.03** | ~70–75% lower | ~$25 | ~$250 | ~$25k | `BEDROCK_QUERY_GENERATOR_MODEL_ID=amazon.nova-pro-v1:0`; **test SQL heavily** |
| F — Haiku SQL gen | Claude 3 Haiku | Claude 3 Haiku | **Claude 3.5 Haiku** | Claude 3 Haiku | **~$0.02–0.03** | ~70–75% lower | ~$25 | ~$250 | ~$25k | `BEDROCK_QUERY_GENERATOR_MODEL_ID=anthropic.claude-3-5-haiku-20241022-v1:0`; more guard/repair failures likely |
| G — Budget (Haiku gen + no LLM router) | Claude 3 Haiku | *(keyword)* | Claude 3.5 Haiku | Claude 3 Haiku | **~$0.02** | ~75–80% lower | ~$20 | ~$200 | ~$20k | Lowest cost while staying on Anthropic; quality trade-off |
| H — Minimum $ (all Nova Lite) | Nova Lite | Nova Lite | Nova Lite | Nova Lite | **~$0.002** | ~95–98% lower | ~$2 | ~$20 | ~$2k | **Not recommended** for production SQL — high error rate expected |
| I — Premium Sonnet (older id) | Claude 3 Haiku | Claude 3 Haiku | Claude 3 Sonnet | Claude 3 Haiku | **~$0.08–0.10** | ~same as A | ~$90 | ~$900 | ~$90k | `anthropic.claude-3-sonnet-20240229-v1:0` — similar price tier to 3.5 |

**How to read “vs current”:** almost all savings come from changing **`BEDROCK_QUERY_GENERATOR_MODEL_ID`** (step 3 — ~80% of token spend). Swapping only Haiku/router/repair (steps 1, 2, 4) saves **at most ~10–15%** unless you disable the LLM router (config B).

**Reference token rates used in estimates** ($ per 1M tokens, input / output):

| Model | Input | Output |
|-------|-------|--------|
| Claude 3 Haiku | $0.25 | $1.25 |
| Claude 3.5 Haiku | $0.80 | $4.00 |
| Claude 3 / 3.5 Sonnet | $3.00 | $15.00 |
| Amazon Nova Micro | $0.035 | $0.14 |
| Amazon Nova Lite | $0.06 | $0.24 |
| Amazon Nova Pro | $0.80 | $3.20 |

**Why this differs from the old pipeline:** the retired SearchPlan path used **2× Haiku** calls (intent + search plan) with large `filter_catalog.json` prompts and **no Sonnet**. Dollar cost per question was often **lower** (~$0.02–0.05) but could spike if huge catalog slices were sent. The current design trades **higher Sonnet cost** for **modular schema guide** context (~48k chars cap) and **LLM-authored read-only SQL** with guards + repair.

**Cost levers:** keyword-only module routing (`QUERY_GENERATOR_MODULE_ROUTER_LLM=false`), Nova Micro/Lite for router + validation repair, smaller `QUERY_GENERATOR_MODULAR_GUIDE_MAX_CHARS`, disable validation repair only if you accept more user-visible guard failures.

### Bedrock model choices

| Model ID | Role |
|----------|------|
| `anthropic.claude-3-haiku-20240307-v1:0` | **Default root** + module router + validation repair |
| `anthropic.claude-3-5-haiku-20241022-v1:0` | Newer Haiku for small steps |
| `anthropic.claude-3-5-sonnet-20241022-v2:0` | **Default catalog SQL generator** (large context) |
| `anthropic.claude-3-sonnet-20240229-v1:0` | Older Sonnet id (still in some `.env` examples) |
| `amazon.nova-lite-v1:0` / `amazon.nova-micro-v1:0` | Lower-cost options for router/repair only (test quality) |

Enable models in **Amazon Bedrock → Model access** for `AWS_REGION`, then restart the server.

## Environment variables

| Variable | Purpose |
|----------|---------|
| `APP_ENV` | `local` / `dev` / `development` → dev DB; `production` / `prod` → prod DB |
| `ADK_WEB_UI` | `true` = serve chat UI and redirect `/` → `/dev-ui/` (default on for local/dev, off for prod) |
| `LOG_LEVEL` | Log level (default `INFO`) |
| `USE_LOCAL_DOCKER_POSTGRES` | `true` = run catalog SQL on `LOCAL_DATABASE_URL` (local Docker) |
| `LOCAL_DATABASE_URL` | Local clone URL (default `localhost:5433`) |
| `DEV_DATABASE_URL` | Remote dev URL (optional; used when local Docker is off) |
| `DEV_DB_STATEMENT_TIMEOUT_MS` | Dev statement timeout (default `15000`) |
| `DEV_DB_POOL_MIN_SIZE` / `DEV_DB_POOL_MAX_SIZE` | Dev pool size (default `1` / `4`) |
| `DEV_DB_CONNECT_TIMEOUT_SECONDS` / `DEV_DB_POOL_TIMEOUT_SECONDS` | Fail fast when DB is down (default `5` / `10`) |
| `PROD_DATABASE_URL` | Production read-only URL |
| `PROD_DB_*` | Production pool/timeout settings |
| `DEFAULT_DEV_ARN` | Local distributor ARN, e.g. `ARN-0411` |
| `LLM_PROVIDER` | `bedrock` for AWS Bedrock via LiteLLM (default) |
| `BEDROCK_MODEL_ID` | Root ADK agent model (default `anthropic.claude-3-haiku-20240307-v1:0`) |
| `BEDROCK_ROOT_MODEL_ID` | Optional root override |
| `BEDROCK_QUERY_GENERATOR_MODEL_ID` | Catalog SQL generator (default `anthropic.claude-3-5-sonnet-20241022-v2:0`) |
| `QUERY_GENERATOR_LLM_MODEL` | Optional LiteLLM override for SQL generation |
| `QUERY_GENERATOR_MODULE_ROUTER_LLM` | `true` = Haiku module router per SQL question (default) |
| `BEDROCK_MODULE_ROUTER_MODEL_ID` | Optional override for module router |
| `QUERY_GENERATOR_MODULAR_GUIDE_MAX_CHARS` | Cap on guide JSON in generator prompt (default `48000`) |
| `CATALOG_SQL_VALIDATION_REPAIR_ENABLED` | Haiku fix for static SQL validation failures (default `true`) |
| `BEDROCK_CATALOG_SQL_VALIDATION_REPAIR_MODEL_ID` | Optional override for validation repair |
| `CATALOG_SQL_MAX_RETRIES_ON_EXECUTE_ERROR` | Sonnet regen on DB error (default `1`) |
| `LLM_REQUEST_TIMEOUT_SECONDS` | Model timeout (default `60`) |
| `LLM_TEMPERATURE` | Model temperature (default `0`) |
| `LLM_MAX_OUTPUT_TOKENS` | Optional max output tokens |
| `AWS_REGION` | e.g. `ap-south-1` |
| `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN` | Bedrock credentials |
| `DEFAULT_PAGE_LIMIT` | Default page size (default `25`) |
| `AWS_PROFILE`, `AWS_ROLE_ARN`, `AWS_SECRETS_MANAGER_PREFIX` | Optional AWS deployment |
| `ALLOWED_ORIGINS` | Comma-separated CORS origins |
