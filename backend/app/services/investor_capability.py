"""Capability boundaries for Individual investor search (``filter_dp_investor_menu`` only)."""

from __future__ import annotations

import re
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

CAPABILITY_FUTURE_VERSION: Final[str] = (
    "We are working to add broader capabilities in a **future version** "
    "(for example city or geography filters, age or date-of-birth ranges, scheme-type analytics, "
    "and top-N / ranking reports)."
)

# Obvious out-of-scope patterns (fast path before LLM). Case-insensitive.
_UNSUPPORTED_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(
            r"\b(age|aged)\b.*\b(\d{1,3}|thirty|forty|fifty|years?\s+old)\b"
            r"|\b(between|from)\s+\d{1,3}\s+(and|to)\s+\d{1,3}\b.*\b(year|age)\b"
            r"|\bdob\b|\bdate\s+of\s+birth\b",
            re.I,
        ),
        "age or date-of-birth filters",
    ),
    (
        re.compile(
            r"\b(in|from|at)\s+(mumbai|delhi|bangalore|bengaluru|chennai|kolkata|pune|"
            r"ahmedabad|hyderabad|surat|jaipur|lucknow|kanpur|nagpur|indore|thane|"
            r"gurgaon|gurugram|noida|faridabad)\b"
            r"|\binvestors?\s+in\s+[a-z]{3,}\b"
            r"|\bcity\b",
            re.I,
        ),
        "city or geography filters",
    ),
    (
        re.compile(
            r"\btop\s+\d+\b|\bfy\s*\d{2,4}\b|\bfinancial\s+year\b"
            r"|\bequity\b|\bhybrid\b|\bbalanced\b|\bliquid\b|\bcash\s+fund"
            r"|\bscheme[\s-]?type\b|\basset\s+class\b",
            re.I,
        ),
        "scheme-type or ranking analytics",
    ),
    (
        re.compile(r"\bnri\b|\bnon[\s-]?resident\b", re.I),
        "NRI / tax-status filters beyond the portal function",
    ),
    (
        re.compile(
            r"\bpan\b|\bfolio\b|\bmobile\b|\bemail\s+address\b|\baadhaar\b",
            re.I,
        ),
        "PAN, folio, or contact lookup (not supported)",
    ),
]


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


def detect_unsupported_question(question: str) -> str | None:
    """Return a short reason if the question clearly exceeds function capability."""

    text = (question or "").strip()
    if not text:
        return None
    for pattern, reason in _UNSUPPORTED_PATTERNS:
        if pattern.search(text):
            return reason
    return None
