"""Unit tests for ``public.filter_dp_investor_menu`` SQL builder."""

from __future__ import annotations

from app.services.dp_investor_menu import (
    DpInvestorMenuParams,
    MenuActivityFilter,
    MenuCompositeFilter,
    MenuSystematicFilter,
    build_filter_dp_investor_menu_sql,
    validate_filter_dp_investor_menu_sql,
)


def test_default_menu_call_matches_portal() -> None:
    sql, params = build_filter_dp_investor_menu_sql(
        DpInvestorMenuParams(),
        trusted_arn="ARN-0411",
    )
    validate_filter_dp_investor_menu_sql(sql, params, "ARN-0411")
    assert "public.filter_dp_investor_menu" in sql
    assert "NULL::current_holdings" in sql
    assert params[0] == "ARN-0411"
    assert params[1:4] == ["ALL", "ALL", "ALL"]


def test_sip_and_redemption_filters() -> None:
    sql, params = build_filter_dp_investor_menu_sql(
        DpInvestorMenuParams(
            systematic=MenuSystematicFilter(mode="WITH", plan=["SIP"]),
            activity=MenuActivityFilter(
                mode="WITH",
                activity_type=["REDEMPTION"],
                duration="1 month",
            ),
        ),
        trusted_arn="ARN-0411",
    )
    assert "ROW('true', ARRAY['SIP']" in sql
    assert "ARRAY['REDEMPTION']" in sql
    assert params[0] == "ARN-0411"


def test_name_search_wraps_wildcards() -> None:
    _, params = build_filter_dp_investor_menu_sql(
        DpInvestorMenuParams(searchtext="rahul"),
        trusted_arn="ARN-0411",
    )
    assert params[4] == "%rahul%"
