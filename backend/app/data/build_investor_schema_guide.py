#!/usr/bin/env python3
"""Build ``investor_db_schema_guide.json`` and ``.md`` from ``investor_db_schema_contract.json``.

Fetches one sample row per table from PostgreSQL (or a SQLite mirror) when a database URL is set.

Usage:
    cd backend && export PYTHONPATH=. && python app/data/build_investor_schema_guide.py

    # explicit URL:
    python app/data/build_investor_schema_guide.py --database-url "$DEV_DATABASE_URL"

    # offline partial samples (demo SQLite):
    python scripts/init_dev_sqlite_demo.py
    python app/data/build_investor_schema_guide.py \\
      --database-url sqlite:///$(pwd)/app/data/dev_investor_demo.sqlite
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

from app.core.config import get_config  # noqa: E402
from app.services.investor_schema_contract import load_packaged_schema_contract  # noqa: E402
from app.services.schema_contract_guide import write_schema_guide_files  # noqa: E402

_CATALOG = Path(__file__).resolve().parent / "filter_catalog.json"


def _resolve_database_url(cli_url: str | None) -> str | None:
    if cli_url and cli_url.strip():
        return cli_url.strip()
    cfg = get_config()
    mirror = cfg.dev_local_sqlite_mirror_file_url
    if mirror:
        return mirror
    return cfg.database_url_value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        default=None,
        help="PostgreSQL or sqlite:/// URL for sample rows (else DEV_DATABASE_URL / SQLite mirror)",
    )
    parser.add_argument(
        "--skip-samples",
        action="store_true",
        help="Do not query the database; omit sample_row data",
    )
    args = parser.parse_args()

    try:
        from dotenv import load_dotenv

        load_dotenv(BACKEND / ".env")
    except ImportError:
        pass

    contract = load_packaged_schema_contract()
    if not contract:
        print("Missing investor_db_schema_contract.json", file=sys.stderr)
        return 1
    catalog = None
    if _CATALOG.is_file():
        catalog = json.loads(_CATALOG.read_text(encoding="utf-8"))

    db_url = None if args.skip_samples else _resolve_database_url(args.database_url)
    if db_url:
        print(f"Fetching sample rows from: {db_url[:80]}{'...' if len(db_url) > 80 else ''}")
    else:
        print("No database URL; building guide without sample_row data.")

    jp, mp = write_schema_guide_files(contract, filter_catalog=catalog, database_url=db_url)
    guide = json.loads(jp.read_text(encoding="utf-8"))
    print(f"Wrote {jp} ({jp.stat().st_size:,} bytes)")
    print(f"Wrote {mp} ({mp.stat().st_size:,} bytes)")
    print(f"Tables: {guide.get('table_count')}, join recipes: {len(guide.get('join_recipes') or [])}")
    print(
        f"Sample rows: {guide.get('sample_rows_attached', 0)}/{guide.get('table_count')} "
        f"(source={guide.get('sample_rows_source')})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
