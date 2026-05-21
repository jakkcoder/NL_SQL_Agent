"""Filter catalog refresh from a local SQLite mirror."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from app.services.filter_catalog import refresh_catalog_from_db


def _minimal_catalog_mirror(path: Path) -> None:
    """Create SQLite with empty tables + one scheme row (matches ``catalog_sqlite`` queries)."""

    conn = sqlite3.connect(str(path))
    try:
        conn.executescript(
            """
            DROP TABLE IF EXISTS scheme_master;
            DROP TABLE IF EXISTS payout_mechanism;
            DROP TABLE IF EXISTS scheme_setup;
            DROP TABLE IF EXISTS customer_master;
            DROP TABLE IF EXISTS tax_status;
            DROP TABLE IF EXISTS transaction_types;

            CREATE TABLE scheme_master (scheme_cd TEXT, allow_broker TEXT);
            INSERT INTO scheme_master (scheme_cd, allow_broker) VALUES ('__TEST_SCH__', 'Y');

            CREATE TABLE payout_mechanism (pay_mech TEXT, active_flag INTEGER);
            CREATE TABLE scheme_setup (cgf_flag TEXT);
            CREATE TABLE customer_master (inv_type TEXT);
            CREATE TABLE tax_status (
                inv_type_code TEXT,
                minor_flag TEXT,
                distributor_flag TEXT,
                active_flag TEXT
            );
            CREATE TABLE transaction_types (trxntypcod TEXT);
            """
        )
        conn.commit()
    finally:
        conn.close()


def test_refresh_catalog_merges_scheme_codes_from_sqlite(tmp_path: Path) -> None:
    db_path = tmp_path / "mirror.sqlite"
    _minimal_catalog_mirror(db_path)
    url = f"sqlite:///{db_path.resolve()}"
    cat = refresh_catalog_from_db(url, output_path=tmp_path / "filter_catalog.test.json")
    assert cat.source == "sqlite+contract"
    assert "__TEST_SCH__" in cat.get_values("scheme_codes")
