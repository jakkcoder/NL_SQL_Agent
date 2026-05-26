"""Build the root agent instruction (static prompt + capability notice)."""

from __future__ import annotations

from app.agents.system_prompts import ROOT_AGENT_BASE_INSTRUCTION
from app.services.investor_capability import CAPABILITY_BRIEF, CAPABILITY_DATA_SOURCE


def build_root_agent_instruction() -> str:
    notice = (
        "CAPABILITY (strict):\n"
        f"{CAPABILITY_BRIEF}\n"
        f"{CAPABILITY_DATA_SOURCE}\n"
        "If a question is outside this list, the search tool returns ``out_of_scope`` — "
        "repeat that reply; do not improvise SQL or data."
    )
    return "\n\n".join((ROOT_AGENT_BASE_INSTRUCTION.strip(), notice))
