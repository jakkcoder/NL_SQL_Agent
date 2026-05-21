"""Root ADK agent for Individual investor search."""

from __future__ import annotations

import sys
from pathlib import Path

# adk web loads this file as investor_search_agent.agent without backend/ on sys.path.
_BACKEND_ROOT = Path(__file__).resolve().parents[3]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from google.adk.agents.llm_agent import Agent
from google.adk.models.lite_llm import LiteLlm

from app.services.filter_prompts import build_root_agent_instruction
from app.agents.tools import (
    analyze_search_arguments_tool,
    detect_intent_tool,
    fetch_investor_schema_contract_tool,
    greeting_tool,
    run_dynamic_investor_sql_tool,
    search_investors_tool,
    unsupported_banking_tool,
)
from app.core.config import apply_runtime_env, get_config


config = get_config()
apply_runtime_env(config)


def _root_tools():
    tools = [
        detect_intent_tool,
        fetch_investor_schema_contract_tool,
        greeting_tool,
        unsupported_banking_tool,
        analyze_search_arguments_tool,
        search_investors_tool,
    ]
    if config.dynamic_investor_sql_enabled:
        tools.append(run_dynamic_investor_sql_tool)
    return tools


def _resolve_agent_model():
    llm = config.llm
    if llm.uses_bedrock:
        kwargs = {"temperature": llm.temperature}
        if llm.max_output_tokens:
            kwargs["max_tokens"] = llm.max_output_tokens
        return LiteLlm(model=llm.model, **kwargs)
    return llm.model


root_agent = Agent(
    model=_resolve_agent_model(),
    name="investor_search_agent",
    description="Routes banking investor-search requests using ADK session state and safe tools.",
    instruction=build_root_agent_instruction(),
    tools=_root_tools(),
)
