"""SQLite dev mirror execution (default Individual list)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from pydantic import SecretStr

from app.core.config import AppConfig
from app.models.search_plan import InvestorTypeFilter, SearchPlan
from app.services.dev_sqlite_investor_search import (
    execute_individual_search_sqlite_dev,
    plan_supported_on_sqlite_dev_mirror,
)


def _seed_mirror(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    try:
        conn.executescript(
            """
            DROP VIEW IF EXISTS scheme_master;
            DROP TABLE IF EXISTS public_scheme_master;
            DROP TABLE IF EXISTS public_investor;
            DROP TABLE IF EXISTS public_distributor_investor_mapping;
            CREATE TABLE public_scheme_master (scheme_cd TEXT, allow_broker TEXT);
            INSERT INTO public_scheme_master VALUES ('X1', 'Y');
            CREATE VIEW scheme_master AS SELECT * FROM public_scheme_master;
            CREATE TABLE public_payout_mechanism (pay_mech TEXT, active_flag INTEGER);
            CREATE TABLE sphmf_scheme_setup (cgf_flag TEXT);
            CREATE TABLE sphmf_customer_master (inv_type TEXT);
            CREATE TABLE public_tax_status (
                inv_type_code TEXT, minor_flag TEXT, distributor_flag TEXT, active_flag TEXT);
            CREATE TABLE sphmf_transaction_types (trxntypcod TEXT);
            CREATE VIEW payout_mechanism AS SELECT * FROM public_payout_mechanism;
            CREATE VIEW scheme_setup AS SELECT * FROM sphmf_scheme_setup;
            CREATE VIEW customer_master AS SELECT * FROM sphmf_customer_master;
            CREATE VIEW tax_status AS SELECT * FROM public_tax_status;
            CREATE VIEW transaction_types AS SELECT * FROM sphmf_transaction_types;
            CREATE TABLE public_investor (
                uuid TEXT, first_name TEXT, middle_name TEXT, last_name TEXT,
                pan_number TEXT, dob TEXT, email TEXT, mobile_number TEXT);
            INSERT INTO public_investor VALUES (
                'u1','Ada','','Lovelace','PAN1',NULL,'a@b.c','1');
            CREATE TABLE public_distributor_investor_mapping (
                arn_code TEXT, investor_uuid TEXT, folio_number TEXT);
            INSERT INTO public_distributor_investor_mapping VALUES ('ARN-TEST','u1','f1');
            """
        )
        conn.commit()
    finally:
        conn.close()


def test_sqlite_dev_list_returns_rows(tmp_path: Path) -> None:
    dbf = tmp_path / "m.sqlite"
    _seed_mirror(dbf)
    cfg = AppConfig(
        environment="local",
        dev_local_sqlite_mirror=str(dbf),
        dev_investor_search_use_sqlite=True,
        dev_database_url=SecretStr("postgresql://u:p@localhost:5432/x"),
    )
    assert cfg.dev_use_sqlite_investor_search is True
    plan = SearchPlan(page_limit=10, page_offset=0)
    assert plan_supported_on_sqlite_dev_mirror(plan) is True
    rows = execute_individual_search_sqlite_dev(cfg, plan, "ARN-TEST")
    assert len(rows) == 1
    assert "Ada" in rows[0]["first_name"] and "Lovelace" in rows[0]["first_name"]


def test_sqlite_dev_rejects_filtered_plan(tmp_path: Path) -> None:
    dbf = tmp_path / "m2.sqlite"
    _seed_mirror(dbf)
    cfg = AppConfig(
        environment="local",
        dev_local_sqlite_mirror=str(dbf),
        dev_investor_search_use_sqlite=True,
    )
    plan = SearchPlan()
    plan.investor_type = InvestorTypeFilter.ACTIVE
    assert plan_supported_on_sqlite_dev_mirror(plan) is False
