"""parse_json_content edge cases (repair / generator responses)."""

from __future__ import annotations

import json

import pytest

from app.services.llm_json import parse_json_content
from app.services.query_flow_router import _normalize_generator_payload


def test_parse_json_content_accepts_single_element_array() -> None:
    raw = '[{"thought": "t", "sql": "SELECT 1", "parameters": ["ARN-0411"]}]'
    out = parse_json_content(raw)
    assert out["sql"] == "SELECT 1"


def test_parse_json_content_rejects_bare_array_of_strings() -> None:
    with pytest.raises(ValueError, match="one object"):
        parse_json_content('["thought", "sql"]')


def test_normalize_generator_payload_rejects_non_object() -> None:
    with pytest.raises(ValueError, match="must be an object"):
        _normalize_generator_payload(["ARN-0411"])


def test_normalize_generator_payload_defaults_missing_thought() -> None:
    out = _normalize_generator_payload(
        {"sql": "SELECT 1", "parameters": ["ARN-0411"]},
    )
    assert out["thought"] == ""
    assert out["sql"] == "SELECT 1"


def test_parse_json_content_unwraps_double_encoded_string() -> None:
    inner = {
        "thought": "age filter",
        "sql": "SELECT i.uuid FROM public.investor i WHERE AGE(i.dob) BETWEEN %s AND %s LIMIT 100",
        "parameters": ["ARN-0411", 30, 40],
    }
    raw = json.dumps(json.dumps(inner))
    out = parse_json_content(raw)
    assert out["parameters"] == ["ARN-0411", 30, 40]


def test_parse_json_content_repairs_multiline_sql_in_json_string() -> None:
    inner_obj = {
        "thought": "age",
        "sql": "SELECT 1\nFROM public.investor i\nWHERE AGE(i.dob) BETWEEN 30 AND 40\nLIMIT 100",
        "parameters": ["ARN-0411"],
    }
    # Simulate Bedrock: outer JSON string whose inner payload has raw newlines in sql
    broken_inner = (
        '{"thought": "age", "sql": "SELECT 1\nFROM public.investor i\n'
        'WHERE AGE(i.dob) BETWEEN 30 AND 40\nLIMIT 100", "parameters": ["ARN-0411"]}'
    )
    raw = json.dumps(broken_inner)
    out = parse_json_content(raw)
    assert "AGE" in out["sql"]
    assert out["parameters"] == ["ARN-0411"]


def test_parse_json_content_extracts_object_after_preamble() -> None:
    inner = json.dumps(
        {
            "thought": "t",
            "sql": "SELECT 1 AS n FROM public.distributor_investor_mapping WHERE arn_code = %s LIMIT 1",
            "parameters": ["ARN-0411"],
        }
    )
    raw = f"Here is the JSON:\n{inner}"
    out = parse_json_content(raw)
    assert "arn_code" in out["sql"]
