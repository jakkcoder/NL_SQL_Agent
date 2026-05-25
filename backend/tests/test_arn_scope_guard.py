"""ARN scope guard — avoid false blocks on city/account tool args."""

from __future__ import annotations

from app.services.arn_scope_guard import arn_scope_block_reason, is_arn_token

TRUSTED = "ARN-0411"


def test_mumbai_and_account_labels_do_not_block_without_arn_in_query() -> None:
    assert (
        arn_scope_block_reason(
            user_query="I want to know my investors from mumbai location",
            tool_arn_arg="Mumbai",
            trusted_arn=TRUSTED,
        )
        is None
    )
    assert (
        arn_scope_block_reason(
            user_query="just show the investors linked to my account",
            tool_arn_arg="my account",
            trusted_arn=TRUSTED,
        )
        is None
    )


def test_different_arn_in_user_text_still_blocks() -> None:
    assert (
        arn_scope_block_reason(
            user_query="show investors for ARN-9999",
            tool_arn_arg=None,
            trusted_arn=TRUSTED,
        )
        is not None
    )


def test_tool_arn_arg_only_when_arn_shaped() -> None:
    assert is_arn_token("ARN-0411")
    assert not is_arn_token("mumbai")
    assert (
        arn_scope_block_reason(
            user_query="list my investors",
            tool_arn_arg="ARN-9999",
            trusted_arn=TRUSTED,
        )
        is not None
    )
