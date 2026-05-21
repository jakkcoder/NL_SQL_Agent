#!/usr/bin/env python3
"""Refresh investor_db_schema_contract.json from PostgreSQL (on-demand).

The backend also auto-refreshes this file on the first investor search-plan build in each
ADK session (non-pytest). Use this script for offline refresh or CI without the app.

Run from repo `backend/` (recommended):

    cd backend && export PYTHONPATH=. && python app/data/export_investor_schema_contract.py

Requires DEV_DATABASE_URL in `backend/.env` (or the environment).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError as exc:  # pragma: no cover
    raise SystemExit("Install python-dotenv (backend requirements).") from exc

# Script lives in app/data/ — backend root is parents[2]
_BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.services.investor_schema_contract import build_full_schema_contract  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output JSON path (default: investor_db_schema_contract.json next to this script)",
    )
    parser.add_argument(
        "--database-url",
        type=str,
        default=None,
        help="Override DEV_DATABASE_URL (otherwise from env / backend/.env)",
    )
    args = parser.parse_args()

    load_dotenv(_BACKEND_ROOT / ".env")

    url = args.database_url or os.environ.get("DEV_DATABASE_URL")
    if not url:
        print("ERROR: Set DEV_DATABASE_URL or pass --database-url", file=sys.stderr)
        return 1

    here = Path(__file__).resolve().parent
    out_path = args.output or (here / "investor_db_schema_contract.json")

    contract = build_full_schema_contract(url)
    out_path.write_text(json.dumps(contract, indent=2, default=str), encoding="utf-8")

    from app.services.schema_contract_guide import write_schema_guide_files  # noqa: E402

    catalog_path = here / "filter_catalog.json"
    catalog = None
    if catalog_path.is_file():
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    gj, gm = write_schema_guide_files(contract, filter_catalog=catalog, database_url=url)
    print(f"Wrote {gj.name} and {gm.name}")

    total_cols = sum(int(t["column_count_information_schema"]) for t in contract["tables"])
    print(f"Wrote {out_path}")
    print(f"tables: {contract['tables_found']}  issues: {contract['tables_missing_in_database']}")
    print(f"total_columns: {total_cols}")
    return 0 if not contract["tables_missing_in_database"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
