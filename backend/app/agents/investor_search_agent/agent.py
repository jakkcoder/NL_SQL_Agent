"""Root ADK agent for Individual investor search."""

from __future__ import annotations

import sys
from pathlib import Path

# adk web loads this file as investor_search_agent.agent without backend/ on sys.path.
_BACKEND_ROOT = Path(__file__).resolve().parents[3]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from google.adk.agents.llm_agent import Agent
from google.genai import types as genai_types

from app.agents.tools import generate_catalog_sql_query_tool, greeting_tool
from app.core.config import apply_runtime_env, get_config
from app.services.filter_prompts import build_root_agent_instruction


config = get_config()
apply_runtime_env(config)


def _root_tools():
    return [
        greeting_tool,
        generate_catalog_sql_query_tool,
    ]


def _root_agent_generate_config() -> genai_types.GenerateContentConfig:
    """Maps AppConfig LLM knobs into ADK request config.

    Use a string ``model`` id on ``Agent`` (not ``LiteLlm``) so ADK Web ``/dev/build_graph``
    can serialize the agent graph without hitting ``LiteLLMClient`` pydantic errors.
    LiteLLM still receives temperature / max tokens via ``LlmRequest.config`` for Bedrock.
    """

    llm = config.llm
    gc_kwargs: dict = {"temperature": float(llm.temperature)}
    if llm.max_output_tokens is not None:
        gc_kwargs["max_output_tokens"] = int(llm.max_output_tokens)
    return genai_types.GenerateContentConfig(**gc_kwargs)


root_agent = Agent(
    model=config.llm.model,  # small/fast Bedrock model (BEDROCK_MODEL_ID / BEDROCK_ROOT_MODEL_ID)
    name="investor_search_agent",
    description="Distributor investor assistant: greeting or catalog-backed SQL generation.",
    instruction=build_root_agent_instruction(),
    tools=_root_tools(),
    generate_content_config=_root_agent_generate_config(),
)
