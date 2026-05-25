#!/usr/bin/env python3
"""Split investor_db_schema_guide.json into modular files under app/data/schema_guide_modules/."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.services.investor_schema_question_patterns import (  # noqa: E402
    EXTRA_JOIN_RECIPES,
    FILTER_VOCABULARY,
    QUESTION_PATTERNS,
    enrich_investor_schema_guide,
)
from app.services.schema_contract_guide import GUIDE_JSON_PATH, JOIN_RECIPES  # noqa: E402

OUT_DIR = BACKEND / "app" / "data" / "schema_guide_modules"

TABLE_TO_MODULE: dict[str, str] = {
    "public.distributor_investor_mapping": "core_arn_investor",
    "public.investor": "core_arn_investor",
    "sphmf.customer_master": "geography_city",
    "public.tax_status": "tax_profile",
    "public.scheme_master": "holdings_schemes",
    "sphmf.scheme_setup": "holdings_schemes",
    "sphmf.customer_schemes": "dormant_holdings",
    "sphmf.processed_trxns": "activity_transactions",
    "sphmf.transaction_types": "activity_transactions",
    "sphmf.sipstp": "sip_systematic",
    "public.payout_mechanism": "banking_otm",
    "sphmf.multiple_bank": "banking_otm",
    "sphmf.dtp_regn": "sip_systematic",
    "sphmf.trigger_trxn": "activity_transactions",
}

PATTERN_TO_MODULE: dict[str, str] = {
    "city_mumbai": "geography_city",
    "age_range": "investor_filters",
    "redemption_equity_last_quarter": "activity_transactions",
    "investor_last_redemption_date": "activity_transactions",
    "active_sip_hybrid_min_amount": "sip_systematic",
    "dormant_inactive": "dormant_holdings",
    "top_purchases_fy25": "activity_transactions",
    "name_multi_city": "geography_city",
    "nri_investors": "tax_profile",
    "minor_not_in_cgf": "tax_profile",
    "no_active_sip": "sip_systematic",
    "liquid_only_funds": "holdings_schemes",
}

RECIPE_TO_MODULE: dict[str, str] = {
    "arn_scope_anchor": "core_arn_investor",
    "investor_identity": "core_arn_investor",
    "folio_kyc_city": "geography_city",
    "otm_bank": "banking_otm",
    "holdings_units": "holdings_schemes",
    "active_sipstp": "sip_systematic",
    "investor_activity": "activity_transactions",
    "minor_tax_status": "tax_profile",
    "cgf_schemes": "holdings_schemes",
    "nri_tax_status": "tax_profile",
    "redemption_activity": "activity_transactions",
    "purchase_activity": "activity_transactions",
    "sip_amount_active": "sip_systematic",
    "no_active_sip": "sip_systematic",
}

MANIFEST_MODULES: list[dict[str, Any]] = [
    {
        "id": "core_arn_investor",
        "always_include": True,
        "summary": "Mandatory ARN scope via distributor_investor_mapping; investor identity (name, PAN, email, mobile, dob).",
        "keywords": ["investor", "investors", "my", "list", "show", "all"],
        "sql_table_markers": ["distributor_investor_mapping", "public.investor"],
    },
    {
        "id": "geography_city",
        "summary": "City and folio KYC via sphmf.customer_master; ILIKE on city; name + multi-city OR.",
        "keywords": [
            "mumbai",
            "ahmedabad",
            "city",
            "cities",
            "location",
            "geography",
            "named",
            "bhavin",
            "name",
        ],
        "sql_table_markers": ["customer_master"],
    },
    {
        "id": "investor_filters",
        "summary": "Age from public.investor.dob using AGE() or EXTRACT(YEAR FROM AGE(...)).",
        "keywords": ["age", "aged", "years", "year", "between", "dob", "30", "40"],
        "sql_table_markers": [".dob", "age("],
    },
    {
        "id": "activity_transactions",
        "summary": "Purchases/redemptions via processed_trxns + transaction_types (trxndbcr P/R); FY and quarter windows on trxn_date.",
        "keywords": [
            "redemption",
            "redeemed",
            "purchase",
            "purchases",
            "quarter",
            "fy25",
            "fy",
            "financial year",
            "equity",
            "transaction",
            "top",
        ],
        "phrase_patterns": [r"last quarter", r"fy\s*25"],
        "sql_table_markers": ["processed_trxns", "transaction_types"],
    },
    {
        "id": "sip_systematic",
        "summary": "Active SIP/STP on sphmf.sipstp (cease_dt, to_date, atrxn_type, amount); scheme_master for hybrid filter.",
        "keywords": [
            "sip",
            "sips",
            "systematic",
            "stp",
            "swp",
            "5000",
            "5,000",
            "monthly",
            "hybrid",
            "instalment",
            "installment",
            "active sip",
            "no active sip",
            "without sip",
        ],
        "sql_table_markers": ["sipstp"],
    },
    {
        "id": "holdings_schemes",
        "summary": "Holdings/unit balance from processed_trxns; scheme_master scheme_type; asset_class on scheme_setup; CGF; liquid-only logic.",
        "keywords": [
            "liquid",
            "cash",
            "units",
            "holding",
            "holdings",
            "scheme",
            "schemes",
            "hybrid",
            "balanced",
            "equity fund",
            "only in",
        ],
        "sql_table_markers": ["scheme_master", "scheme_setup"],
    },
    {
        "id": "dormant_holdings",
        "summary": "Dormant/inactive via customer_schemes.l_trxn_date; zero units via processed_trxns aggregates.",
        "keywords": [
            "dormant",
            "inactive",
            "not transacted",
            "no transaction",
            "zero units",
            "0 units",
        ],
        "sql_table_markers": ["customer_schemes"],
    },
    {
        "id": "tax_profile",
        "summary": "NRI (tax_status.nri_nre), minor (minor_flag), CGF scheme membership.",
        "keywords": ["nri", "nre", "minor", "cgf", "capital gains feeder"],
        "sql_table_markers": ["tax_status", "cgf_flag"],
    },
    {
        "id": "banking_otm",
        "summary": "OTM / bank mandate via multiple_bank and payout_mechanism (optional).",
        "keywords": ["otm", "mandate", "bank"],
        "sql_table_markers": ["multiple_bank", "payout_mechanism"],
    },
]

VOCAB_BY_MODULE: dict[str, list[str]] = {
    "core_arn_investor": ["arn_scope", "name_search"],
    "geography_city": ["city_match", "name_search"],
    "investor_filters": ["age_years"],
    "activity_transactions": [
        "activity",
        "processed_trxns_date",
        "financial_year_fy25",
        "last_calendar_quarter",
    ],
    "sip_systematic": ["sipstp_active", "scheme_classification"],
    "holdings_schemes": ["scheme_classification"],
    "dormant_holdings": ["dormant_heuristics"],
    "tax_profile": ["nri", "minor"],
    "banking_otm": [],
}


def _table_index(guide: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(t["fully_qualified"]): t
        for t in guide.get("tables") or []
        if isinstance(t, dict) and t.get("fully_qualified")
    }


def _recipe_index() -> dict[str, dict[str, str]]:
    idx = {r["name"]: r for r in JOIN_RECIPES}
    for r in EXTRA_JOIN_RECIPES:
        idx[r["name"]] = r
    return idx


def main() -> int:
    if not GUIDE_JSON_PATH.is_file():
        print(f"Missing {GUIDE_JSON_PATH}; run build_investor_schema_guide.py first.", file=sys.stderr)
        return 1

    guide_raw = json.loads(GUIDE_JSON_PATH.read_text(encoding="utf-8"))
    guide = enrich_investor_schema_guide(guide_raw)
    tables = _table_index(guide)
    recipes = _recipe_index()
    patterns_by_id = {p["id"]: p for p in QUESTION_PATTERNS}

    module_ids = {m["id"] for m in MANIFEST_MODULES}
    buckets: dict[str, dict[str, Any]] = {
        mid: {
            "module_id": mid,
            "summary": next(m["summary"] for m in MANIFEST_MODULES if m["id"] == mid),
            "tables": [],
            "join_recipes": [],
            "question_patterns": [],
            "filter_vocabulary": {},
        }
        for mid in module_ids
    }

    for fq, mod_id in TABLE_TO_MODULE.items():
        if fq in tables and mod_id in buckets:
            buckets[mod_id]["tables"].append(tables[fq])

    all_recipe_names: set[str] = set()
    for name, mod_id in RECIPE_TO_MODULE.items():
        if name in recipes and mod_id in buckets:
            all_recipe_names.add(name)
            if recipes[name] not in buckets[mod_id]["join_recipes"]:
                buckets[mod_id]["join_recipes"].append(recipes[name])

    for pid, mod_id in PATTERN_TO_MODULE.items():
        if pid in patterns_by_id and mod_id in buckets:
            buckets[mod_id]["question_patterns"].append(patterns_by_id[pid])

    for mod_id, keys in VOCAB_BY_MODULE.items():
        for key in keys:
            if key in FILTER_VOCABULARY:
                buckets[mod_id]["filter_vocabulary"][key] = FILTER_VOCABULARY[key]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for mid, payload in buckets.items():
        path = OUT_DIR / f"{mid}.json"
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"wrote {path.name}: tables={len(payload['tables'])} recipes={len(payload['join_recipes'])}")

    manifest = {
        "version": 1,
        "source_guide": str(GUIDE_JSON_PATH.name),
        "sql_rules": guide.get("sql_rules") or {},
        "modules": MANIFEST_MODULES,
    }
    (OUT_DIR / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"wrote manifest.json ({len(MANIFEST_MODULES)} modules)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
