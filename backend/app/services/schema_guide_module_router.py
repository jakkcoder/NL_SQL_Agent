"""LLM router: pick schema guide module ids for the catalog SQL generator payload."""

from __future__ import annotations

import json
import logging
from typing import Any

import litellm
from pydantic import BaseModel, ConfigDict, Field

from app.agents.system_prompts import SCHEMA_GUIDE_MODULE_ROUTER_SYSTEM_PROMPT
from app.core.config import apply_runtime_env, get_config
from app.services.llm_json import parse_json_content
from app.services.schema_guide_modules import (
    CORE_MODULE_ID,
    load_manifest,
    modular_guide_available,
    select_module_ids_keyword,
)

logger = logging.getLogger(__name__)


class SchemaGuideModuleRouterTurn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    thought: str = ""
    selected_module_ids: list[str] = Field(default_factory=list)


def _coerce_router_turn_payload(parsed: dict[str, Any]) -> dict[str, Any]:
    """Bedrock often echoes ``question`` from the user JSON; strip before strict validate."""

    ids = parsed.get("selected_module_ids")
    if ids is None and isinstance(parsed.get("modules"), list):
        ids = parsed.get("modules")
    if not isinstance(ids, list):
        ids = []
    return {
        "thought": str(parsed.get("thought") or ""),
        "selected_module_ids": ids,
    }


def _valid_module_ids() -> set[str]:
    manifest = load_manifest()
    return {
        str(m.get("id"))
        for m in manifest.get("modules") or []
        if isinstance(m, dict) and m.get("id")
    }


def _manifest_modules_for_router() -> list[dict[str, str]]:
    """Compact catalog for the router LLM (id + summary only)."""

    out: list[dict[str, str]] = []
    for entry in load_manifest().get("modules") or []:
        if not isinstance(entry, dict):
            continue
        mid = str(entry.get("id") or "").strip()
        if not mid:
            continue
        out.append(
            {
                "id": mid,
                "summary": str(entry.get("summary") or ""),
                "always_include": bool(entry.get("always_include")),
            }
        )
    return out


def _sanitize_module_ids(
    raw_ids: list[Any],
    *,
    max_modules: int,
) -> list[str]:
    valid = _valid_module_ids()
    chosen: list[str] = []
    for item in raw_ids:
        mid = str(item).strip()
        if mid in valid and mid not in chosen:
            chosen.append(mid)
    if CORE_MODULE_ID not in chosen:
        chosen.insert(0, CORE_MODULE_ID)
    # Drop duplicate core if appended elsewhere
    seen: set[str] = set()
    ordered: list[str] = []
    for mid in chosen:
        if mid not in seen:
            seen.add(mid)
            ordered.append(mid)
    return ordered[: max(1, max_modules)]


def run_schema_guide_module_router_llm(
    *,
    question: str,
    repair_context: dict[str, Any] | None = None,
    max_modules: int = 5,
) -> tuple[SchemaGuideModuleRouterTurn, dict[str, Any]]:
    """Call small LLM to choose guide module ids; raises on empty/invalid response."""

    cfg = get_config()
    apply_runtime_env(cfg)
    model = cfg.module_router_llm_model_resolved

    always_include = [
        str(m["id"])
        for m in _manifest_modules_for_router()
        if m.get("always_include")
    ]
    if CORE_MODULE_ID not in always_include:
        always_include.insert(0, CORE_MODULE_ID)

    user_payload: dict[str, Any] = {
        "question": question,
        "available_modules": _manifest_modules_for_router(),
        "always_include": always_include,
        "max_modules": max_modules,
    }
    if repair_context:
        user_payload["repair_context"] = {
            "failed_sql": str(repair_context.get("failed_sql") or "")[:4000],
            "database_error": str(repair_context.get("database_error") or "")[:500],
        }
    user_str = json.dumps(user_payload, ensure_ascii=True)

    log: dict[str, Any] = {
        "phase": "schema_guide_module_router",
        "model": model,
        "question": question,
        "user_payload_chars": len(user_str),
        "raw_response": None,
        "error": None,
    }

    kwargs: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": SCHEMA_GUIDE_MODULE_ROUTER_SYSTEM_PROMPT},
            {"role": "user", "content": user_str},
        ],
        "temperature": 0,
        "timeout": cfg.module_router_request_timeout_seconds,
        "response_format": {"type": "json_object"},
        "max_tokens": cfg.module_router_max_output_tokens,
    }

    response = litellm.completion(**kwargs)
    content = response.choices[0].message.content
    log["raw_response"] = content
    if not content:
        raise ValueError("Empty schema guide module router response")

    parsed = parse_json_content(content)
    turn = SchemaGuideModuleRouterTurn.model_validate(_coerce_router_turn_payload(parsed))
    turn.selected_module_ids = _sanitize_module_ids(
        turn.selected_module_ids,
        max_modules=max_modules,
    )
    log["selected_module_ids"] = turn.selected_module_ids
    log["parsed_thought"] = turn.thought
    return turn, log


def select_module_ids_for_question(
    question: str,
    *,
    repair_context: dict[str, Any] | None = None,
    max_modules: int = 5,
) -> tuple[list[str], dict[str, Any]]:
    """Select module ids via LLM router with optional keyword fallback."""

    meta: dict[str, Any] = {"selection_method": None}

    if not modular_guide_available():
        meta["selection_method"] = "keyword_no_manifest"
        return select_module_ids_keyword(
            question, repair_context=repair_context, max_modules=max_modules
        ), meta

    cfg = get_config()
    if cfg.query_generator_module_router_llm_enabled:
        try:
            turn, router_log = run_schema_guide_module_router_llm(
                question=question,
                repair_context=repair_context,
                max_modules=max_modules,
            )
            meta["selection_method"] = "llm"
            meta["router_log"] = router_log
            meta["router_thought"] = turn.thought
            return turn.selected_module_ids, meta
        except Exception as exc:
            logger.warning("Schema guide module router LLM failed: %s", exc)
            meta["router_error"] = str(exc)
            if not cfg.query_generator_module_router_keyword_fallback:
                raise

    meta["selection_method"] = "keyword_fallback"
    ids = select_module_ids_keyword(
        question, repair_context=repair_context, max_modules=max_modules
    )
    return ids, meta
