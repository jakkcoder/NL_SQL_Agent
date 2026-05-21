"""Large-context filter catalog → one read-only SQL (single LLM call)."""

from __future__ import annotations

import ast
import json
import logging
from typing import Any

import litellm
from pydantic import BaseModel, ConfigDict, Field

from app.agents.system_prompts import CATALOG_SQL_GENERATOR_SYSTEM_PROMPT
from app.core.config import apply_runtime_env, get_config
from app.services.llm_json import parse_json_content

logger = logging.getLogger(__name__)


class CatalogSqlGeneratorTurn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    thought: str
    sql: str
    parameters: list[Any] = Field(default_factory=list)


def _normalize_generator_payload(raw: dict[str, Any]) -> dict[str, Any]:
    """Coerce occasional model quirks (e.g. parameters as a JSON/Python string)."""

    out = dict(raw)
    params = out.get("parameters")
    if isinstance(params, str):
        text = params.strip()
        parsed: Any = None
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            try:
                parsed = ast.literal_eval(text)
            except (SyntaxError, ValueError):
                parsed = [text]
        if isinstance(parsed, list):
            out["parameters"] = parsed
        elif parsed is None:
            out["parameters"] = []
        else:
            out["parameters"] = [parsed]
    return out


def run_catalog_sql_generator_llm(
    *,
    question: str,
    trusted_arn: str,
    schema_contract: dict[str, Any],
    schema_contract_max_chars: int,
    catalog_dict: dict[str, Any] | None = None,
    catalog_max_chars: int = 0,
    guide_only: bool | None = None,
) -> tuple[CatalogSqlGeneratorTurn, dict[str, Any]]:
    """Single-shot SQL proposal from schema guide (and optionally filter catalog)."""

    from app.services.investor_schema_contract import serialize_schema_contract_for_prompt

    cfg = get_config()
    apply_runtime_env(cfg)
    model = cfg.query_generator_llm_model_resolved
    use_guide_only = (
        guide_only if guide_only is not None else cfg.query_generator_guide_only
    )
    is_guide = schema_contract.get("contract_kind") == "investor_schema_guide"
    if use_guide_only and not is_guide:
        use_guide_only = False

    schema_raw = serialize_schema_contract_for_prompt(schema_contract, schema_contract_max_chars)

    if use_guide_only:
        user_payload = {
            "session_arn": trusted_arn,
            "investor_schema_guide_json": schema_raw,
            "question": question,
        }
        cat_raw = ""
    else:
        catalog_dict = catalog_dict or {}
        cat_raw = json.dumps(catalog_dict, ensure_ascii=True, default=str)
        if catalog_max_chars and len(cat_raw) > catalog_max_chars:
            cat_raw = cat_raw[: catalog_max_chars - 80] + "\n...(filter_catalog_json truncated)\n"
        schema_field = (
            "investor_schema_guide_json" if is_guide else "investor_schema_contract_json"
        )
        user_payload = {
            "session_arn": trusted_arn,
            "filter_catalog_json": cat_raw,
            schema_field: schema_raw,
            "question": question,
        }
    user_str = json.dumps(user_payload, ensure_ascii=True)

    log: dict[str, Any] = {
        "phase": "catalog_sql_generator",
        "model": model,
        "payload_mode": "guide_only" if use_guide_only else "guide_and_catalog",
        "user_payload_keys": sorted(user_payload.keys()),
        "user_payload_chars": len(user_str),
        "catalog_json_chars": len(cat_raw),
        "schema_guide_json_chars": len(schema_raw),
        "schema_contract_kind": schema_contract.get("contract_kind"),
        "question": question,
        "raw_response": None,
        "error": None,
    }

    system = CATALOG_SQL_GENERATOR_SYSTEM_PROMPT

    kwargs: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user_str},
        ],
        "temperature": 0,
        "timeout": cfg.llm.request_timeout_seconds,
        "response_format": {"type": "json_object"},
    }
    max_out = cfg.query_generator_max_output_tokens_resolved
    if max_out:
        kwargs["max_tokens"] = max_out

    response = litellm.completion(**kwargs)
    content = response.choices[0].message.content
    log["raw_response"] = content
    if not content:
        raise ValueError("Empty catalog SQL generator response")
    turn = CatalogSqlGeneratorTurn.model_validate(
        _normalize_generator_payload(parse_json_content(content))
    )
    log["parsed_thought"] = turn.thought
    log["parsed_sql"] = turn.sql
    log["parsed_param_count"] = len(turn.parameters)
    return turn, log
