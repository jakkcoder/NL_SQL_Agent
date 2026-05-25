#!/usr/bin/env python3
"""Smoke-test ADK /run for benchmark questions; print pass/fail per query."""

from __future__ import annotations

import json
import re
import sys
import time
import urllib.error
import urllib.request
from typing import Any

BASE = "http://127.0.0.1:8000"
APP = "investor_search_agent"
USER = "verify-backend-queries"
RUN_TIMEOUT = 240

QUERIES: list[tuple[str, list[str], list[str]]] = [
    (
        "Show my investors in Mumbai",
        ["tool_called", "executed_or_sql"],
        ["mumbai", "city", "customer_master"],
    ),
    (
        "Investor with Age between 30 and 40",
        ["tool_called", "executed_or_sql"],
        ["age", "dob"],
    ),
    (
        "Investors who did redemption in last quarter for equity funds.",
        ["tool_called", "executed_or_sql"],
        ["redemption", "trxndbcr", "equity", "processed_trxns"],
    ),
    (
        "Active SIPs above 5,000 per month in hybrid funds.",
        ["tool_called", "executed_or_sql"],
        ["sipstp", "sip", "amount", "hybrid", "balanced"],
    ),
    (
        "Dormant / inactive investors (investors not transacted in certain period / having 0 units across all schemes)",
        ["tool_called", "executed_or_sql"],
        ["l_trxn_date", "customer_schemes"],
    ),
    (
        "Top 20 investors by purchases in FY25",
        ["tool_called", "executed_or_sql"],
        ["purchase", "trxndbcr", "limit", "20"],
    ),
    (
        "Investors named 'Bhavin' in Mumbai or Ahmedabad.",
        ["tool_called", "executed_or_sql"],
        ["bhavin", "mumbai", "ahmedabad", "first_name"],
    ),
    (
        "NRI investors",
        ["tool_called", "executed_or_sql"],
        ["nri", "tax_status"],
    ),
    (
        "Minor Investors not invested in CGF schemes",
        ["tool_called", "executed_or_sql"],
        ["minor", "cgf", "scheme_setup"],
    ),
    (
        "Investors with no active SIP",
        ["tool_called", "executed_or_sql"],
        ["sipstp", "not exists"],
    ),
    (
        "Investors with investment only in Liquid / cash funds",
        ["tool_called", "executed_or_sql"],
        ["liquid", "processed_trxns", "scheme"],
    ),
]


def _post(url: str, body: dict[str, Any] | None, timeout: int) -> Any:
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def _get(url: str, timeout: int) -> Any:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def _normalize_events(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [e for e in data if isinstance(e, dict)]
    if isinstance(data, dict):
        if isinstance(data.get("events"), list):
            return [e for e in data["events"] if isinstance(e, dict)]
        if data.get("content"):
            return [data]
    return []


def _extract_tool_response(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    last: dict[str, Any] | None = None
    for ev in events:
        for part in (ev.get("content") or {}).get("parts") or []:
            if not isinstance(part, dict):
                continue
            fr = part.get("functionResponse") or part.get("function_response")
            if not isinstance(fr, dict):
                continue
            resp = fr.get("response")
            if isinstance(resp, dict):
                last = resp
    return last


def _sql_from_session(state: dict[str, Any]) -> str:
    fq = state.get("final_query") or {}
    if isinstance(fq, dict):
        return str(fq.get("sql") or fq.get("sql_postgresql") or "")
    return str(state.get("last_sql") or "")


def _check_sql(sql: str, keywords: list[str]) -> list[str]:
    low = sql.lower()
    missing = []
    for kw in keywords:
        k = kw.lower()
        if k == "not exists" and "not exists" not in low:
            missing.append(kw)
        elif k not in low:
            missing.append(kw)
    return missing


def main() -> int:
    try:
        _get(f"{BASE}/health", 5)
    except Exception as exc:
        print(f"Backend not reachable at {BASE}: {exc}", file=sys.stderr)
        return 1

    results: list[dict[str, Any]] = []
    for i, (question, checks, sql_keywords) in enumerate(QUERIES, 1):
        print(f"\n{'=' * 72}\n[{i}/{len(QUERIES)}] {question}\n{'=' * 72}")
        row: dict[str, Any] = {"question": question, "ok": False, "issues": []}
        t0 = time.perf_counter()
        try:
            sess = _post(f"{BASE}/apps/{APP}/users/{USER}/sessions", {}, 30)
            sid = sess.get("id") or sess.get("sessionId")
            _post(
                f"{BASE}/run",
                {
                    "appName": APP,
                    "userId": USER,
                    "sessionId": sid,
                    "newMessage": {"role": "user", "parts": [{"text": question}]},
                },
                RUN_TIMEOUT,
            )
            after = _get(f"{BASE}/apps/{APP}/users/{USER}/sessions/{sid}", 30)
        except urllib.error.HTTPError as exc:
            row["issues"].append(f"HTTP {exc.code}: {exc.read().decode(errors='replace')[:500]}")
            results.append(row)
            print("FAIL:", row["issues"][0])
            continue
        except Exception as exc:
            row["issues"].append(str(exc))
            results.append(row)
            print("FAIL:", exc)
            continue

        elapsed = time.perf_counter() - t0
        row["elapsed_s"] = round(elapsed, 1)
        state = after.get("state") or {}
        events = _normalize_events(after.get("events") or [])
        tool = _extract_tool_response(events)
        sql = _sql_from_session(state)

        if tool is None:
            row["issues"].append("Root agent did not return generate_catalog_sql_query_tool response")
        else:
            row["tool_status"] = tool.get("status")
            row["executed"] = tool.get("executed")
            row["row_count"] = tool.get("row_count") or tool.get("count") or len(tool.get("rows") or [])
            row["reply_head"] = (tool.get("reply") or "")[:200]
            if tool.get("status") == "blocked":
                row["issues"].append("ARN scope blocked (unexpected)")
            if tool.get("status") == "error":
                err = tool.get("execute_error") or tool.get("validation_error") or tool.get("reply")
                row["issues"].append(f"Tool error: {str(err)[:300]}")
            if "Catalog SQL generator failed" in (tool.get("reply") or ""):
                row["issues"].append("SQL generator failed")

        if not sql.strip():
            row["issues"].append("No SQL in session state (final_query / last_sql)")
        else:
            row["sql_head"] = sql[:220].replace("\n", " ")
            missing_kw = _check_sql(sql, sql_keywords)
            if missing_kw:
                row["issues"].append(f"SQL missing expected tokens: {missing_kw}")

        if tool and tool.get("executed") and (row.get("row_count") or 0) == 0:
            row["issues"].append("Executed but 0 rows (may be valid for strict filters)")

        row["ok"] = len(row["issues"]) == 0 and tool is not None and tool.get("status") == "ok"
        if tool and tool.get("status") == "ok" and not tool.get("executed"):
            # SQL-only mode still ok if SQL present
            if sql.strip():
                row["ok"] = len([x for x in row["issues"] if "0 rows" not in x]) == 0

        results.append(row)
        status = "PASS" if row["ok"] else "FAIL"
        print(f"{status} in {row['elapsed_s']}s | tool={row.get('tool_status')} executed={row.get('executed')} rows={row.get('row_count')}")
        if row.get("sql_head"):
            print(f"  SQL: {row['sql_head']}…")
        if row.get("reply_head"):
            print(f"  Reply: {row['reply_head']}…")
        for issue in row["issues"]:
            print(f"  ! {issue}")

    passed = sum(1 for r in results if r.get("ok"))
    print(f"\n\nSUMMARY: {passed}/{len(results)} passed")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
