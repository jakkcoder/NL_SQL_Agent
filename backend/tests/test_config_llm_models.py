"""Bedrock root vs query-generator model resolution."""

from __future__ import annotations

from app.core.config import AppConfig


def test_bedrock_root_and_query_generator_defaults() -> None:
    cfg = AppConfig(
        llm_provider="bedrock",
        bedrock_model_id="anthropic.claude-3-haiku-20240307-v1:0",
        bedrock_query_generator_model_id="anthropic.claude-3-sonnet-20240229-v1:0",
    )
    assert cfg.llm.model == "bedrock/anthropic.claude-3-haiku-20240307-v1:0"
    assert cfg.query_generator_llm_model_resolved == (
        "bedrock/anthropic.claude-3-sonnet-20240229-v1:0"
    )


def test_bedrock_root_model_id_override() -> None:
    cfg = AppConfig(
        llm_provider="bedrock",
        bedrock_model_id="anthropic.claude-3-haiku-20240307-v1:0",
        bedrock_root_model_id="amazon.nova-micro-v1:0",
    )
    assert cfg.llm.model == "bedrock/amazon.nova-micro-v1:0"


def test_query_generator_llm_model_overrides_bedrock_default() -> None:
    cfg = AppConfig(
        llm_provider="bedrock",
        query_generator_llm_model="anthropic.claude-3-sonnet-20240229-v1:0",
    )
    assert cfg.query_generator_llm_model_resolved == (
        "bedrock/anthropic.claude-3-sonnet-20240229-v1:0"
    )
