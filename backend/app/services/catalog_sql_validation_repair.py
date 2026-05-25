"""Small LLM pass to fix catalog SQL that failed static validation (before execution)."""

from __future__ import annotations

import json
import logging
from typing import Any

import litellm

from app.agents.system_prompts import CATALOG_SQL_VALIDATION_REPAIR_SYSTEM_PROMPT
from app.core.config import apply_runtime_env, get_config
from app.services.llm_json import parse_json_content
from app.services.query_flow_router import (
    CatalogSqlGeneratorTurn,
    _normalize_generator_payload,
)

logger = logging.getLogger(__name__)


def run_catalog_sql_validation_repair_llm(
    *,
    question: str,
    trusted_arn: str,
    failed_sql: str,
    failed_parameters: list[Any],
    validation_error: str,
) -> tuple[CatalogSqlGeneratorTurn, dict[str, Any]]:
    """Haiku-scale repair when ``sql_guard`` rejects generator output."""

    cfg = get_config()
    apply_runtime_env(cfg)
    model = cfg.catalog_sql_validation_repair_model_resolved

    user_payload = {
        "session_arn": trusted_arn,
        "question": question,
        "validation_error": validation_error[:500],
        "failed_sql": failed_sql[:8000],
        "failed_parameters": failed_parameters,
    }
    user_str = json.dumps(user_payload, ensure_ascii=True, default=str)

    log: dict[str, Any] = {
        "phase": "catalog_sql_validation_repair",
        "model": model,
        "validation_error": validation_error[:500],
        "user_payload_chars": len(user_str),
        "raw_response": None,
        "error": None,
    }

    kwargs: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": CATALOG_SQL_VALIDATION_REPAIR_SYSTEM_PROMPT},
            {"role": "user", "content": user_str},
        ],
        "temperature": 0,
        "timeout": cfg.catalog_sql_validation_repair_timeout_seconds,
        "response_format": {"type": "json_object"},
        "max_tokens": cfg.catalog_sql_validation_repair_max_output_tokens,
    }

    response = litellm.completion(**kwargs)
    content = response.choices[0].message.content
    log["raw_response"] = content
    if not content:
        raise ValueError("Empty catalog SQL validation repair response")

    turn = CatalogSqlGeneratorTurn.model_validate(
        _normalize_generator_payload(parse_json_content(content))
    )
    log["parsed_thought"] = turn.thought
    log["parsed_sql"] = turn.sql
    log["parsed_param_count"] = len(turn.parameters)
    return turn, log
