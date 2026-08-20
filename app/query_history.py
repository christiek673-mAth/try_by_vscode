"""Query history storage and retrieval."""
import json
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional

from pydantic import BaseModel


class QueryHistoryEntry(BaseModel):
    """Single query history record."""
    
    query_id: str
    timestamp: float
    user_id: str
    tenant_id: str
    question: str
    sql: str
    datasource: str
    row_count: int
    execution_ms: float
    success: bool
    error: Optional[str] = None


class QueryHistory:
    """Manages query history with file-based storage."""
    
    def __init__(self, storage_path: str = "./data/query_history.jsonl", retention_days: int = 90):
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.retention_days = retention_days
        self._last_cleanup = 0
    
    def add(
        self,
        user_id: str,
        tenant_id: str,
        question: str,
        sql: str,
        datasource: str,
        row_count: int,
        execution_ms: float,
        success: bool,
        error: Optional[str] = None,
    ) -> str:
        """Add query to history."""
        query_id = str(uuid.uuid4())
        entry = QueryHistoryEntry(
            query_id=query_id,
            timestamp=time.time(),
            user_id=user_id,
            tenant_id=tenant_id,
            question=question,
            sql=sql,
            datasource=datasource,
            row_count=row_count,
            execution_ms=execution_ms,
            success=success,
            error=error,
        )
        
        with open(self.storage_path, "a", encoding="utf-8") as f:
            f.write(entry.json() + "\n")
        
        self._cleanup_if_needed()
        return query_id
    
    def get_user_history(
        self,
        user_id: str,
        tenant_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> List[QueryHistoryEntry]:
        """Retrieve user's query history."""
        if not self.storage_path.exists():
            return []
        
        entries = []
        cutoff_time = time.time() - (self.retention_days * 86400)
        
        with open(self.storage_path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    entry = QueryHistoryEntry(**json.loads(line))
                    if (entry.user_id == user_id and 
                        entry.tenant_id == tenant_id and 
                        entry.timestamp > cutoff_time):
                        entries.append(entry)
                except Exception:
                    continue
        
        entries.sort(key=lambda x: x.timestamp, reverse=True)
        return entries[offset:offset + limit]
    
    def get_by_id(self, query_id: str) -> Optional[QueryHistoryEntry]:
        """Retrieve specific query by ID."""
        if not self.storage_path.exists():
            return None
        
        with open(self.storage_path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    entry = QueryHistoryEntry(**json.loads(line))
                    if entry.query_id == query_id:
                        return entry
                except Exception:
                    continue
        return None
    
    def search(
        self,
        user_id: str,
        tenant_id: str,
        keyword: str,
        limit: int = 20,
    ) -> List[QueryHistoryEntry]:
        """Search query history by keyword."""
        if not self.storage_path.exists():
            return []
        
        entries = []
        cutoff_time = time.time() - (self.retention_days * 86400)
        keyword_lower = keyword.lower()
        
        with open(self.storage_path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    entry = QueryHistoryEntry(**json.loads(line))
                    if (entry.user_id == user_id and 
                        entry.tenant_id == tenant_id and 
                        entry.timestamp > cutoff_time and
                        (keyword_lower in entry.question.lower() or 
                         keyword_lower in entry.sql.lower())):
                        entries.append(entry)
                except Exception:
                    continue
        
        entries.sort(key=lambda x: x.timestamp, reverse=True)
        return entries[:limit]
    
    def _cleanup_if_needed(self):
        """Remove old entries beyond retention period."""
        now = time.time()
        if now - self._last_cleanup < 86400:
            return
        
        if not self.storage_path.exists():
            return
        
        cutoff_time = now - (self.retention_days * 86400)
        temp_path = self.storage_path.with_suffix(".tmp")
        
        try:
            with open(self.storage_path, "r", encoding="utf-8") as f_in:
                with open(temp_path, "w", encoding="utf-8") as f_out:
                    for line in f_in:
                        try:
                            entry = json.loads(line)
                            if entry.get("timestamp", 0) > cutoff_time:
                                f_out.write(line)
                        except Exception:
                            continue
            
            temp_path.replace(self.storage_path)
            self._last_cleanup = now
        except Exception:
            if temp_path.exists():
                temp_path.unlink()
    
    def stats(self) -> Dict:
        """Get history statistics."""
        if not self.storage_path.exists():
            return {"total_queries": 0}
        
        total = 0
        success = 0
        cutoff_time = time.time() - (self.retention_days * 86400)
        
        with open(self.storage_path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    entry = json.loads(line)
                    if entry.get("timestamp", 0) > cutoff_time:
                        total += 1
                        if entry.get("success"):
                            success += 1
                except Exception:
                    continue
        
        return {
            "total_queries": total,
            "success_queries": success,
            "success_rate": round(success / total * 100, 2) if total > 0 else 0,
        }

