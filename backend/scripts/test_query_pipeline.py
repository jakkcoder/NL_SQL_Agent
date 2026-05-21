#!/usr/bin/env python3
"""Run sample NL queries through plan -> SQL -> DB and print results."""

from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import get_config
from app.db.postgres import (
    DatabaseNotConfiguredError,
    DatabaseUnavailableError,
    PostgresClient,
)
from app.models.search_plan import InvestorTab
from app.services.individual_executor import IndividualInvestorExecutor
from app.services.intent_parser import parse_investor_search_intent
from app.services.non_individual_executor import NonIndividualInvestorExecutor
from app.services.plan_validator import PlanValidator
from app.services.query_arguments import plan_to_query_arguments

# Example NL coverage: pytest tests/test_example_queries_sql.py tests/test_example_queries_adk_state.py -q

SAMPLE_QUERIES = [
    ("individual default", "show individual investors"),
    ("individual active OTM", "show active individual investors with OTM"),
    ("individual SIP 3 month", "individual investors with SIP in last 3 months"),
    ("individual holdings", "individual investors with holdings"),
    ("non-individual active OTM", "active non-individual investors with OTM"),
    ("non-individual CGF", "non-individual CGF investors"),
]


def run_query(label: str, query: str, arn: str, config) -> dict:
    plan = parse_investor_search_intent(query)
    validation = PlanValidator().validate(plan)
    args = plan_to_query_arguments(plan)
    result = {
        "label": label,
        "query": query,
        "investor_tab": plan.investor_tab.value,
        "validation": validation.status,
        "can_execute": validation.can_execute,
        "engine": args.get("engine"),
        "filters_applied": args.get("filters_applied"),
    }
    if not validation.can_execute:
        result["message"] = validation.message
        return result

    db_config = config.database
    db = PostgresClient(
        config.database_url_value,
        db_config.statement_timeout_ms,
        min_size=1,
        max_size=1,
        connect_timeout_seconds=db_config.connect_timeout_seconds,
        pool_timeout_seconds=db_config.pool_timeout_seconds,
    )
    try:
        db.open()
        if plan.investor_tab == InvestorTab.INDIVIDUAL:
            executor = IndividualInvestorExecutor(db)
            sql, params = executor._build_function_call(plan, arn)
            result["sql_preview"] = " ".join(sql.split())[:200]
            result["param_count"] = len(params)
            rows = executor.execute(plan, arn)
        elif plan.investor_tab == InvestorTab.NON_INDIVIDUAL:
            executor = NonIndividualInvestorExecutor(db, config)
            rows = executor.execute(plan, arn)
            result["sql_calls"] = len(getattr(db, "_last_calls", [])) if hasattr(db, "_last_calls") else "n/a"
        else:
            rows = []
        result["row_count"] = len(rows)
        result["status"] = "ok"
    except (DatabaseNotConfiguredError, DatabaseUnavailableError) as exc:
        result["status"] = "no_db"
        result["error"] = str(exc)
    except Exception as exc:
        result["status"] = "error"
        result["error"] = str(exc)
        result["traceback"] = traceback.format_exc()
    finally:
        db.close()
    return result


def main() -> int:
    config = get_config()
    arn = config.search.default_dev_arn
    print(f"ARN={arn} DB={'configured' if config.database_url_value else 'missing'}\n")

    outcomes = []
    for label, query in SAMPLE_QUERIES:
        print(f"--- {label}: {query!r}")
        outcome = run_query(label, query, arn, config)
        outcomes.append(outcome)
        print(json.dumps({k: v for k, v in outcome.items() if k != "traceback"}, indent=2))
        if outcome.get("traceback"):
            print(outcome["traceback"])
        print()

    failed = [o for o in outcomes if o.get("status") == "error"]
    blocked = [o for o in outcomes if not o.get("can_execute")]
    print(f"Summary: {len(outcomes)} queries, {len(failed)} errors, {len(blocked)} blocked")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
