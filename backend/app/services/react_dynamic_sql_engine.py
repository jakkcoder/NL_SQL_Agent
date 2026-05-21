"""ReAct-style LLM loop: validate → execute read-only SQL (max 3 attempts)."""

from __future__ import annotations

import json
import logging
from typing import Any

import litellm
from pydantic import BaseModel, ConfigDict, Field

from app.agents.query_engine_instructions import QUERY_ENGINE_SYSTEM_PROMPT
from app.core.config import apply_runtime_env
from app.db.postgres import PostgresClient
from app.services.llm_json import parse_json_content
from app.services.schema_digest import summarize_contract_for_sql_prompt
from app.services.sql_guard import (
    SqlGuardError,
    validate_arn_first_parameter,
    validate_dynamic_sql,
)

logger = logging.getLogger(__name__)

MAX_SQL_ATTEMPTS = 3


class SqlReactTurn(BaseModel):
    """One LLM turn: reasoning + executable SQL."""

    model_config = ConfigDict(extra="forbid")

    thought: str
    sql: str
    parameters: list[Any] = Field(default_factory=list)


def run_react_dynamic_sql(
    *,
    user_question: str,
    trusted_arn: str,
    schema_compact: dict[str, Any],
    db: PostgresClient,
    llm_model: str,
    llm_timeout_seconds: int,
    max_output_tokens: int | None,
) -> dict[str, Any]:
    """ReAct loop: propose SQL → guard → execute; feed DB errors back (≤ ``MAX_SQL_ATTEMPTS``)."""

    apply_runtime_env()
    digest = summarize_contract_for_sql_prompt(schema_compact)
    trace: list[dict[str, Any]] = []

    messages: list[dict[str, str]] = [
        {"role": "system", "content": QUERY_ENGINE_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": json.dumps(
                {
                    "session_arn": trusted_arn,
                    "schema_digest": digest,
                    "question": user_question,
                    "attempt_budget": MAX_SQL_ATTEMPTS,
                },
                ensure_ascii=True,
            ),
        },
    ]

    last_error: str | None = None
    final_sql: str | None = None
    final_params: list[Any] | None = None
    rows: list[dict[str, Any]] | None = None

    for attempt in range(1, MAX_SQL_ATTEMPTS + 1):
        kwargs: dict[str, Any] = {
            "model": llm_model,
            "messages": messages,
            "temperature": 0,
            "timeout": llm_timeout_seconds,
            "response_format": {"type": "json_object"},
        }
        if max_output_tokens:
            kwargs["max_tokens"] = max_output_tokens

        try:
            response = litellm.completion(**kwargs)
            content = response.choices[0].message.content
            if not content:
                raise ValueError("Empty LLM response")
            turn = SqlReactTurn.model_validate(parse_json_content(content))
        except Exception as exc:
            last_error = f"LLM parse error: {exc}"
            trace.append({"attempt": attempt, "phase": "llm", "error": last_error})
            messages.append(
                {
                    "role": "user",
                    "content": f"Observation (attempt {attempt}): {last_error}\n"
                    "Return corrected JSON only.",
                }
            )
            continue

        trace.append({"attempt": attempt, "thought": turn.thought, "sql": turn.sql, "parameters": turn.parameters})

        try:
            validate_dynamic_sql(turn.sql)
            validate_arn_first_parameter(turn.sql, list(turn.parameters), trusted_arn)
        except SqlGuardError as exc:
            last_error = str(exc)
            trace.append({"attempt": attempt, "phase": "guard", "error": last_error})
            messages.append(
                {
                    "role": "user",
                    "content": f"Observation (attempt {attempt}): validation failed: {last_error}\n"
                    "Fix sql/parameters; JSON only.",
                }
            )
            continue

        try:
            rows = db.fetch_all(turn.sql, tuple(turn.parameters))
            final_sql = turn.sql
            final_params = list(turn.parameters)
            trace.append({"attempt": attempt, "phase": "execute", "row_count": len(rows)})
            return {
                "ok": True,
                "attempts": attempt,
                "final_sql": final_sql,
                "parameters": final_params,
                "rows": rows,
                "trace": trace,
                "error": None,
            }
        except Exception as exc:
            last_error = str(exc)
            logger.warning("Dynamic SQL execution failed (attempt %s): %s", attempt, last_error)
            trace.append({"attempt": attempt, "phase": "execute", "error": last_error})
            messages.append(
                {
                    "role": "user",
                    "content": f"Observation (attempt {attempt}): database error: {last_error}\n"
                    "Return corrected JSON only.",
                }
            )

    return {
        "ok": False,
        "attempts": MAX_SQL_ATTEMPTS,
        "final_sql": final_sql,
        "parameters": final_params,
        "rows": rows or [],
        "trace": trace,
        "error": last_error or "Exhausted retry budget",
    }
