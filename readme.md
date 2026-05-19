### NL SQL Agent

Local/dev-first MVP for a mutual fund distributor investor-search chatbot.

The backend uses Google ADK for the agent definition and keeps SQL execution deterministic:

- Individual investors call the existing PostgreSQL function `filter_dp_investor_menu()`.
- Non-Individual investors use approved SQL templates and preserve the current combination behavior by intersecting separate result sets.
- Pending investors, arbitrary SQL generation, PAN/folio/mobile/email search, and flexible duration phrases are out of scope for MVP.

### Local Setup

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Update `backend/.env` with the real read-only PostgreSQL connection string and Google model credentials.

```bash
uvicorn app.main:app --reload --port 8000
```

The backend now uses Google ADK's built-in FastAPI server. List the available
agents with:

```bash
curl http://localhost:8000/list-apps
```

Send a message through ADK's runtime API:

```bash
curl -X POST http://localhost:8000/run \
  -H "Content-Type: application/json" \
  -d '{
    "appName": "investor_search_agent",
    "userId": "local_user",
    "sessionId": "local_session",
    "newMessage": {
      "role": "user",
      "parts": [{"text": "show individual investors"}]
    }
  }'
```

### Required Environment

- `APP_ENV`: runtime environment. Use `local`, `dev`, or `development` for dev DB; `production` or `prod` for prod DB.
- `LOG_LEVEL`: application log level, default `INFO`.
- `DEV_DATABASE_URL`: PostgreSQL read-only connection for local/dev.
- `DEV_DB_STATEMENT_TIMEOUT_MS`: dev statement timeout, default `15000`.
- `DEV_DB_POOL_MIN_SIZE`: dev pool minimum size, default `1`.
- `DEV_DB_POOL_MAX_SIZE`: dev pool maximum size, default `4`.
- `PROD_DATABASE_URL`: PostgreSQL read-only connection for production.
- `PROD_DB_STATEMENT_TIMEOUT_MS`: prod statement timeout, default `15000`.
- `PROD_DB_POOL_MIN_SIZE`: prod pool minimum size, default `2`.
- `PROD_DB_POOL_MAX_SIZE`: prod pool maximum size, default `10`.
- `DEFAULT_DEV_ARN`: local testing ARN, for example `ARN-0411`.
- `LLM_PROVIDER`: set `bedrock` for AWS Bedrock via ADK LiteLLM (default).
- `BEDROCK_MODEL_ID`: Bedrock model id, for example `anthropic.claude-3-haiku-20240307-v1:0`.
- `LLM_REQUEST_TIMEOUT_SECONDS`: model request timeout, default `60`.
- `LLM_TEMPERATURE`: model temperature, default `0`.
- `LLM_MAX_OUTPUT_TOKENS`: optional max output tokens for Bedrock calls.
- `AWS_REGION`: AWS region for Bedrock, for example `ap-south-1`.
- `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`: AWS credentials for Bedrock.
- `DEFAULT_PAGE_LIMIT`: default result page size, default `25`.
- `MAX_INTERSECTION_ROWS`: internal cap for Non-Individual intersection queries, default `5000`.
- `AWS_PROFILE`, `AWS_ROLE_ARN`, `AWS_SECRETS_MANAGER_PREFIX`: optional AWS deployment/secret-manager settings.
- `ALLOWED_ORIGINS`: comma-separated CORS origins.

### Test

```bash
cd backend
pytest
```

Integration tests against PostgreSQL require valid read-only database credentials.