# NL SQL Agent

Local/dev-first MVP for a mutual fund distributor **Individual investor** search chatbot.

The backend uses Google ADK for the agent and keeps SQL execution deterministic:

- Individual investors call PostgreSQL `filter_dp_investor_menu()`.
- Non-Individual investor search is **not** in this MVP (executor code kept for a later phase).
- Optional **dynamic read-only SQL** (`DYNAMIC_INVESTOR_SQL_ENABLED=true`): a separate tool runs an LLM + ReAct loop (max three attempts) against the investor schema contract with static SQL guards and mandatory ARN binding. Prefer the filter search path for normal list queries.
- Out of scope: pending investors, PAN/folio/mobile/email lookup, flexible duration phrases (unless enabled as above for contract-grounded reporting only).

**Schema for the SearchPlan LLM:** On the **first** investor search / plan build in an ADK session, the backend **auto-fetches** live PostgreSQL column metadata (once), stores a compact copy in session, and **rewrites** `backend/app/data/investor_db_schema_contract.json`. Later turns skip DB introspection until the session ends. `fetch_investor_schema_contract_tool(force=true)` forces a refresh. During **pytest**, auto-fetch uses the packaged JSON only (no DB, no file write). Refresh the file manually anytime with `python app/data/export_investor_schema_contract.py` from `backend/`.

## Prerequisites

- Python 3.10+
- Read-only PostgreSQL access for dev (often a **private IP** like `10.x.x.x` — connect only when **VPN / corporate network** is up)
- AWS Bedrock credentials (default LLM) or Google model credentials

**`DEV_DATABASE_URL`:** use `postgresql://USER:PASSWORD@HOST:PORT/DATABASE`. If the password contains `@`, `#`, or other reserved characters, **URL-encode** them (for `@` use `%40`). If TLS is required, append `?sslmode=require`. Put the final URL only in `backend/.env` (never commit it).

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
| `DEV_DATABASE_URL` | read-only PostgreSQL URL |
| `DEFAULT_DEV_ARN` | `ARN-0411` |
| `DYNAMIC_INVESTOR_SQL_ENABLED` | `false` (set `true` to expose ad-hoc read-only SQL tool) |
| `DYNAMIC_SQL_LLM_MODEL` | optional; defaults to the main LLM model |
| `LLM_PROVIDER` | `bedrock` |
| `BEDROCK_MODEL_ID` | `anthropic.claude-3-haiku-20240307-v1:0` |
| `AWS_REGION` | e.g. `ap-south-1` |
| `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` | Bedrock credentials |

## Start the backend

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
adk web app/agents --port 8000 --reload
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

**Search fails: `Connection refused` on `localhost:5432` or pool timeout**

The LLM/search-plan step can succeed while **PostgreSQL is down**. Investor rows come only from the DB.

1. Start your dev PostgreSQL instance (or point `DEV_DATABASE_URL` at a reachable host).
2. Confirm the URL in `backend/.env` matches that server.
3. Retry the search in the chat UI — you should get a clear in-chat error instead of a 30s SSE hang if the DB is still unreachable.

Optional pipeline check (needs a running DB for row counts):

```bash
cd backend
source .venv/bin/activate
export PYTHONPATH=.
python scripts/test_query_pipeline.py
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

When **`detect_intent_tool`** routes to Individual investor search (`search_investors_tool` or `analyze_search_arguments_tool`), it **seeds** `final_query`, `last_sql`, and `last_sql_parameters` using a default plan (same engine as a plain “show my investors” query for `DEFAULT_DEV_ARN`). **`search_investors_tool`** / **`analyze_search_arguments_tool`** then **overwrite** those keys with the real parsed plan.

**Geography** (e.g. “investors in Mumbai”) is **not** modeled in SQL in this MVP: there is no city column in `filter_dp_investor_menu` arguments. You will still see the standard function call; location would require a future product/DB design.

## Tests

```bash
cd backend
source .venv/bin/activate
export PYTHONPATH=.
pytest
```

Unit tests mock the database (90+ cases, including all Individual CSV filter mappings). One integration test hits live PostgreSQL when `DEV_DATABASE_URL` is set and the server is reachable; otherwise it is skipped.

```bash
pytest -m integration   # live DB only
```

### Bedrock model choices (cost)

Set `BEDROCK_MODEL_ID` in `backend/.env`. LiteLLM calls `bedrock/<model-id>`.

| Model ID | Notes |
|----------|--------|
| `anthropic.claude-3-haiku-20240307-v1:0` | **Default** — routing + JSON search plans |
| `anthropic.claude-3-5-haiku-20241022-v1:0` | Newer Haiku variant |
| `amazon.nova-lite-v1:0` | Lower-cost AWS option |
| `amazon.nova-micro-v1:0` | Lowest-cost AWS option |

Enable the model in **Amazon Bedrock → Model access** for your region (`AWS_REGION`), then restart the server.

## Environment variables

| Variable | Purpose |
|----------|---------|
| `APP_ENV` | `local` / `dev` / `development` → dev DB; `production` / `prod` → prod DB |
| `ADK_WEB_UI` | `true` = serve chat UI and redirect `/` → `/dev-ui/` (default on for local/dev, off for prod) |
| `LOG_LEVEL` | Log level (default `INFO`) |
| `DEV_DATABASE_URL` | PostgreSQL read-only URL for local/dev |
| `DEV_DB_STATEMENT_TIMEOUT_MS` | Dev statement timeout (default `15000`) |
| `DEV_DB_POOL_MIN_SIZE` / `DEV_DB_POOL_MAX_SIZE` | Dev pool size (default `1` / `4`) |
| `DEV_DB_CONNECT_TIMEOUT_SECONDS` / `DEV_DB_POOL_TIMEOUT_SECONDS` | Fail fast when DB is down (default `5` / `10`) |
| `PROD_DATABASE_URL` | Production read-only URL |
| `PROD_DB_*` | Production pool/timeout settings |
| `DEFAULT_DEV_ARN` | Local distributor ARN, e.g. `ARN-0411` |
| `LLM_PROVIDER` | `bedrock` for AWS Bedrock via LiteLLM (default) |
| `BEDROCK_MODEL_ID` | Bedrock model id (default `anthropic.claude-3-haiku-20240307-v1:0`) |
| `LLM_REQUEST_TIMEOUT_SECONDS` | Model timeout (default `60`) |
| `LLM_TEMPERATURE` | Model temperature (default `0`) |
| `LLM_MAX_OUTPUT_TOKENS` | Optional max output tokens |
| `AWS_REGION` | e.g. `ap-south-1` |
| `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN` | Bedrock credentials |
| `DEFAULT_PAGE_LIMIT` | Default page size (default `25`) |
| `MAX_INTERSECTION_ROWS` | NI intersection cap (default `5000`; unused in Individual MVP) |
| `AWS_PROFILE`, `AWS_ROLE_ARN`, `AWS_SECRETS_MANAGER_PREFIX` | Optional AWS deployment |
| `ALLOWED_ORIGINS` | Comma-separated CORS origins |
