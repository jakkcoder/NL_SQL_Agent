"""Post-execute dedupe when SQL returns one row per folio."""

from app.services.catalog_sql_executor import dedupe_investor_result_rows


def test_dedupe_by_uuid_keeps_first_row() -> None:
    rows = [
        {"uuid": "u1", "first_name": "A", "folio_number": "1"},
        {"uuid": "u1", "first_name": "A", "folio_number": "2"},
        {"uuid": "u2", "first_name": "B", "folio_number": "3"},
    ]
    out = dedupe_investor_result_rows(rows)
    assert len(out) == 2
    assert out[0]["folio_number"] == "1"
    assert out[1]["uuid"] == "u2"


def test_dedupe_investor_uuid_column() -> None:
    rows = [
        {"investor_uuid": "x", "email": "a@b.com"},
        {"investor_uuid": "x", "email": "a@b.com"},
    ]
    assert len(dedupe_investor_result_rows(rows)) == 1


def test_dedupe_preserves_rows_without_uuid() -> None:
    rows = [{"first_name": "A"}, {"first_name": "B"}]
    assert len(dedupe_investor_result_rows(rows)) == 2
