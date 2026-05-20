from google.adk.agents.llm_agent import Agent
from google.adk.models.lite_llm import LiteLlm

from app.agents.instructions import ROOT_AGENT_INSTRUCTION
from app.agents.tools import (
    ask_investor_type_tool,
    detect_intent_tool,
    greeting_tool,
    search_investors_tool,
    unsupported_banking_tool,
    update_routing_state_tool,
)
from app.core.config import apply_runtime_env, get_config


config = get_config()
apply_runtime_env(config)


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
    description="Routes banking investor-search requests to the correct safe tool.",
    instruction=ROOT_AGENT_INSTRUCTION,
    tools=[
        detect_intent_tool,
        greeting_tool,
        ask_investor_type_tool,
        unsupported_banking_tool,
        update_routing_state_tool,
        search_investors_tool,
    ],
)
