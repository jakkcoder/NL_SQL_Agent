"""SQL generator sends guide + question only (no filter catalog in LLM payload)."""

from __future__ import annotations

import json
from unittest.mock import patch

from app.services.schema_contract_guide import load_schema_guide
from app.services.query_flow_router import run_catalog_sql_generator_llm


def test_guide_only_payload_keys() -> None:
    guide = load_schema_guide()
    assert guide is not None

    captured: dict = {}

    def _fake_completion(**kwargs):
        captured["user_content"] = kwargs["messages"][1]["content"]
        class _Msg:
            content = json.dumps(
                {
                    "thought": "test",
                    "sql": "SELECT 1 FROM public.distributor_investor_mapping WHERE arn_code = %s LIMIT 1",
                    "parameters": ["ARN-0411"],
                }
            )

        class _Choice:
            message = _Msg()

        class _Resp:
            choices = [_Choice()]

        return _Resp()

    with patch("app.services.query_flow_router.litellm.completion", _fake_completion):
        run_catalog_sql_generator_llm(
            question="Investor with Age between 30 and 40",
            trusted_arn="ARN-0411",
            schema_contract=guide,
            schema_contract_max_chars=120_000,
            guide_only=True,
        )

    payload = json.loads(captured["user_content"])
    assert payload.keys() >= {
        "session_arn",
        "investor_schema_guide_json",
        "question",
    }
    assert "filter_catalog_json" not in payload
    assert payload["question"] == "Investor with Age between 30 and 40"
    assert "filter_catalog_json" not in payload
    guide_inner = json.loads(payload["investor_schema_guide_json"])
    assert guide_inner.get("contract_kind") == "investor_schema_guide"
    assert guide_inner.get("table_count", 0) >= 1
    if "selected_guide_modules" in payload:
        assert isinstance(payload["selected_guide_modules"], list)
