#!/usr/bin/env python3
"""POST each query to the local ADK /run API and print session state (final_query / last_sql).

Usage (from repo):
  cd backend && source .venv/bin/activate && export PYTHONPATH=. \\
    && uvicorn app.main:app --host 127.0.0.1 --port 8000

  # other terminal:
  cd backend && source .venv/bin/activate && export PYTHONPATH=. \\
    && python scripts/run_query_benchmark.py
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from typing import Any

BASE = "http://127.0.0.1:8000"
APP = "investor_search_agent"
USER = "benchmark-user"

QUERIES: list[str] = [
    "Show my investors in Mumbai",
    "Investor with Age between 30 and 40",
    "Investors who did redemption in last quarter for equity funds.",
    "Active SIPs above 5,000 per month in hybrid funds.",
    "Dormant / inactive investors (investors not transacted in certain period / having 0 units across all schemes)",
    "Top 20 investors by purchases in FY25",
    "Investors named 'Bhavin' in Mumbai or Ahmedabad.",
    "NRI investors",
    "Minor Investors not invested in CGF schemes",
    "Investors with no active SIP",
    "Investors with investment only in Liquid / cash funds",
]


def _post_json(url: str, payload: dict[str, Any] | None, timeout: int) -> Any:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json"} if data is not None else {},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _get_json(url: str, timeout: int) -> Any:
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _assistant_text_tail(events: list[dict[str, Any]], max_chars: int = 1200) -> str:
    for ev in reversed(events):
        content = ev.get("content") or {}
        parts = content.get("parts") or []
        texts: list[str] = []
        for p in parts:
            if isinstance(p, dict) and p.get("text"):
                texts.append(str(p["text"]))
        if texts:
            blob = "\n".join(texts).strip()
            if len(blob) > max_chars:
                return blob[:max_chars] + "\n…[truncated]"
            return blob
    return "(no assistant text in events)"


def main() -> int:
    try:
        _get_json(f"{BASE}/health", timeout=5)
    except urllib.error.URLError as exc:
        print(f"Backend not reachable at {BASE}: {exc}", file=sys.stderr)
        print("Start uvicorn from backend/: export PYTHONPATH=. && uvicorn app.main:app --host 127.0.0.1 --port 8000", file=sys.stderr)
        return 1

    print("=" * 80)
    print("ADK benchmark: one fresh session per query; then GET session for state.")
    print("=" * 80)

    for i, question in enumerate(QUERIES, start=1):
        print(f"\n### {i}/{len(QUERIES)} — {question!r}\n")

        try:
            session = _post_json(
                f"{BASE}/apps/{APP}/users/{USER}/sessions",
                {},
                timeout=30,
            )
        except urllib.error.HTTPError as exc:
            print(f"create_session HTTP {exc.code}: {exc.read().decode()[:500]}")
            continue

        sid = session.get("id") or session.get("sessionId")
        run_body = {
            "appName": APP,
            "userId": USER,
            "sessionId": sid,
            "newMessage": {"role": "user", "parts": [{"text": question}]},
        }

        try:
            _post_json(f"{BASE}/run", run_body, timeout=180)
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode(errors="replace")
            print(f"/run HTTP {exc.code}: {raw[:1500]}")
            continue
        except Exception as exc:
            print(f"/run error: {exc}")
            continue

        try:
            sess_after = _get_json(
                f"{BASE}/apps/{APP}/users/{USER}/sessions/{sid}",
                timeout=30,
            )
        except Exception as exc:
            print(f"get_session error: {exc}")
            continue

        state = sess_after.get("state") or {}
        fq = state.get("final_query") or state.get("finalQuery")
        last_sql = state.get("last_sql") or state.get("lastSql")
        last_params = state.get("last_sql_parameters") or state.get("lastSqlParameters")

        events = sess_after.get("events") or []
        tail = _assistant_text_tail(events)

        print("--- final_query (session.state) ---")
        if fq:
            print(json.dumps(fq, indent=2, default=str)[:4000])
        else:
            print("(missing final_query in state)")

        print("\n--- last_sql (top-level session.state copy) ---")
        if isinstance(last_sql, str):
            print(last_sql[:2500] + ("…" if len(last_sql) > 2500 else ""))
        else:
            print(repr(last_sql))

        if last_params is not None:
            print("\n--- last_sql_parameters ---")
            print(json.dumps(last_params, default=str)[:1500])

        print("\n--- assistant reply (tail from last event with text) ---")
        print(tail)

        print("-" * 80)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
