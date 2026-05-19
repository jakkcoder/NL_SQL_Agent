from pathlib import Path

from fastapi import FastAPI
from google.adk.cli.fast_api import get_fast_api_app

from app.core.config import apply_runtime_env, get_config


BACKEND_DIR = Path(__file__).resolve().parents[1]
AGENTS_DIR = BACKEND_DIR / "adk_agents"

config = get_config()
apply_runtime_env(config)
missing_config = config.production_missing_values()
if missing_config:
    missing = ", ".join(missing_config)
    raise RuntimeError(f"Missing required production configuration: {missing}")

app: FastAPI = get_fast_api_app(
    agents_dir=str(AGENTS_DIR),
    allow_origins=config.security.allowed_origins,
    web=False,
    auto_create_session=True,
)
