from datetime import datetime, timezone
from typing import Any


class AuditLogger:
    """Small local audit hook for MVP development."""

    def log_event(self, event_type: str, payload: dict[str, Any]) -> None:
        timestamp = datetime.now(timezone.utc).isoformat()
        safe_payload = {key: value for key, value in payload.items() if key not in {"rows", "email", "mobile_number"}}
        print({"timestamp": timestamp, "event_type": event_type, "payload": safe_payload})
