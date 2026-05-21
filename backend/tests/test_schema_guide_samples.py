"""Schema guide sample_row helpers."""

from __future__ import annotations

from app.services.schema_contract_guide import (
    _json_safe_sample_value,
    _sample_row_from_db_row,
    build_schema_guide,
)
from app.services.investor_schema_contract import load_packaged_schema_contract


def test_sample_row_from_db_row_filters_columns() -> None:
    row = _sample_row_from_db_row(
        {"uuid": "abc", "dob": "1990-01-15", "secret": "x"},
        ["uuid", "dob"],
    )
    assert row == {"uuid": "abc", "dob": "1990-01-15"}
    assert "secret" not in row


def test_json_safe_sample_value_truncates_long_strings() -> None:
    assert len(_json_safe_sample_value("a" * 300)) <= 160


def test_build_schema_guide_without_database_has_no_samples() -> None:
    contract = load_packaged_schema_contract()
    assert contract is not None
    guide = build_schema_guide(contract, database_url=None)
    assert guide.get("sample_rows_attached", 0) == 0
    assert all(t.get("sample_row") is None for t in guide.get("tables", []))
