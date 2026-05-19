from typing import Any


def format_rows_for_chat(rows: list[dict[str, Any]], limit: int, offset: int) -> str:
    if not rows:
        return "No investors found for this request."

    lines = [f"Found {len(rows)} investor(s). Showing {offset + 1}-{offset + len(rows)}:"]
    for row in rows[: min(len(rows), 10)]:
        name = row.get("name") or row.get("first_name") or "Unknown"
        pan = row.get("pan_number") or "N/A"
        dob = row.get("dob") or "N/A"
        email = row.get("email") or "N/A"
        mobile = row.get("mobile_number") or "N/A"
        lines.append(f"- {name} | PAN: {pan} | DOB: {dob} | Email: {email} | Mobile: {mobile}")

    if len(rows) > 10:
        lines.append(f"...and {len(rows) - 10} more on this page.")
    if len(rows) == limit:
        lines.append("Ask for the next page to see more results.")
    return "\n".join(lines)
