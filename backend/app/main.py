from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.chat import router as chat_router
from app.core.settings import get_settings
from app.db.postgres import PostgresClient
from app.services.chat_service import ChatService


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    db = PostgresClient(settings.database_url, settings.db_statement_timeout_ms)
    db.open()
    app.state.settings = settings
    app.state.db = db
    app.state.chat_service = ChatService(db, settings)
    yield
    db.close()


app = FastAPI(title="Investor Chatbot MVP", version="0.1.0", lifespan=lifespan)

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
