"""Capability boundaries for Individual investor search (``filter_dp_investor_menu`` only)."""

from __future__ import annotations

from typing import Final

# What the assistant can do today (portal function parameters only).
CAPABILITY_BRIEF: Final[str] = (
    "I can help you answer questions related to **Individual** investor lists and filters "
    "for your distributor book—for example: show all investors; eligibility (with/without email); "
    "OTM registered or not; active or dormant investors; CGF, minor, or other subtypes; investors "
    "with or without current holdings; SIP, STP, SWP, and other systematic plans; recent purchase, "
    "redemption, switch, or SIP activity; and searching by investor name."
)

CAPABILITY_DATA_SOURCE: Final[str] = (
    "All answers use **only** the approved warehouse function "
    "``public.filter_dp_investor_menu``. I never query underlying tables directly or generate "
    "custom SQL."
)

CAPABILITY_UNSUPPORTED_BODY: Final[str] = (
    "This question is **not available** with the current model capability. "
    f"{CAPABILITY_DATA_SOURCE} "
    "Your request needs filters or analytics that this function does not support yet."
)

QUERY_GENERATION_FAILED_REPLY: Final[str] = (
    "I am not able to generate the query for your request right now. "
    "Please try rephrasing your question using the supported Individual investor filters "
    "(for example: show my investors, investors with active SIP, or find investor named …)."
)


CAPABILITY_FUTURE_VERSION: Final[str] = (
    "We are working to add broader capabilities in a **future version** "
    "(for example city or geography filters, age or date-of-birth ranges, scheme-type analytics, "
    "and top-N / ranking reports)."
)

def build_capability_greeting() -> str:
    return (
        "Hi, I am a chatbot from HDFC Mutual Fund.\n\n"
        f"{CAPABILITY_BRIEF}\n\n"
        f"{CAPABILITY_DATA_SOURCE}\n\n"
        "Ask me a question about your Individual investors—for example, "
        "\"show my investors\" or \"investors with active SIP\"."
    )


def build_unsupported_capability_reply(detail: str | None = None) -> str:
    """Standard reply when the question cannot be served via ``filter_dp_investor_menu``."""

    lines = [
        CAPABILITY_BRIEF,
        "",
        CAPABILITY_UNSUPPORTED_BODY,
    ]
    if detail:
        lines.append(f"Specifically: {detail.rstrip('.')}.")
    lines.extend(["", CAPABILITY_FUTURE_VERSION])
    return "\n".join(lines)


def build_query_generation_failed_reply() -> str:
    """After one repair attempt, when Sonnet still cannot produce a valid function call."""

    return QUERY_GENERATION_FAILED_REPLY
