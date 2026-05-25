"""Block cross-ARN investor queries (session ARN vs user text / tool args)."""

from __future__ import annotations

import re
# Distributor ARN tokens as used in HDFC systems (e.g. ARN-0411, ARN-TEST).
_ARN_TOKEN = re.compile(r"\b(ARN-[A-Z0-9]+)\b", re.IGNORECASE)

ARN_SCOPE_REPLY = (
    "I can only show investors linked to your distributor account. "
    "I cannot look up or list investors for another ARN or distributor."
)


def normalize_arn(value: str) -> str:
    return value.strip().upper()


def is_arn_token(value: str) -> bool:
    """True only for distributor ARN tokens (e.g. ARN-0411), not cities or free text."""

    if not value or not value.strip():
        return False
    return bool(_ARN_TOKEN.fullmatch(value.strip()))


def extract_arn_codes_from_text(text: str) -> list[str]:
    if not text:
        return []
    return [normalize_arn(m.group(1)) for m in _ARN_TOKEN.finditer(text)]


def arn_scope_block_reason(
    *,
    user_query: str,
    tool_arn_arg: str | None,
    trusted_arn: str,
) -> str | None:
    """Return a user-facing block message if the request must not run; else None."""

    trusted = normalize_arn(trusted_arn)
    if not trusted:
        return None

    if tool_arn_arg and is_arn_token(tool_arn_arg):
        arg = normalize_arn(tool_arn_arg)
        if arg != trusted:
            return ARN_SCOPE_REPLY

    for code in extract_arn_codes_from_text(user_query):
        if code != trusted:
            return ARN_SCOPE_REPLY

    return None
