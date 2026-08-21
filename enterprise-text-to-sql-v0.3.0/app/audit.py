import json
import os
import threading
from datetime import datetime, timezone
from typing import Any, Dict, Optional


class AuditLogger:
    def __init__(self, path: str):
        self.path = path
        self._lock = threading.Lock()

    def write(self, event: Dict[str, Any]) -> None:
        record = dict(event)
        record["timestamp"] = datetime.now(timezone.utc).isoformat()
        
        # Enhanced audit fields
        if "user_context" in record:
            ctx = record["user_context"]
            record["user_id"] = ctx.get("user_id", "unknown")
            record["tenant_id"] = ctx.get("tenant_id", "unknown")
            record["ip_address"] = ctx.get("ip_address")
            record["user_agent"] = ctx.get("user_agent")
            record["roles"] = ctx.get("roles", [])
            del record["user_context"]
        
        # PII detection flags
        if "sql" in record:
            record["contains_pii"] = self._detect_pii(record["sql"])
        
        directory = os.path.dirname(self.path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        with self._lock:
            with open(self.path, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=True, default=str) + "\n")

    def _detect_pii(self, sql: str) -> bool:
        """Simple PII keyword detection in SQL."""
        pii_keywords = ["email", "phone", "ssn", "id_card", "passport", "credit_card"]
        sql_lower = sql.lower()
        return any(keyword in sql_lower for keyword in pii_keywords)
