#!/usr/bin/env python3
"""Create a tiny SQLite file for local dev (no PostgreSQL required).

Builds ``app/data/dev_investor_demo.sqlite`` with:

- Physical catalog tables + compatibility views (same layout as ``sync_filter_catalog_sqlite``)
- ``public_investor`` + ``public_distributor_investor_mapping`` with one demo row

Use with::

    APP_ENV=local
    DEV_LOCAL_SQLITE_MIRROR=app/data/dev_investor_demo.sqlite
    DEV_INVESTOR_SEARCH_USE_SQLITE=true

Optional: leave ``DEV_DATABASE_URL`` unset for fully offline catalog + search
(LLM calls still need cloud credentials).
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
DEFAULT_OUT = BACKEND_DIR / "app" / "data" / "dev_investor_demo.sqlite"

# UUID + ARN aligned with .env.example DEFAULT_DEV_ARN
_DEMO_UUID = "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"
_DEFAULT_ARN = "ARN-0411"

_DDL = """
PRAGMA foreign_keys=OFF;

DROP VIEW IF EXISTS scheme_master;
DROP VIEW IF EXISTS payout_mechanism;
DROP VIEW IF EXISTS scheme_setup;
DROP VIEW IF EXISTS customer_master;
DROP VIEW IF EXISTS tax_status;
DROP VIEW IF EXISTS transaction_types;

DROP TABLE IF EXISTS public_investor;
DROP TABLE IF EXISTS public_distributor_investor_mapping;

DROP TABLE IF EXISTS public_scheme_master;
DROP TABLE IF EXISTS public_payout_mechanism;
DROP TABLE IF EXISTS sphmf_scheme_setup;
DROP TABLE IF EXISTS sphmf_customer_master;
DROP TABLE IF EXISTS public_tax_status;
DROP TABLE IF EXISTS sphmf_transaction_types;

CREATE TABLE public_scheme_master (scheme_cd TEXT, allow_broker TEXT);
INSERT INTO public_scheme_master (scheme_cd, allow_broker) VALUES ('DEMO-SCHEME', 'Y');

CREATE TABLE public_payout_mechanism (pay_mech TEXT, active_flag INTEGER);
INSERT INTO public_payout_mechanism (pay_mech, active_flag) VALUES ('NEFT', 1);

CREATE TABLE sphmf_scheme_setup (cgf_flag TEXT);
INSERT INTO sphmf_scheme_setup (cgf_flag) VALUES ('N');

CREATE TABLE sphmf_customer_master (inv_type TEXT);
CREATE TABLE public_tax_status (
    inv_type_code TEXT,
    minor_flag TEXT,
    distributor_flag TEXT,
    active_flag TEXT
);
INSERT INTO public_tax_status (inv_type_code, minor_flag, distributor_flag, active_flag)
VALUES ('IND', 'N', 'Y', 'Y');

CREATE TABLE sphmf_transaction_types (trxntypcod TEXT);
INSERT INTO sphmf_transaction_types (trxntypcod) VALUES ('P');

CREATE VIEW scheme_master AS SELECT * FROM public_scheme_master;
CREATE VIEW payout_mechanism AS SELECT * FROM public_payout_mechanism;
CREATE VIEW scheme_setup AS SELECT * FROM sphmf_scheme_setup;
CREATE VIEW customer_master AS SELECT * FROM sphmf_customer_master;
CREATE VIEW tax_status AS SELECT * FROM public_tax_status;
CREATE VIEW transaction_types AS SELECT * FROM sphmf_transaction_types;

CREATE TABLE public_investor (
    uuid TEXT,
    first_name TEXT,
    middle_name TEXT,
    last_name TEXT,
    pan_number TEXT,
    dob TEXT,
    email TEXT,
    mobile_number TEXT
);
INSERT INTO public_investor (
    uuid, first_name, middle_name, last_name, pan_number, dob, email, mobile_number
) VALUES (
    '{uuid}', 'Demo', '', 'Investor', 'ABCDE1234F', '1990-01-01',
    'demo.investor@example.com', '9999999999'
);

CREATE TABLE public_distributor_investor_mapping (
    arn_code TEXT,
    investor_uuid TEXT,
    folio_number TEXT
);
INSERT INTO public_distributor_investor_mapping (arn_code, investor_uuid, folio_number)
VALUES ('{arn}', '{uuid}', 'F000001');
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT, help="SQLite output path")
    parser.add_argument("--arn", default=_DEFAULT_ARN, help="ARN code for the demo mapping row")
    args = parser.parse_args()

    out = args.output
    out.parent.mkdir(parents=True, exist_ok=True)
    ddl = _DDL.format(uuid=_DEMO_UUID, arn=args.arn.strip())
    conn = sqlite3.connect(str(out))
    try:
        conn.executescript(ddl)
        conn.commit()
    finally:
        conn.close()
    print(f"Wrote {out}")
    print("Set in backend/.env (development):")
    print(f"  DEV_LOCAL_SQLITE_MIRROR=app/data/{out.name}")
    print("  DEV_INVESTOR_SEARCH_USE_SQLITE=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
