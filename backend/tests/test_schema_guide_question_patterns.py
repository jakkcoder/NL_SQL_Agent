"""Curated question_patterns on investor schema guide."""

from __future__ import annotations

from app.services.schema_contract_guide import load_schema_guide


def test_load_schema_guide_includes_question_patterns() -> None:
    load_schema_guide.cache_clear()
    guide = load_schema_guide()
    assert guide is not None
    patterns = guide.get("question_patterns")
    assert isinstance(patterns, list)
    assert len(patterns) >= 10
    ids = {p["id"] for p in patterns if isinstance(p, dict)}
    assert "active_sip_hybrid_min_amount" in ids
    assert "age_range" in ids
    vocab = guide.get("filter_vocabulary")
    assert isinstance(vocab, dict)
    assert "activity" in vocab
    assert "investor_row_dedup" in vocab
    assert "replace(trim(concat_ws" in str(vocab.get("name_search", ""))
    rules = guide.get("sql_rules") or {}
    assert "investor_row_dedup" in rules
    assert "investor_name_search" in rules
    age = next(p for p in patterns if p.get("id") == "age_range")
    assert "DISTINCT ON (i.uuid)" in age.get("sql_skeleton", "")
    name_pat = next(p for p in patterns if p.get("id") == "name_multi_city")
    sk = name_pat.get("sql_skeleton", "")
    assert "replace(trim(concat_ws" in sk
    assert "lower(i.first_name) ILIKE" not in sk
    last_red = next(p for p in patterns if p.get("id") == "investor_last_redemption_date")
    assert "last_redemption_date" in last_red.get("sql_skeleton", "")
    assert "LEFT JOIN" in last_red.get("sql_skeleton", "")
