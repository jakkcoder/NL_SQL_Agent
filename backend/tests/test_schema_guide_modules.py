"""Modular schema guide selection and payload size."""

from __future__ import annotations

from app.services.schema_guide_modules import (
    build_guide_payload_for_question,
    modular_guide_available,
    select_module_ids_keyword,
)


def test_modular_files_exist() -> None:
    assert modular_guide_available()


def test_mumbai_selects_geography_not_sip_noise() -> None:
    ids = select_module_ids_keyword("Show my investors in Mumbai")
    assert "core_arn_investor" in ids
    assert "geography_city" in ids
    assert "sip_systematic" not in ids


def test_sip_hybrid_selects_sip_and_schemes() -> None:
    ids = select_module_ids_keyword(
        "Active SIPs above 5,000 per month in hybrid funds."
    )
    assert "sip_systematic" in ids
    assert "holdings_schemes" in ids
    assert "geography_city" not in ids


def test_modular_payload_under_context_budget() -> None:
    q = "Investors who did redemption in last quarter for equity funds."
    raw, mods, meta = build_guide_payload_for_question(q, max_chars=48_000)
    assert meta.get("selection_method") in ("llm", "keyword_fallback")
    assert len(raw) < 45_000
    assert "activity_transactions" in mods
    assert "processed_trxns" in raw
