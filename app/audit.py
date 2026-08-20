import json
import os
import threading
from datetime import datetime, timezone
from typing import Any, Dict


class AuditLogger:
    def __init__(self, path: str):
        self.path = path
        self._lock = threading.Lock()

    def write(self, event: Dict[str, Any]) -> None:
        record = dict(event)
        record["timestamp"] = datetime.now(timezone.utc).isoformat()
        directory = os.path.dirname(self.path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        with self._lock:
            with open(self.path, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=True, default=str) + "\n")