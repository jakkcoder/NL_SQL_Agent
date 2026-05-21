"""Schema guide is included in catalog SQL generator LLM payload."""

from __future__ import annotations

from app.services.investor_schema_contract import schema_contract_for_sql_generator
from app.services.schema_contract_guide import (
    guide_json_path,
    load_schema_guide,
    serialize_schema_guide_for_prompt,
)


def test_schema_guide_file_exists() -> None:
    path = guide_json_path()
    assert path.is_file(), f"missing {path}; run app/data/build_investor_schema_guide.py"
    guide = load_schema_guide()
    assert guide is not None
    assert guide.get("contract_kind") == "investor_schema_guide"
    assert isinstance(guide.get("tables"), list) and len(guide["tables"]) >= 1
    assert isinstance(guide.get("join_recipes"), list) and len(guide["join_recipes"]) >= 1


def test_sql_generator_uses_guide_not_raw_contract() -> None:
    guide = schema_contract_for_sql_generator()
    assert guide is not None
    assert guide.get("contract_kind") == "investor_schema_guide"
    raw = serialize_schema_guide_for_prompt(guide, max_chars=200_000)
    assert "investor_schema_guide" in raw or "distributor_investor_mapping" in raw
    assert "sphmf.customer_master" in raw
    assert "city" in raw
    assert len(raw) < 200_000
