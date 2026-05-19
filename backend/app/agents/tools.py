from typing import Any

from app.models.chat import ChatMessage
from app.services.intent_parser import parse_investor_search_intent
from app.services.plan_validator import PlanValidator


def parse_investor_search_intent_tool(query: str) -> dict[str, Any]:
    """Parse a distributor's message into the MVP's structured SearchPlan."""

    plan = parse_investor_search_intent(query=query, messages=[], page_limit=25, page_offset=0)
    validation = PlanValidator().validate(plan)
    return {
        "plan": plan.model_dump(mode="json"),
        "validation": {
            "status": validation.status,
            "message": validation.message,
            "can_execute": validation.can_execute,
        },
    }


def parse_with_context(query: str, messages: list[ChatMessage], page_limit: int, page_offset: int) -> dict[str, Any]:
    """Backend helper used by FastAPI, mirroring the ADK tool contract."""

    plan = parse_investor_search_intent(
        query=query,
        messages=messages,
        page_limit=page_limit,
        page_offset=page_offset,
    )
    validation = PlanValidator().validate(plan)
    return {
        "plan": plan,
        "validation": validation,
    }
