"""Query result caching with Redis and fallback to in-memory."""
import hashlib
import json
import time
from typing import Any, Dict, Optional

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False


class QueryCache:
    """Cache for query results with TTL support."""
    
    def __init__(
        self,
        redis_url: Optional[str] = None,
        default_ttl: int = 3600,
        max_memory_items: int = 1000,
    ):
        self.default_ttl = default_ttl
        self.max_memory_items = max_memory_items
        
        # Try Redis first
        if redis_url and REDIS_AVAILABLE:
            try:
                self.redis = redis.from_url(redis_url, decode_responses=True)
                self.redis.ping()
                self.backend = "redis"
            except Exception:
                self.redis = None
                self.backend = "memory"
                self._memory_cache: Dict[str, Dict[str, Any]] = {}
        else:
            self.redis = None
            self.backend = "memory"
            self._memory_cache: Dict[str, Dict[str, Any]] = {}
    
    def _make_key(self, question: str, tenant_id: str, datasource: str, user_id: str = "") -> str:
        """Generate cache key from query parameters."""
        raw = f"{question}:{tenant_id}:{datasource}:{user_id}"
        return "query:" + hashlib.sha256(raw.encode()).hexdigest()
    
    def get(self, question: str, tenant_id: str, datasource: str, user_id: str = "") -> Optional[Dict]:
        """Retrieve cached query result."""
        key = self._make_key(question, tenant_id, datasource, user_id)
        
        if self.backend == "redis":
            try:
                data = self.redis.get(key)
                if data:
                    return json.loads(data)
            except Exception:
                pass
        else:
            # Memory backend
            if key in self._memory_cache:
                entry = self._memory_cache[key]
                if entry["expires_at"] > time.time():
                    return entry["data"]
                else:
                    del self._memory_cache[key]
        
        return None
    
    def set(
        self,
        question: str,
        tenant_id: str,
        datasource: str,
        result: Dict,
        ttl: Optional[int] = None,
        user_id: str = "",
    ):
        """Store query result in cache."""
        key = self._make_key(question, tenant_id, datasource, user_id)
        ttl = ttl or self.default_ttl
        
        if self.backend == "redis":
            try:
                self.redis.setex(key, ttl, json.dumps(result))
            except Exception:
                pass
        else:
            # Memory backend with LRU eviction
            if len(self._memory_cache) >= self.max_memory_items:
                # Remove oldest entry
                oldest_key = min(self._memory_cache.keys(), key=lambda k: self._memory_cache[k]["expires_at"])
                del self._memory_cache[oldest_key]
            
            self._memory_cache[key] = {
                "data": result,
                "expires_at": time.time() + ttl,
            }
    
    def invalidate(self, question: str, tenant_id: str, datasource: str, user_id: str = ""):
        """Remove specific cache entry."""
        key = self._make_key(question, tenant_id, datasource, user_id)
        
        if self.backend == "redis":
            try:
                self.redis.delete(key)
            except Exception:
                pass
        else:
            self._memory_cache.pop(key, None)
    
    def invalidate_pattern(self, pattern: str):
        """Invalidate all keys matching pattern (Redis only)."""
        if self.backend == "redis":
            try:
                for key in self.redis.scan_iter(match=f"query:*{pattern}*"):
                    self.redis.delete(key)
            except Exception:
                pass
    
    def clear_all(self):
        """Clear entire cache."""
        if self.backend == "redis":
            try:
                for key in self.redis.scan_iter(match="query:*"):
                    self.redis.delete(key)
            except Exception:
                pass
        else:
            self._memory_cache.clear()
    
    def stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        if self.backend == "redis":
            try:
                info = self.redis.info("stats")
                return {
                    "backend": "redis",
                    "hits": info.get("keyspace_hits", 0),
                    "misses": info.get("keyspace_misses", 0),
                    "keys": self.redis.dbsize(),
                }
            except Exception:
                return {"backend": "redis", "error": "unavailable"}
        else:
            return {
                "backend": "memory",
                "keys": len(self._memory_cache),
                "max_items": self.max_memory_items,
            }
