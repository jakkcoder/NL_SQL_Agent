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

Open `frontend/index.html` in a browser. The default endpoint is already `http://localhost:8000/chat`.

### Required Environment

- `DATABASE_URL`: real PostgreSQL read-only connection.
- `DEFAULT_DEV_ARN`: local testing ARN, for example `ARN-0411`.
- `GOOGLE_API_KEY`: Google model key for ADK/Gemini use.
- `GOOGLE_ADK_MODEL`: model name, default `gemini-2.0-flash`.
- `DB_STATEMENT_TIMEOUT_MS`: statement timeout, default `15000`.
- `DEFAULT_PAGE_LIMIT`: default result page size, default `25`.

### Test

```bash
cd backend
pytest
```

Integration tests against PostgreSQL require valid read-only database credentials.