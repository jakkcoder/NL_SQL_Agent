from google.adk.agents.llm_agent import Agent

from app.agents.instructions import ROOT_AGENT_INSTRUCTION
from app.agents.tools import parse_investor_search_intent_tool
from app.core.settings import get_settings


settings = get_settings()

root_agent = Agent(
    model=settings.google_adk_model,
    name="investor_search_agent",
    description="Plans safe investor search requests for the distributor portal MVP.",
    instruction=ROOT_AGENT_INSTRUCTION,
    tools=[parse_investor_search_intent_tool],
)
