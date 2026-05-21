#!/usr/bin/env python3
"""Refresh filter_catalog.json from DB distinct values + contract enums.

Usage (from backend/):
  PYTHONPATH=. python scripts/refresh_filter_catalog.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import get_config  # noqa: E402
from app.services.filter_catalog import (  # noqa: E402
    GENERATED_CATALOG_PATH,
    refresh_catalog_from_db,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh investor filter catalog from database.")
    parser.add_argument(
        "--output",
        type=Path,
        default=GENERATED_CATALOG_PATH,
        help=f"Output JSON path (default: {GENERATED_CATALOG_PATH})",
    )
    parser.add_argument("--pretty", action="store_true", help="Print catalog JSON to stdout")
    args = parser.parse_args()

    config = get_config()
    catalog = refresh_catalog_from_db(
        database_url=config.database_url_value,
        statement_timeout_ms=config.database.statement_timeout_ms,
        output_path=args.output,
    )

    print(f"Wrote catalog to {args.output} (source={catalog.source}, loaded_at={catalog.loaded_at})")
    for key in sorted(catalog.to_dict().get("filters", {})):
        count = len(catalog.get_values(key))
        print(f"  {key}: {count} values")

    if args.pretty:
        print(json.dumps(catalog.to_dict(), indent=2, ensure_ascii=True))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
